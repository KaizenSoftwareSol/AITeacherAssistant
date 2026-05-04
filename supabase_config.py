# supabase_config.py

import os

from supabase import Client, create_client

from settings import settings


class SupabaseConfig:
    """Supabase configuration and client management."""

    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.anon_key = settings.SUPABASE_ANON_KEY
        self.service_key = settings.SUPABASE_SERVICE_ROLE_KEY
        self._client: Client = None
        self._admin_client: Client = None

    @property
    def client(self) -> Client:
        """Get Supabase client instance (anon key)."""
        if self._client is None:
            if not self.url or not self.anon_key:
                raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
            self._client = create_client(self.url, self.anon_key)
        return self._client

    @property
    def admin_client(self) -> Client:
        """Get Supabase admin client instance (service role key)."""
        if self._admin_client is None:
            if not self.url or not self.service_key:
                raise ValueError(
                    "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"
                )
            self._admin_client = create_client(self.url, self.service_key)
        return self._admin_client

    def get_storage_bucket(self, bucket_name: str):
        """Get a specific storage bucket."""
        return self.admin_client.storage.from_(
            bucket_name
        )  # Use admin client to bypass RLS

    def upload_file(
        self,
        bucket_name: str,
        file_path: str,
        file_data: bytes,
        file_options: dict = None,
    ):
        """Upload a file to Supabase storage."""
        bucket = self.admin_client.storage.from_(bucket_name)  # Use admin client
        return bucket.upload(file_path, file_data, file_options)

    def download_file(self, bucket_name: str, file_path: str):
        """Download a file from Supabase storage."""
        bucket = self.admin_client.storage.from_(bucket_name)  # Use admin client
        return bucket.download(file_path)

    def delete_file(self, bucket_name: str, file_path: str):
        """Delete a file from Supabase storage."""
        bucket = self.admin_client.storage.from_(bucket_name)  # Use admin client
        return bucket.remove([file_path])

    def list_files(self, bucket_name: str, folder_path: str = ""):
        """List files in a bucket folder."""
        bucket = self.admin_client.storage.from_(bucket_name)  # Use admin client
        return bucket.list(folder_path)


# Global Supabase instance
supabase = SupabaseConfig()

# Storage bucket names
BUCKETS = {
    "LECTURE_MATERIALS": "LECTURE_MATERIALS",
    "CURRICULUM_DOCS": "CURRICULUM_DOCS",
    "GENERATED_CONTENT": "GENERATED_CONTENT",
    "USER_UPLOADS": "USER_UPLOADS",
    "FEEDBACK_ATTACHMENTS": "feedback-attachments",
}
