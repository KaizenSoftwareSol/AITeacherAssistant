"""
Script to restore university-level data from Cloud Supabase to Local Supabase.

This script migrates:
- university table
- semester table (university-level semesters)
- course table (and related data)
- teacher table
- student table
- enrollment table
- lecture table
- And other university-related tables

Usage:
    python scripts/restore_university_data.py
    
    # Or specify cloud credentials
    python scripts/restore_university_data.py --cloud-url <url> --cloud-key <key>
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any
import json

# Load .env file automatically
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded environment from {env_path}")
    else:
        load_dotenv()
except ImportError:
    print("Note: python-dotenv not installed, installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-dotenv"])
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded environment from {env_path}")

try:
    from supabase import create_client, Client
except Exception as e:
    print("Please install supabase python client: pip install supabase")
    raise


# Tables to migrate in order (respecting foreign key dependencies)
MIGRATION_ORDER = [
    "university",           # No dependencies
    "semester",            # Depends on university
    "course",              # Depends on university
    "teacher",             # Depends on university, users
    "student",             # Depends on university, users
    "enrollment",          # Depends on course, student, semester
    "lecture",             # Depends on course, semester, document
    "document",            # Depends on teacher
    "assessment",          # Depends on course, lecture
    "question",            # Depends on assessment
    "notification",        # Depends on users, course, lecture
]


def fetch_table_data(client: Client, table_name: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Fetch all data from a table with optional filters."""
    try:
        query = client.table(table_name).select("*")
        
        # Apply filters
        if filters:
            for key, value in filters.items():
                if value is None:
                    query = query.is_(key, "null")
                else:
                    query = query.eq(key, value)
        
        # Fetch all records (handle pagination)
        all_data = []
        page_size = 1000
        offset = 0
        
        while True:
            result = query.range(offset, offset + page_size - 1).execute()
            if not result.data:
                break
            all_data.extend(result.data)
            if len(result.data) < page_size:
                break
            offset += page_size
        
        return all_data
    except Exception as e:
        print(f"    [x] Error fetching {table_name}: {e}")
        return []


def insert_table_data(client: Client, table_name: str, data: List[Dict[str, Any]], batch_size: int = 100) -> int:
    """Insert data into a table in batches."""
    if not data:
        return 0
    
    inserted = 0
    failed = 0
    
    # Insert in batches
    for i in range(0, len(data), batch_size):
        batch = data[i:i + batch_size]
        try:
            result = client.table(table_name).insert(batch).execute()
            inserted += len(result.data) if result.data else len(batch)
            print(f"    [✓] Inserted {len(batch)} records into {table_name}")
        except Exception as e:
            print(f"    [x] Failed to insert batch into {table_name}: {e}")
            # Try inserting one by one
            for record in batch:
                try:
                    client.table(table_name).insert(record).execute()
                    inserted += 1
                except Exception as ex:
                    print(f"      [x] Failed to insert record: {ex}")
                    failed += 1
    
    return inserted, failed


def clear_table_data(client: Client, table_name: str) -> int:
    """Clear all data from a table (use with caution!)."""
    try:
        # Delete all records
        result = client.table(table_name).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        return len(result.data) if result.data else 0
    except Exception as e:
        print(f"    [x] Error clearing {table_name}: {e}")
        return 0


def migrate_table(
    cloud: Client,
    local: Client,
    table_name: str,
    clear_local: bool = False,
    filters: Dict[str, Any] = None
) -> tuple[int, int]:
    """Migrate a single table from cloud to local."""
    print(f"\n[*] Migrating table: {table_name}")
    
    # Fetch from cloud
    print(f"    [*] Fetching data from cloud...")
    cloud_data = fetch_table_data(cloud, table_name, filters)
    print(f"    [✓] Found {len(cloud_data)} records in cloud")
    
    if not cloud_data:
        print(f"    [!] No data to migrate for {table_name}")
        return 0, 0
    
    # Clear local if requested
    if clear_local:
        print(f"    [*] Clearing local {table_name}...")
        cleared = clear_table_data(local, table_name)
        print(f"    [✓] Cleared {cleared} records from local")
    
    # Insert into local
    print(f"    [*] Inserting into local...")
    inserted, failed = insert_table_data(local, table_name, cloud_data)
    
    print(f"    [✓] Migration complete: {inserted} inserted, {failed} failed")
    return inserted, failed


def migrate_university_data(
    cloud_url: str,
    cloud_key: str,
    local_url: str,
    local_key: str,
    university_id: str = None,
    clear_local: bool = False,
    tables: List[str] = None
) -> None:
    """Main migration function."""
    print("=" * 60)
    print("University-Level Data Migration Script")
    print("=" * 60)
    
    # Connect to Supabase instances
    print("\n[*] Connecting to Cloud Supabase...")
    cloud = create_client(cloud_url, cloud_key)
    print("[*] Connecting to Local Supabase...")
    local = create_client(local_url, local_key)
    
    # Determine which tables to migrate
    tables_to_migrate = tables or MIGRATION_ORDER
    
    # Build filters if university_id is specified
    filters_map = {}
    if university_id:
        # Filter tables by university_id where applicable
        university_tables = ["university", "semester", "course", "teacher", "student", "enrollment", "lecture"]
        for table in university_tables:
            if table == "university":
                filters_map[table] = {"id": university_id}
            elif table == "semester":
                filters_map[table] = {"university_id": university_id, "course_id": None}  # Only university-level
            else:
                filters_map[table] = {"university_id": university_id}
    
    # Migrate each table in order
    total_inserted = 0
    total_failed = 0
    
    for table_name in tables_to_migrate:
        filters = filters_map.get(table_name)
        inserted, failed = migrate_table(
            cloud, local, table_name, 
            clear_local=clear_local and table_name == tables_to_migrate[0],  # Only clear first table
            filters=filters
        )
        total_inserted += inserted
        total_failed += failed
    
    # Summary
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Total records inserted: {total_inserted}")
    print(f"Total records failed: {total_failed}")
    print(f"Tables migrated: {len(tables_to_migrate)}")
    print("\n[✓] Migration complete!")
    print("\nNext steps:")
    print("1. Verify data in Local Supabase Studio: http://127.0.0.1:54423")
    print("2. Check that semesters are showing up correctly")
    print("3. Test your application endpoints")


def main():
    parser = argparse.ArgumentParser(
        description="Restore university-level data from Cloud Supabase to Local Supabase"
    )
    
    # Cloud Supabase credentials
    parser.add_argument(
        "--cloud-url",
        default=os.getenv("CLOUD_SUPABASE_URL") or os.getenv("SUPABASE_URL"),
        help="Cloud Supabase URL (or set CLOUD_SUPABASE_URL env var)"
    )
    parser.add_argument(
        "--cloud-key",
        default=os.getenv("CLOUD_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        help="Cloud Supabase Service Role Key (or set CLOUD_SUPABASE_SERVICE_ROLE_KEY env var)"
    )
    
    # Local Supabase credentials
    parser.add_argument(
        "--local-url",
        default=os.getenv("SUPABASE_URL", "http://127.0.0.1:54421"),
        help="Local Supabase URL (default: http://127.0.0.1:54421)"
    )
    parser.add_argument(
        "--local-key",
        default=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        help="Local Supabase Service Role Key (or set SUPABASE_SERVICE_ROLE_KEY env var)"
    )
    
    # Options
    parser.add_argument(
        "--university-id",
        help="Only migrate data for a specific university (UUID)"
    )
    parser.add_argument(
        "--clear-local",
        action="store_true",
        help="Clear local tables before migrating (WARNING: This deletes existing data!)"
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        help="Specific tables to migrate (default: all university-related tables)"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.cloud_url or not args.cloud_key:
        print("[x] Error: Cloud Supabase credentials required")
        print("    Set CLOUD_SUPABASE_URL and CLOUD_SUPABASE_SERVICE_ROLE_KEY in .env")
        print("    Or use --cloud-url and --cloud-key arguments")
        sys.exit(1)
    
    if not args.local_key:
        print("[x] Error: Local Supabase Service Role Key required")
        print("    Set SUPABASE_SERVICE_ROLE_KEY in .env")
        print("    Or use --local-key argument")
        sys.exit(1)
    
    # Confirm if clearing local data
    if args.clear_local:
        response = input("\n[!] WARNING: This will DELETE all existing local data. Continue? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            return
    
    # Run migration
    try:
        migrate_university_data(
            cloud_url=args.cloud_url,
            cloud_key=args.cloud_key,
            local_url=args.local_url,
            local_key=args.local_key,
            university_id=args.university_id,
            clear_local=args.clear_local,
            tables=args.tables
        )
    except KeyboardInterrupt:
        print("\n\n[!] Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[x] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
