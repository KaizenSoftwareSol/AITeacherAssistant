# utils/db.py

from supabase import create_client, Client
from settings import settings
from typing import Optional, Dict, Any, List
import json


class SupabaseDB:
    """Supabase database operations using Supabase client directly."""
    
    def __init__(self):
        self.client: Optional[Client] = None
        self.admin_client: Optional[Client] = None
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize Supabase clients."""
        if settings.SUPABASE_URL and settings.SUPABASE_ANON_KEY:
            try:
                self.client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
                print("✓ Supabase client initialized successfully")
            except Exception as e:
                print(f"⚠️  Warning: Could not initialize Supabase client: {e}")
                print("   Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables")
        else:
            print("⚠️  Warning: Supabase environment variables not set")
            print("   Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables")
        
        if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
            try:
                self.admin_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
                print("✓ Supabase admin client initialized successfully")
            except Exception as e:
                print(f"⚠️  Warning: Could not initialize Supabase admin client: {e}")
                print("   Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")
        else:
            print("⚠️  Warning: Supabase admin environment variables not set")
            print("   Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")
    
    def get_client(self) -> Client:
        """Get Supabase client for regular operations."""
        if self.client is None:
            raise RuntimeError("Supabase client not initialized. Please set SUPABASE_URL and SUPABASE_ANON_KEY environment variables.")
        return self.client
    
    def get_admin_client(self) -> Client:
        """Get Supabase admin client for admin operations."""
        if self.admin_client is None:
            raise RuntimeError("Supabase admin client not initialized. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.")
        return self.admin_client
    
    # User operations
    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user."""
        try:
            result = self.get_admin_client().table("users").insert(user_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating user: {e}")
            raise
    
    def get_user_by_id(self, user_id) -> Optional[Dict[str, Any]]:
        """Get user by ID (supports both int and UUID string)."""
        try:
            # Convert user_id to string to handle UUIDs
            result = self.get_client().table("users").select("*").eq("id", str(user_id)).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting user: {e}")
            return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email."""
        try:
            result = self.get_client().table("users").select("*").eq("email", email).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting user by email: {e}")
            return None
    
    def update_user(self, user_id, user_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update user (supports UUID strings)."""
        try:
            result = self.get_admin_client().table("users").update(user_data).eq("id", str(user_id)).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error updating user: {e}")
            return None
    
    def delete_user(self, user_id) -> bool:
        """Delete user (supports UUID strings)."""
        try:
            result = self.get_admin_client().table("users").delete().eq("id", str(user_id)).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting user: {e}")
            return False
    
    def get_users(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all users with pagination."""
        try:
            result = self.get_client().table("users").select("*").range(skip, skip + limit - 1).execute()
            return result.data
        except Exception as e:
            print(f"Error getting users: {e}")
            return []
    
    # Document operations
    def create_document(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new document."""
        try:
            result = self.get_admin_client().table("documents").insert(document_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating document: {e}")
            raise
    
    def get_document_by_id(self, document_id) -> Optional[Dict[str, Any]]:
        """Get document by ID (supports UUID strings)."""
        try:
            result = self.get_client().table("documents").select("*").eq("id", str(document_id)).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting document: {e}")
            return None
    
    def get_teacher_documents(self, teacher_id, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Get documents by teacher ID (supports UUID strings)."""
        try:
            result = self.get_client().table("documents").select("*").eq("teacher_id", str(teacher_id)).range(skip, skip + limit - 1).execute()
            return result.data
        except Exception as e:
            print(f"Error getting teacher documents: {e}")
            return []
    
    def update_document(self, document_id, document_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update document (supports UUID strings)."""
        try:
            result = self.get_admin_client().table("documents").update(document_data).eq("id", str(document_id)).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error updating document: {e}")
            return None
    
    def delete_document(self, document_id) -> bool:
        """Delete document (supports UUID strings)."""
        try:
            result = self.get_admin_client().table("documents").delete().eq("id", str(document_id)).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting document: {e}")
            return False
    
    # Generic operations
    def create_record(self, table_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a record in any table."""
        try:
            result = self.get_admin_client().table(table_name).insert(data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error creating record in {table_name}: {e}")
            raise
    
    def get_record_by_id(self, table_name: str, record_id) -> Optional[Dict[str, Any]]:
        """Get a record by ID from any table (supports UUID strings and ints)."""
        try:
            result = self.get_client().table(table_name).select("*").eq("id", str(record_id)).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting record from {table_name}: {e}")
            return None
    
    def get_records(self, table_name: str, filters: Dict[str, Any] = None, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Get records from any table with optional filters."""
        try:
            query = self.get_client().table(table_name).select("*")
            
            # Apply filters (convert values to strings for UUID support)
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, str(value) if value is not None else value)
            
            result = query.range(skip, skip + limit - 1).execute()
            return result.data
        except Exception as e:
            print(f"Error getting records from {table_name}: {e}")
            return []
    
    def update_record(self, table_name: str, record_id, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a record in any table (supports UUID strings and ints)."""
        try:
            result = self.get_admin_client().table(table_name).update(data).eq("id", str(record_id)).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error updating record in {table_name}: {e}")
            return None
    
    def delete_record(self, table_name: str, record_id) -> bool:
        """Delete a record from any table (supports UUID strings and ints)."""
        try:
            result = self.get_admin_client().table(table_name).delete().eq("id", str(record_id)).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting record from {table_name}: {e}")
            return False


# Global Supabase database instance
db = SupabaseDB()


async def create_db_and_tables():
    """Initialize database tables and admin user in Supabase."""
    if not db.admin_client:
        print("⚠️  Warning: Supabase admin client not initialized. Cannot create tables.")
        print("   Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables and restart the application.")
        return
    
    try:
        # Check if admin user exists
        admin_user = db.get_user_by_email("admin@admin.com")
        if not admin_user:
            # Create admin user
            from auth.models import UserCreate, UserRole
            from auth.service import AuthService
            
            admin_user_data = {
                "email": "admin@admin.com",
                "username": "admin",
                "hashed_password": AuthService.get_password_hash("123"),
                "role": UserRole.ADMIN.value,
                "first_name": "Admin",
                "last_name": "User",
                "is_active": True
            }
            
            db.create_user(admin_user_data)
            print("✓ Admin user created successfully in Supabase")
        else:
            print("✓ Admin user already exists in Supabase")
            
    except Exception as e:
        print(f"⚠️  Warning: Could not create admin user in Supabase: {e}")
        print("   Please create admin user manually in Supabase dashboard")


# Dependency for FastAPI
def get_db():
    """FastAPI Dependency to get Supabase database instance."""
    return db