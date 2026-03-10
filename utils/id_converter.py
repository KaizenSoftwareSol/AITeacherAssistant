# utils/id_converter.py
"""
Utility functions for converting between UUID and integer IDs.

After migration, the database will use integer IDs internally for performance,
but external APIs will continue to use UUIDs for security and compatibility.
"""

from typing import Optional, Union, Dict, List
from utils.db import get_db


class IDConverter:
    """Helper class for UUID <-> integer ID conversion."""
    
    # Cache for UUID -> integer mappings
    _uuid_to_int_cache: Dict[str, Dict[str, int]] = {}
    _int_to_uuid_cache: Dict[str, Dict[int, str]] = {}
    
    @staticmethod
    def _get_cache_key(table_name: str) -> str:
        """Get cache key for table."""
        return f"id_mapping:{table_name}"
    
    @staticmethod
    async def uuid_to_int(db, table_name: str, uuid: str) -> Optional[int]:
        """
        Convert UUID to integer ID for a given table.
        
        Args:
            db: Database instance
            table_name: Name of the table
            uuid: UUID string to convert
            
        Returns:
            Integer ID or None if not found
        """
        if not uuid:
            return None
        
        # Check cache first
        cache_key = IDConverter._get_cache_key(table_name)
        if cache_key in IDConverter._uuid_to_int_cache:
            if uuid in IDConverter._uuid_to_int_cache[cache_key]:
                return IDConverter._uuid_to_int_cache[cache_key][uuid]
        
        try:
            # Query database
            result = (
                db.get_admin_client().table(table_name)
                .select("id")
                .eq("uuid", uuid)
                .limit(1)
                .execute()
            )
            
            if result.data and len(result.data) > 0:
                int_id = result.data[0].get("id")
                
                # Cache the result
                if cache_key not in IDConverter._uuid_to_int_cache:
                    IDConverter._uuid_to_int_cache[cache_key] = {}
                IDConverter._uuid_to_int_cache[cache_key][uuid] = int_id
                
                # Also cache reverse mapping
                if cache_key not in IDConverter._int_to_uuid_cache:
                    IDConverter._int_to_uuid_cache[cache_key] = {}
                IDConverter._int_to_uuid_cache[cache_key][int_id] = uuid
                
                return int_id
            
            return None
        except Exception as e:
            print(f"Error converting UUID to int for {table_name}: {e}")
            return None
    
    @staticmethod
    async def int_to_uuid(db, table_name: str, int_id: int) -> Optional[str]:
        """
        Convert integer ID to UUID for a given table.
        
        Args:
            db: Database instance
            table_name: Name of the table
            int_id: Integer ID to convert
            
        Returns:
            UUID string or None if not found
        """
        if int_id is None:
            return None
        
        # Check cache first
        cache_key = IDConverter._get_cache_key(table_name)
        if cache_key in IDConverter._int_to_uuid_cache:
            if int_id in IDConverter._int_to_uuid_cache[cache_key]:
                return IDConverter._int_to_uuid_cache[cache_key][int_id]
        
        try:
            # Query database
            result = (
                db.get_admin_client().table(table_name)
                .select("uuid")
                .eq("id", int_id)
                .limit(1)
                .execute()
            )
            
            if result.data and len(result.data) > 0:
                uuid = result.data[0].get("uuid")
                
                # Cache the result
                if cache_key not in IDConverter._int_to_uuid_cache:
                    IDConverter._int_to_uuid_cache[cache_key] = {}
                IDConverter._int_to_uuid_cache[cache_key][int_id] = uuid
                
                # Also cache reverse mapping
                if cache_key not in IDConverter._uuid_to_int_cache:
                    IDConverter._uuid_to_int_cache[cache_key] = {}
                IDConverter._uuid_to_int_cache[cache_key][uuid] = int_id
                
                return uuid
            
            return None
        except Exception as e:
            print(f"Error converting int to UUID for {table_name}: {e}")
            return None
    
    @staticmethod
    async def batch_uuid_to_int(db, table_name: str, uuids: List[str]) -> Dict[str, int]:
        """
        Batch convert UUIDs to integer IDs.
        
        Args:
            db: Database instance
            table_name: Name of the table
            uuids: List of UUID strings
            
        Returns:
            Dictionary mapping UUID -> integer ID
        """
        if not uuids:
            return {}
        
        result = {}
        uncached_uuids = []
        
        # Check cache first
        cache_key = IDConverter._get_cache_key(table_name)
        if cache_key in IDConverter._uuid_to_int_cache:
            for uuid in uuids:
                if uuid in IDConverter._uuid_to_int_cache[cache_key]:
                    result[uuid] = IDConverter._uuid_to_int_cache[cache_key][uuid]
                else:
                    uncached_uuids.append(uuid)
        else:
            uncached_uuids = uuids
        
        # Query uncached UUIDs
        if uncached_uuids:
            try:
                query_result = (
                    db.get_admin_client().table(table_name)
                    .select("id, uuid")
                    .in_("uuid", uncached_uuids)
                    .execute()
                )
                
                # Initialize cache if needed
                if cache_key not in IDConverter._uuid_to_int_cache:
                    IDConverter._uuid_to_int_cache[cache_key] = {}
                if cache_key not in IDConverter._int_to_uuid_cache:
                    IDConverter._int_to_uuid_cache[cache_key] = {}
                
                for row in query_result.data or []:
                    uuid_val = row.get("uuid")
                    int_id = row.get("id")
                    if uuid_val and int_id is not None:
                        result[uuid_val] = int_id
                        IDConverter._uuid_to_int_cache[cache_key][uuid_val] = int_id
                        IDConverter._int_to_uuid_cache[cache_key][int_id] = uuid_val
            except Exception as e:
                print(f"Error batch converting UUIDs to int for {table_name}: {e}")
        
        return result
    
    @staticmethod
    def normalize_id(id_value: Union[str, int, None]) -> Optional[Union[str, int]]:
        """
        Normalize ID value - accepts both UUID strings and integer IDs.
        During migration period, we need to handle both.
        
        Args:
            id_value: UUID string, integer ID, or None
            
        Returns:
            Normalized ID value
        """
        if id_value is None:
            return None
        
        # If it's already an integer, return as-is
        if isinstance(id_value, int):
            return id_value
        
        # If it's a string, try to determine if it's UUID or integer
        if isinstance(id_value, str):
            # Try to parse as integer first
            try:
                return int(id_value)
            except ValueError:
                # Not an integer, assume it's a UUID
                return id_value
        
        return id_value
    
    @staticmethod
    def is_uuid(value: Union[str, int, None]) -> bool:
        """
        Check if a value looks like a UUID.
        
        Args:
            value: Value to check
            
        Returns:
            True if value looks like a UUID string
        """
        if not isinstance(value, str):
            return False
        
        # UUID format: 8-4-4-4-12 hex characters
        import re
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            re.IGNORECASE
        )
        return bool(uuid_pattern.match(value))
    
    @staticmethod
    def is_int(value: Union[str, int, None]) -> bool:
        """
        Check if a value is an integer ID.
        
        Args:
            value: Value to check
            
        Returns:
            True if value is an integer
        """
        if isinstance(value, int):
            return True
        
        if isinstance(value, str):
            try:
                int(value)
                return True
            except ValueError:
                return False
        
        return False
