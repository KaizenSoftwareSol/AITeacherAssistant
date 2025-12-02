import os
import sys
import argparse
from pathlib import Path
from typing import Iterable, Tuple, Set

# Load .env file automatically
try:
    from dotenv import load_dotenv
    # Look for .env in project root (parent of scripts folder)
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded environment from {env_path}")
    else:
        load_dotenv()  # Try default locations
except ImportError:
    print("Note: python-dotenv not installed, installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-dotenv"])
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded environment from {env_path}")

import requests

try:
    from supabase import create_client, Client
except Exception as e:
    print("Please install supabase python client: pip install supabase")
    raise


BUCKETS = [
    "LECTURE_MATERIALS",
    "CURRICULUM_DOCS",
    "GENERATED_CONTENT",
    "USER_UPLOADS",
]


def guess_content_type(path: str) -> str:
    path_lower = (path or "").lower()
    if path_lower.endswith(".pdf"):
        return "application/pdf"
    if path_lower.endswith(".json"):
        return "application/json"
    if path_lower.endswith(".txt"):
        return "text/plain; charset=utf-8"
    if path_lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


def list_local_buckets(local: Client) -> list:
    """List all buckets in local Supabase storage."""
    try:
        buckets = local.storage.list_buckets()
        bucket_names = [b.name for b in buckets]
        return bucket_names
    except Exception as e:
        print(f"[!] Could not list local buckets: {e}")
        return []


def create_bucket_via_api(base_url: str, service_key: str, bucket_name: str, public: bool = True) -> bool:
    """Create a bucket using direct REST API call."""
    url = f"{base_url}/storage/v1/bucket"
    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "Content-Type": "application/json",
    }
    payload = {
        "id": bucket_name,
        "name": bucket_name,
        "public": public,
    }
    try:
        resp = requests.post(url, json=payload, headers=headers)
        if resp.status_code in (200, 201):
            return True
        elif resp.status_code == 400 and "already exists" in resp.text.lower():
            return True  # Already exists
        elif resp.status_code == 409:  # Conflict = already exists
            return True
        else:
            print(f"    API response: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"    Request error: {e}")
        return False


def ensure_buckets(local: Client, bucket_names: Iterable[str], base_url: str = None, service_key: str = None) -> None:
    # First list existing buckets
    existing = list_local_buckets(local)
    print(f"    Existing local buckets: {existing}")
    
    for name in bucket_names:
        if name in existing:
            print(f"[=] Bucket already exists: {name}")
            continue
        
        # Try using direct API if credentials provided
        if base_url and service_key:
            print(f"[*] Creating bucket '{name}' via REST API...")
            if create_bucket_via_api(base_url, service_key, name, public=True):
                print(f"[+] Created bucket: {name}")
                continue
        
        # Fallback to SDK
        try:
            local.storage.create_bucket(name, {"public": True})
            print(f"[+] Created bucket: {name}")
        except Exception as e:
            error_str = str(e)
            if "already exists" in error_str.lower() or "duplicate" in error_str.lower():
                print(f"[=] Bucket exists: {name}")
            else:
                print(f"[!] Failed to create bucket '{name}': {e}")


def gather_paths_from_cloud(cloud: Client) -> Set[Tuple[str, str]]:
    """
    Gather storage objects to migrate using DB metadata rather than bucket listing.
    Returns a set of tuples: (bucket_name, storage_path)
    """
    paths: Set[Tuple[str, str]] = set()

    # lecture_content table: storage_bucket + storage_path
    try:
        result = cloud.table("lecture_content").select("storage_bucket,storage_path").execute()
        for row in result.data or []:
            bucket = row.get("storage_bucket")
            path = row.get("storage_path")
            if bucket and path:
                paths.add((bucket, path))
    except Exception as e:
        print(f"[!] Warning: could not fetch lecture_content: {e}")

    # documents table: file_path + content_json_path are in USER_UPLOADS
    try:
        result = cloud.table("documents").select("file_path,content_json_path").execute()
        for row in result.data or []:
            file_path = row.get("file_path")
            json_path = row.get("content_json_path")
            if file_path:
                paths.add(("USER_UPLOADS", file_path))
            if json_path:
                paths.add(("USER_UPLOADS", json_path))
    except Exception as e:
        print(f"[!] Warning: could not fetch documents: {e}")

    return paths


def list_cloud_buckets(cloud: Client) -> list:
    """List all buckets in cloud Supabase storage."""
    try:
        buckets = cloud.storage.list_buckets()
        bucket_names = [b.name for b in buckets]
        return bucket_names
    except Exception as e:
        print(f"[!] Could not list cloud buckets: {e}")
        return []


def list_bucket_files(client: Client, bucket_name: str, path: str = "") -> list:
    """Recursively list all files in a bucket."""
    all_files = []
    try:
        items = client.storage.from_(bucket_name).list(path)
        for item in items:
            item_path = f"{path}/{item['name']}" if path else item['name']
            if item.get('id') is None:  # It's a folder
                all_files.extend(list_bucket_files(client, bucket_name, item_path))
            else:  # It's a file
                all_files.append(item_path)
    except Exception as e:
        print(f"[!] Error listing {bucket_name}/{path}: {e}")
    return all_files


def migrate_objects(cloud: Client, local: Client, objects: Set[Tuple[str, str]], bucket_mapping: dict = None) -> None:
    migrated = 0
    skipped = 0
    failed = 0
    
    if bucket_mapping is None:
        bucket_mapping = {}

    for bucket_name, storage_path in sorted(objects):
        # Use mapping if available (e.g., GENERATED_CONTENT -> generated-content)
        cloud_bucket = bucket_mapping.get(bucket_name, bucket_name)
        
        print(f"[>] Migrating {cloud_bucket}:{storage_path}")
        
        # Step 1: Download from cloud
        try:
            data = cloud.storage.from_(cloud_bucket).download(storage_path)
            if data is None:
                print(f"    [!] No data downloaded, skipping")
                skipped += 1
                continue
            print(f"    [✓] Downloaded {len(data)} bytes from cloud")
        except Exception as e:
            print(f"    [x] DOWNLOAD FAILED from cloud: {e}")
            failed += 1
            continue
        
        # Step 2: Upload to local
        try:
            content_type = guess_content_type(storage_path)
            try:
                local.storage.from_(bucket_name).upload(
                    storage_path,
                    data,
                    {"content-type": content_type, "upsert": "true"},
                )
            except Exception as upload_err:
                # If 'upsert' not supported, try remove then upload
                print(f"    [!] Upsert failed, trying remove+upload: {upload_err}")
                try:
                    local.storage.from_(bucket_name).remove([storage_path])
                except Exception:
                    pass
                local.storage.from_(bucket_name).upload(
                    storage_path,
                    data,
                    {"content-type": content_type},
                )
            print(f"    [✓] Uploaded to local {bucket_name}")
            migrated += 1
        except Exception as e:
            print(f"    [x] UPLOAD FAILED to local: {e}")
            failed += 1

    print(f"\nSummary: migrated={migrated}, skipped={skipped}, failed={failed}, total={len(objects)}")


def main():
    parser = argparse.ArgumentParser(description="Migrate Supabase storage objects from cloud to local.")
    parser.add_argument("--cloud-url", default=os.getenv("CLOUD_SUPABASE_URL") or os.getenv("SUPABASE_URL_CLOUD"), help="Cloud Supabase URL")
    parser.add_argument(
        "--cloud-key",
        default=os.getenv("CLOUD_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY_CLOUD"),
        help="Cloud Supabase service role key",
    )
    parser.add_argument("--local-url", default=os.getenv("SUPABASE_URL") or os.getenv("LOCAL_SUPABASE_URL"), help="Local Supabase URL")
    parser.add_argument(
        "--local-key",
        default=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("LOCAL_SUPABASE_SERVICE_ROLE_KEY"),
        help="Local Supabase service role key",
    )
    parser.add_argument(
        "--buckets",
        nargs="*",
        default=BUCKETS,
        help=f"Bucket names to ensure locally (default: {', '.join(BUCKETS)})",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list cloud buckets and files, don't migrate",
    )
    parser.add_argument(
        "--from-storage",
        action="store_true",
        help="Migrate all files found in cloud storage (not just DB references)",
    )
    args = parser.parse_args()

    missing = []
    if not args.cloud_url:
        missing.append("cloud-url")
    if not args.cloud_key:
        missing.append("cloud-key")
    if not args.local_url:
        missing.append("local-url")
    if not args.local_key:
        missing.append("local-key")
    if missing:
        print(f"Missing required args/env: {', '.join(missing)}")
        print("Provide via flags or environment variables:")
        print("  CLOUD_SUPABASE_URL and CLOUD_SUPABASE_SERVICE_ROLE_KEY")
        print("  SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (for local)")
        sys.exit(1)

    print("[*] Connecting to Cloud Supabase...")
    cloud = create_client(args.cloud_url, args.cloud_key)
    print("[*] Connecting to Local Supabase...")
    local = create_client(args.local_url, args.local_key)

    # First, list actual buckets in cloud storage
    print("\n[*] Listing CLOUD storage buckets...")
    cloud_buckets = list_cloud_buckets(cloud)
    print(f"    Cloud buckets found: {cloud_buckets}")
    
    if args.list_only:
        # List files in each bucket
        for bucket in cloud_buckets:
            print(f"\n[*] Files in cloud bucket '{bucket}':")
            files = list_bucket_files(cloud, bucket)
            for f in files[:20]:  # Show first 20
                print(f"    - {f}")
            if len(files) > 20:
                print(f"    ... and {len(files) - 20} more files")
        print("\n[✓] List complete.")
        return

    # Ensure local buckets exist (use cloud bucket names)
    buckets_to_create = set(args.buckets)
    buckets_to_create.update(cloud_buckets)  # Also create any bucket found in cloud
    
    print("\n[*] Ensuring local buckets...")
    ensure_buckets(local, buckets_to_create, base_url=args.local_url, service_key=args.local_key)
    
    # Verify buckets were created
    print("\n[*] Verifying local buckets after creation...")
    final_buckets = list_local_buckets(local)
    print(f"    Local buckets now: {final_buckets}")
    
    missing_buckets = buckets_to_create - set(final_buckets)
    if missing_buckets:
        print(f"\n[!] WARNING: These buckets could not be created: {missing_buckets}")
        print("[!] You may need to create them manually in Supabase Studio: http://127.0.0.1:54423")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            return
    
    if args.from_storage:
        # Migrate directly from storage (all files in all buckets)
        print("\n[*] Gathering files directly from cloud storage...")
        objects: Set[Tuple[str, str]] = set()
        for bucket in cloud_buckets:
            print(f"    Scanning bucket: {bucket}")
            files = list_bucket_files(cloud, bucket)
            for f in files:
                objects.add((bucket, f))
            print(f"    Found {len(files)} files in {bucket}")
    else:
        # Use DB metadata to find files
        print("\n[*] Gathering storage paths from cloud database metadata...")
        objects = gather_paths_from_cloud(cloud)
        
        # Check which buckets are referenced in DB
        referenced_buckets = set(b for b, _ in objects)
        print(f"    DB references buckets: {referenced_buckets}")
        print(f"    Cloud has buckets: {set(cloud_buckets)}")
        
        # Warn about mismatches
        missing_buckets = referenced_buckets - set(cloud_buckets)
        if missing_buckets:
            print(f"\n[!] WARNING: DB references buckets that don't exist in cloud: {missing_buckets}")
            print("[!] Files in these buckets cannot be migrated!")
            print("[!] You may want to run with --from-storage to migrate actual cloud files")

    print(f"\n[*] Found {len(objects)} objects to migrate")

    print("[*] Migrating objects...")
    migrate_objects(cloud, local, objects)

    print("\n[✓] Done.")


if __name__ == "__main__":
    main()


