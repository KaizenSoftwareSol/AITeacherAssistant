# services/cache_service.py
"""
High-performance caching service with in-memory LRU cache and optional Redis support.
Provides decorators and utilities for caching database queries and API responses.
"""

import asyncio
import hashlib
import json
import pickle
import time
from collections import OrderedDict
from datetime import datetime
from functools import wraps
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

from logger import logger

T = TypeVar("T")


class LRUCache:
    """Thread-safe LRU Cache with TTL support."""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        Initialize LRU cache.
        
        Args:
            max_size: Maximum number of items to store
            default_ttl: Default time-to-live in seconds
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache."""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            value, expiry = self._cache[key]
            
            # Check if expired
            if expiry < time.time():
                del self._cache[key]
                self._misses += 1
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set item in cache with TTL."""
        with self._lock:
            expiry = time.time() + (ttl or self.default_ttl)
            
            # Remove oldest items if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = (value, expiry)
            self._cache.move_to_end(key)
    
    def delete(self, key: str) -> bool:
        """Delete item from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern (simple prefix match)."""
        with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(pattern)]
            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)
    
    def clear(self) -> None:
        """Clear all items from cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def cleanup_expired(self) -> int:
        """Remove expired items. Returns count of removed items."""
        with self._lock:
            current_time = time.time()
            expired_keys = [
                k for k, (_, expiry) in self._cache.items() 
                if expiry < current_time
            ]
            for key in expired_keys:
                del self._cache[key]
            return len(expired_keys)
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.2f}%",
            }


class CacheService:
    """
    Centralized caching service with multiple cache regions.
    Supports both sync and async operations.
    """
    
    _instance: Optional["CacheService"] = None
    
    def __new__(cls):
        """Singleton pattern for cache service."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Initialize cache regions with different TTLs and sizes
        self.caches: Dict[str, LRUCache] = {
            # User-related caching (short TTL as user data changes frequently)
            "users": LRUCache(max_size=500, default_ttl=60),
            
            # Authentication caching (medium TTL for JWT validation results)
            "auth": LRUCache(max_size=1000, default_ttl=300),
            
            # Course data caching (longer TTL as courses change infrequently)
            "courses": LRUCache(max_size=200, default_ttl=600),
            
            # Lecture data caching
            "lectures": LRUCache(max_size=500, default_ttl=300),
            
            # Enrollment data caching
            "enrollments": LRUCache(max_size=1000, default_ttl=180),
            
            # Quiz and assessment caching
            "assessments": LRUCache(max_size=300, default_ttl=300),
            
            # Flashcard caching
            "flashcards": LRUCache(max_size=200, default_ttl=600),
            
            # General query results caching
            "queries": LRUCache(max_size=2000, default_ttl=120),
            
            # Teacher profile caching
            "teachers": LRUCache(max_size=200, default_ttl=300),
            
            # Student profile caching
            "students": LRUCache(max_size=500, default_ttl=300),
        }
        
        # Redis client (optional, lazy-loaded)
        self._redis = None
        self._use_redis = False
        
        self._initialized = True
        logger.info("CacheService initialized with in-memory LRU caches")
    
    async def try_init_redis(self, redis_url: Optional[str] = None) -> bool:
        """
        Try to initialize Redis connection.
        Falls back to in-memory cache if Redis is unavailable.
        """
        if not redis_url:
            import os
            redis_url = os.getenv("REDIS_URL")
        
        if not redis_url:
            logger.info("No REDIS_URL configured, using in-memory cache only")
            return False
        
        try:
            import redis.asyncio as redis
            
            self._redis = redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=False,
            )
            # Test connection
            await self._redis.ping()
            self._use_redis = True
            logger.info("Redis cache initialized successfully")
            return True
        except ImportError:
            logger.warning("redis package not installed, using in-memory cache")
            return False
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}, using in-memory cache")
            return False
    
    def _make_key(self, region: str, *args, **kwargs) -> str:
        """Generate a cache key from arguments."""
        key_parts = [region]
        key_parts.extend(str(arg) for arg in args)
        key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
        key_str = ":".join(key_parts)
        
        # Use hash for very long keys
        if len(key_str) > 200:
            return f"{region}:{hashlib.md5(key_str.encode()).hexdigest()}"
        return key_str
    
    def get(self, region: str, *args, **kwargs) -> Optional[Any]:
        """Get item from cache."""
        key = self._make_key(region, *args, **kwargs)
        cache = self.caches.get(region, self.caches["queries"])
        return cache.get(key)
    
    def set(
        self, 
        region: str, 
        value: Any, 
        *args, 
        ttl: Optional[int] = None, 
        **kwargs
    ) -> None:
        """Set item in cache."""
        key = self._make_key(region, *args, **kwargs)
        cache = self.caches.get(region, self.caches["queries"])
        cache.set(key, value, ttl)
    
    def delete(self, region: str, *args, **kwargs) -> bool:
        """Delete item from cache."""
        key = self._make_key(region, *args, **kwargs)
        cache = self.caches.get(region, self.caches["queries"])
        return cache.delete(key)
    
    def invalidate_user(self, user_id: str) -> None:
        """Invalidate all caches related to a user."""
        pattern = f"users:{user_id}"
        self.caches["users"].delete_pattern(pattern)
        self.caches["auth"].delete_pattern(pattern)
        logger.debug(f"Invalidated cache for user {user_id}")
    
    def invalidate_course(self, course_id: str) -> None:
        """Invalidate all caches related to a course."""
        self.caches["courses"].delete_pattern(f"courses:{course_id}")
        self.caches["lectures"].delete_pattern(f"lectures:course:{course_id}")
        self.caches["enrollments"].delete_pattern(f"enrollments:course:{course_id}")
        logger.debug(f"Invalidated cache for course {course_id}")
    
    def invalidate_lecture(self, lecture_id: str) -> None:
        """Invalidate all caches related to a lecture."""
        self.caches["lectures"].delete_pattern(f"lectures:{lecture_id}")
        self.caches["assessments"].delete_pattern(f"assessments:lecture:{lecture_id}")
        self.caches["flashcards"].delete_pattern(f"flashcards:{lecture_id}")
        logger.debug(f"Invalidated cache for lecture {lecture_id}")
    
    def invalidate_student(self, student_id: str) -> None:
        """Invalidate all caches related to a student."""
        self.caches["students"].delete_pattern(f"students:{student_id}")
        self.caches["enrollments"].delete_pattern(f"enrollments:student:{student_id}")
        logger.debug(f"Invalidated cache for student {student_id}")
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all cache regions."""
        return {name: cache.stats() for name, cache in self.caches.items()}
    
    def cleanup_all(self) -> Dict[str, int]:
        """Cleanup expired items from all caches."""
        return {name: cache.cleanup_expired() for name, cache in self.caches.items()}
    
    def clear_all(self) -> None:
        """Clear all caches."""
        for cache in self.caches.values():
            cache.clear()
        logger.info("All caches cleared")


# Global cache instance
cache = CacheService()


def cached(
    region: str = "queries",
    ttl: Optional[int] = None,
    key_prefix: str = "",
    include_args: bool = True,
):
    """
    Decorator for caching function results.
    
    Args:
        region: Cache region to use
        ttl: Time-to-live in seconds (None = use region default)
        key_prefix: Optional prefix for cache key
        include_args: Whether to include function arguments in cache key
    
    Example:
        @cached(region="users", ttl=60)
        def get_user(user_id: str):
            return db.get_user(user_id)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            # Build cache key
            if include_args:
                cache_key = cache._make_key(
                    region, 
                    key_prefix or func.__name__, 
                    *args, 
                    **kwargs
                )
            else:
                cache_key = cache._make_key(region, key_prefix or func.__name__)
            
            # Try to get from cache
            cached_value = cache.caches.get(region, cache.caches["queries"]).get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            if result is not None:
                cache.caches.get(region, cache.caches["queries"]).set(cache_key, result, ttl)
            
            return result
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            # Build cache key
            if include_args:
                cache_key = cache._make_key(
                    region, 
                    key_prefix or func.__name__, 
                    *args, 
                    **kwargs
                )
            else:
                cache_key = cache._make_key(region, key_prefix or func.__name__)
            
            # Try to get from cache
            cached_value = cache.caches.get(region, cache.caches["queries"]).get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            if result is not None:
                cache.caches.get(region, cache.caches["queries"]).set(cache_key, result, ttl)
            
            return result
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def cache_response(
    ttl: int = 60,
    vary_by: Optional[List[str]] = None,
    region: str = "queries",
):
    """
    Decorator for caching FastAPI route responses.
    
    Args:
        ttl: Time-to-live in seconds
        vary_by: List of request parameters to vary cache by
        region: Cache region to use
    
    Example:
        @router.get("/courses")
        @cache_response(ttl=120, vary_by=["user_id"])
        async def get_courses(user_id: str):
            return get_all_courses(user_id)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Build cache key from function name and vary_by parameters
            key_parts = [func.__name__]
            
            if vary_by:
                for param in vary_by:
                    if param in kwargs:
                        key_parts.append(f"{param}:{kwargs[param]}")
            
            cache_key = cache._make_key(region, *key_parts)
            
            # Try to get from cache
            cached_value = cache.caches.get(region, cache.caches["queries"]).get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            if result is not None:
                cache.caches.get(region, cache.caches["queries"]).set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    
    return decorator


class QueryCache:
    """
    Helper class for caching database query results.
    Provides a context manager pattern for complex caching scenarios.
    """
    
    def __init__(
        self, 
        region: str = "queries", 
        ttl: int = 120,
        key_parts: Optional[List[str]] = None
    ):
        self.region = region
        self.ttl = ttl
        self.key_parts = key_parts or []
        self._cache = cache
        self._key: Optional[str] = None
        self._hit = False
        self._value: Any = None
    
    def build_key(self, *args, **kwargs) -> "QueryCache":
        """Build cache key from arguments."""
        self._key = self._cache._make_key(
            self.region, 
            *self.key_parts, 
            *args, 
            **kwargs
        )
        return self
    
    def get(self) -> Optional[Any]:
        """Try to get value from cache."""
        if not self._key:
            return None
        self._value = self._cache.caches.get(
            self.region, 
            self._cache.caches["queries"]
        ).get(self._key)
        self._hit = self._value is not None
        return self._value
    
    def set(self, value: Any) -> None:
        """Set value in cache if not already cached."""
        if self._key and not self._hit:
            self._cache.caches.get(
                self.region, 
                self._cache.caches["queries"]
            ).set(self._key, value, self.ttl)
    
    @property
    def hit(self) -> bool:
        """Check if cache was hit."""
        return self._hit


# Background task for periodic cache cleanup
async def periodic_cache_cleanup(interval: int = 300):
    """
    Background task to periodically clean up expired cache entries.
    
    Args:
        interval: Cleanup interval in seconds
    """
    while True:
        await asyncio.sleep(interval)
        try:
            stats = cache.cleanup_all()
            total_cleaned = sum(stats.values())
            if total_cleaned > 0:
                logger.debug(f"Cache cleanup: removed {total_cleaned} expired entries")
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")

