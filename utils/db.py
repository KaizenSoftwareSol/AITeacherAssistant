# utils/db.py

import json
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from services.cache_service import cache, cached
from settings import settings


class SupabaseDB:
    """Supabase database operations using Supabase client directly with caching support."""

    def __init__(self):
        self.client: Optional[Client] = None
        self.admin_client: Optional[Client] = None
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize Supabase clients."""
        if settings.SUPABASE_URL and settings.SUPABASE_ANON_KEY:
            try:
                self.client = create_client(
                    settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY
                )
                print("✓ Supabase client initialized successfully")
            except Exception as e:
                print(f"⚠️  Warning: Could not initialize Supabase client: {e}")
                print(
                    "   Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables"
                )
        else:
            print("⚠️  Warning: Supabase environment variables not set")
            print(
                "   Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables"
            )

        if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
            try:
                self.admin_client = create_client(
                    settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
                )
                print("✓ Supabase admin client initialized successfully")
            except Exception as e:
                print(f"⚠️  Warning: Could not initialize Supabase admin client: {e}")
                print(
                    "   Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables"
                )
        else:
            print("⚠️  Warning: Supabase admin environment variables not set")
            print(
                "   Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables"
            )

    def get_client(self) -> Client:
        """Get Supabase client for regular operations."""
        if self.client is None:
            raise RuntimeError(
                "Supabase client not initialized. Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables."
            )
        return self.client

    def get_admin_client(self) -> Client:
        """Get Supabase admin client for admin operations."""
        if self.admin_client is None:
            raise RuntimeError(
                "Supabase admin client not initialized. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables."
            )
        return self.admin_client

    # User operations with caching
    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user."""
        try:
            result = self.get_admin_client().table("users").insert(user_data).execute()
            user = result.data[0] if result.data else None
            
            # Invalidate any cached user data
            if user:
                cache.invalidate_user(str(user.get("id")))
            
            return user
        except Exception as e:
            print(f"Error creating user: {e}")
            raise

    def get_user_by_id(self, user_id, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """Get user by ID (supports both int and UUID string) with caching."""
        try:
            user_id_str = str(user_id)
            
            # Check cache first
            if use_cache:
                cached_user = cache.get("users", "id", user_id_str)
                if cached_user is not None:
                    return cached_user if cached_user != "__NONE__" else None
            
            # Fetch from database
            result = (
                self.get_admin_client()
                .table("users")
                .select("*")
                .eq("id", user_id_str)
                .execute()
            )
            user = result.data[0] if result.data else None
            
            # Cache result
            if use_cache:
                cache.set("users", user if user else "__NONE__", "id", user_id_str, ttl=60)
            
            return user
        except Exception as e:
            print(f"Error getting user: {e}")
            return None

    def get_user_by_email(self, email: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """Get user by email with caching."""
        try:
            # Check cache first
            if use_cache:
                cached_user = cache.get("users", "email", email)
                if cached_user is not None:
                    return cached_user if cached_user != "__NONE__" else None
            
            result = (
                self.get_admin_client()
                .table("users")
                .select("*")
                .eq("email", email)
                .execute()
            )
            user = result.data[0] if result.data else None
            
            # Cache result
            if use_cache:
                cache.set("users", user if user else "__NONE__", "email", email, ttl=60)
            
            return user
        except Exception as e:
            print(f"Error getting user by email: {e}")
            return None

    def update_user(
        self, user_id, user_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update user (supports UUID strings)."""
        try:
            result = (
                self.get_admin_client()
                .table("users")
                .update(user_data)
                .eq("id", str(user_id))
                .execute()
            )
            user = result.data[0] if result.data else None
            
            # Invalidate cache
            cache.invalidate_user(str(user_id))
            
            return user
        except Exception as e:
            print(f"Error updating user: {e}")
            return None

    def delete_user(self, user_id) -> bool:
        """Delete user (supports UUID strings)."""
        try:
            result = (
                self.get_admin_client()
                .table("users")
                .delete()
                .eq("id", str(user_id))
                .execute()
            )
            
            # Invalidate cache
            cache.invalidate_user(str(user_id))
            
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting user: {e}")
            return False

    def get_users(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all users with pagination."""
        try:
            result = (
                self.get_admin_client()
                .table("users")
                .select("*")
                .range(skip, skip + limit - 1)
                .execute()
            )
            return result.data
        except Exception as e:
            print(f"Error getting users: {e}")
            return []

    # Document operations with caching
    def create_document(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new document."""
        try:
            result = (
                self.get_admin_client()
                .table("documents")
                .insert(document_data)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating document: {e}")
            raise

    def get_document_by_id(self, document_id, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """Get document by ID (supports UUID strings) with caching."""
        try:
            doc_id_str = str(document_id)
            
            # Check cache first
            if use_cache:
                cached_doc = cache.get("queries", "document", doc_id_str)
                if cached_doc is not None:
                    return cached_doc if cached_doc != "__NONE__" else None
            
            result = (
                self.get_admin_client()
                .table("documents")
                .select("*")
                .eq("id", doc_id_str)
                .execute()
            )
            doc = result.data[0] if result.data else None
            
            # Cache result
            if use_cache:
                cache.set("queries", doc if doc else "__NONE__", "document", doc_id_str, ttl=300)
            
            return doc
        except Exception as e:
            print(f"Error getting document: {e}")
            return None

    def get_teacher_documents(
        self, teacher_id, skip: int = 0, limit: int = 100, use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Get documents by teacher ID (supports UUID strings) with caching."""
        try:
            teacher_id_str = str(teacher_id)
            cache_key = f"teacher_docs:{teacher_id_str}:{skip}:{limit}"
            
            # Check cache first
            if use_cache:
                cached_docs = cache.get("queries", cache_key)
                if cached_docs is not None:
                    return cached_docs
            
            result = (
                self.get_admin_client()
                .table("documents")
                .select("*")
                .eq("teacher_id", teacher_id_str)
                .range(skip, skip + limit - 1)
                .execute()
            )
            docs = result.data
            
            # Cache result
            if use_cache:
                cache.set("queries", docs, cache_key, ttl=120)
            
            return docs
        except Exception as e:
            print(f"Error getting teacher documents: {e}")
            return []

    def update_document(
        self, document_id, document_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update document (supports UUID strings)."""
        try:
            result = (
                self.get_admin_client()
                .table("documents")
                .update(document_data)
                .eq("id", str(document_id))
                .execute()
            )
            
            # Invalidate cache
            cache.delete("queries", "document", str(document_id))
            
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error updating document: {e}")
            return None

    def delete_document(self, document_id) -> bool:
        """Delete document (supports UUID strings)."""
        try:
            result = (
                self.get_admin_client()
                .table("documents")
                .delete()
                .eq("id", str(document_id))
                .execute()
            )
            
            # Invalidate cache
            cache.delete("queries", "document", str(document_id))
            
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting document: {e}")
            return False

    # Generic operations with caching support
    def create_record(self, table_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a record in any table."""
        try:
            result = self.get_admin_client().table(table_name).insert(data).execute()
            record = result.data[0] if result.data else None
            
            # Invalidate related caches based on table
            if record:
                self._invalidate_table_cache(table_name, record)
            
            return record
        except Exception as e:
            print(f"Error creating record in {table_name}: {e}")
            raise

    def get_record_by_id(
        self, table_name: str, record_id, use_cache: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Get a record by ID from any table (supports UUID strings and ints) with caching."""
        try:
            record_id_str = str(record_id)
            cache_key = f"{table_name}:{record_id_str}"
            
            # Check cache first
            if use_cache:
                cached_record = cache.get("queries", cache_key)
                if cached_record is not None:
                    return cached_record if cached_record != "__NONE__" else None
            
            result = (
                self.get_admin_client()
                .table(table_name)
                .select("*")
                .eq("id", record_id_str)
                .execute()
            )
            record = result.data[0] if result.data else None
            
            # Cache result
            if use_cache:
                cache.set("queries", record if record else "__NONE__", cache_key, ttl=120)
            
            return record
        except Exception as e:
            print(f"Error getting record from {table_name}: {e}")
            return None

    def get_records(
        self,
        table_name: str,
        filters: Dict[str, Any] = None,
        skip: int = 0,
        limit: int = 100,
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get records from any table with optional filters and caching."""
        try:
            # Build cache key from filters
            filter_str = json.dumps(filters, sort_keys=True) if filters else "none"
            cache_key = f"{table_name}:list:{filter_str}:{skip}:{limit}"
            
            # Check cache first
            if use_cache:
                cached_records = cache.get("queries", cache_key)
                if cached_records is not None:
                    return cached_records
            
            query = self.get_admin_client().table(table_name).select("*")

            # Apply filters (convert values to strings for UUID support)
            if filters:
                for key, value in filters.items():
                    if value is None:
                        # Use .is_() for NULL checks
                        query = query.is_(key, "null")
                    else:
                        # Convert to string for UUID support
                        query = query.eq(key, str(value))

            result = query.range(skip, skip + limit - 1).execute()
            records = result.data
            
            # Cache result
            if use_cache:
                cache.set("queries", records, cache_key, ttl=60)
            
            return records
        except Exception as e:
            print(f"Error getting records from {table_name}: {e}")
            return []

    def update_record(
        self, table_name: str, record_id, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a record in any table (supports UUID strings and ints)."""
        try:
            result = (
                self.get_admin_client()
                .table(table_name)
                .update(data)
                .eq("id", str(record_id))
                .execute()
            )
            record = result.data[0] if result.data else None
            
            # Invalidate cache
            cache.delete("queries", f"{table_name}:{str(record_id)}")
            if record:
                self._invalidate_table_cache(table_name, record)
            
            return record
        except Exception as e:
            print(f"Error updating record in {table_name}: {e}")
            return None

    def delete_record(self, table_name: str, record_id) -> bool:
        """Delete a record from any table (supports UUID strings and ints)."""
        try:
            result = (
                self.get_admin_client()
                .table(table_name)
                .delete()
                .eq("id", str(record_id))
                .execute()
            )
            
            # Invalidate cache
            cache.delete("queries", f"{table_name}:{str(record_id)}")
            
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting record from {table_name}: {e}")
            return False
    
    def _invalidate_table_cache(self, table_name: str, record: Dict[str, Any]) -> None:
        """Invalidate caches based on table name and record data."""
        record_id = record.get("id")
        
        if table_name == "course":
            cache.invalidate_course(str(record_id))
        elif table_name == "lecture":
            cache.invalidate_lecture(str(record_id))
            if record.get("course_id"):
                cache.invalidate_course(str(record.get("course_id")))
        elif table_name == "enrollment":
            if record.get("student_id"):
                cache.invalidate_student(str(record.get("student_id")))
            if record.get("course_id"):
                cache.invalidate_course(str(record.get("course_id")))
        elif table_name == "student":
            cache.invalidate_student(str(record_id))
        elif table_name == "users":
            cache.invalidate_user(str(record_id))
    
    # Optimized batch operations
    def get_records_batch(
        self,
        table_name: str,
        ids: List[str],
        use_cache: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get multiple records by IDs in a single query.
        Returns a dict mapping id -> record for easy lookup.
        """
        if not ids:
            return {}
        
        try:
            # Check cache for each ID first
            result_map = {}
            missing_ids = []
            
            if use_cache:
                for record_id in ids:
                    cache_key = f"{table_name}:{str(record_id)}"
                    cached = cache.get("queries", cache_key)
                    if cached is not None and cached != "__NONE__":
                        result_map[str(record_id)] = cached
                    else:
                        missing_ids.append(str(record_id))
            else:
                missing_ids = [str(id) for id in ids]
            
            # Fetch missing records in a single query
            if missing_ids:
                result = (
                    self.get_admin_client()
                    .table(table_name)
                    .select("*")
                    .in_("id", missing_ids)
                    .execute()
                )
                
                for record in result.data:
                    record_id = str(record.get("id"))
                    result_map[record_id] = record
                    
                    # Cache each record
                    if use_cache:
                        cache.set("queries", record, f"{table_name}:{record_id}", ttl=120)
            
            return result_map
        except Exception as e:
            print(f"Error getting batch records from {table_name}: {e}")
            return {}


# Global Supabase database instance
db = SupabaseDB()


async def create_db_and_tables():
    """Initialize database tables in Supabase."""
    if not db.admin_client:
        print(
            "⚠️  Warning: Supabase admin client not initialized. Cannot create tables."
        )
        print(
            "   Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables and restart the application."
        )
        return

    # Note: Default admin user creation removed
    # Admins should be created through the System User onboarding process
    # or manually via the Supabase dashboard with a valid university_id
    print("✓ Database initialization complete")
    print("   Note: Use System User to create universities and admins, or create manually in Supabase")


# Dependency for FastAPI
def get_db():
    """FastAPI Dependency to get Supabase database instance."""
    return db
