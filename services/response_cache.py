# services/response_cache.py
"""
FastAPI middleware for response caching and request optimization.
"""

import hashlib
import time
from typing import Callable, Optional, Set

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from logger import logger
from services.cache_service import cache


class ResponseCacheMiddleware(BaseHTTPMiddleware):
    """
    Middleware to cache GET responses for improved performance.
    
    Only caches GET requests with specific path patterns.
    Excludes authentication endpoints and endpoints with sensitive data.
    """
    
    # Paths that should be cached (prefix matching)
    CACHEABLE_PATHS: Set[str] = {
        "/api/v1/student/my-courses",
        "/api/v1/courses",
    }
    
    # Paths that should never be cached
    EXCLUDED_PATHS: Set[str] = {
        "/api/v1/auth",
        "/api/v1/healthz",
        "/api/v1/health",
        "/api/v1/ready",
        "/api/v1/metrics",
        "/api/v1/cache",
    }
    
    # Default TTL in seconds
    DEFAULT_TTL: int = 60
    
    # Path-specific TTLs
    PATH_TTLS = {
        "/api/v1/student/my-courses": 120,
        "/api/v1/courses": 120,
    }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with caching logic."""
        
        # Only cache GET requests
        if request.method != "GET":
            return await call_next(request)
        
        path = request.url.path
        
        # Check if path should be excluded
        for excluded in self.EXCLUDED_PATHS:
            if path.startswith(excluded):
                return await call_next(request)
        
        # Check if path should be cached
        should_cache = False
        for cacheable in self.CACHEABLE_PATHS:
            if path.startswith(cacheable):
                should_cache = True
                break
        
        if not should_cache:
            return await call_next(request)
        
        # Build cache key from path, query params, and authorization
        cache_key = self._build_cache_key(request)
        
        # Try to get from cache
        cached_response = cache.get("queries", f"response:{cache_key}")
        if cached_response is not None:
            return JSONResponse(
                content=cached_response["content"],
                status_code=cached_response["status_code"],
                headers={"X-Cache": "HIT"},
            )
        
        # Execute request
        response = await call_next(request)
        
        # Only cache successful responses
        if 200 <= response.status_code < 300:
            # Read response body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            
            # Get TTL for this path
            ttl = self.DEFAULT_TTL
            for path_prefix, path_ttl in self.PATH_TTLS.items():
                if path.startswith(path_prefix):
                    ttl = path_ttl
                    break
            
            try:
                import json
                content = json.loads(body.decode())
                
                # Cache the response
                cache.set(
                    "queries",
                    {
                        "content": content,
                        "status_code": response.status_code,
                    },
                    f"response:{cache_key}",
                    ttl=ttl,
                )
                
                # Return new response with cache miss header
                return JSONResponse(
                    content=content,
                    status_code=response.status_code,
                    headers={"X-Cache": "MISS"},
                )
            except Exception:
                # If we can't parse as JSON, return original response
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )
        
        return response
    
    def _build_cache_key(self, request: Request) -> str:
        """Build a unique cache key for the request."""
        # Include path
        key_parts = [request.url.path]
        
        # Include sorted query params
        if request.query_params:
            sorted_params = sorted(request.query_params.items())
            key_parts.append(str(sorted_params))
        
        # Include authorization header hash (to separate user-specific responses)
        auth_header = request.headers.get("authorization", "")
        if auth_header:
            # Hash the token for privacy
            auth_hash = hashlib.md5(auth_header.encode()).hexdigest()[:16]
            key_parts.append(auth_hash)
        
        # Create final key
        key_str = ":".join(key_parts)
        
        # Hash if too long
        if len(key_str) > 200:
            return hashlib.md5(key_str.encode()).hexdigest()
        
        return key_str


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log request timing for performance monitoring.
    """
    
    # Threshold in seconds for slow request logging
    SLOW_REQUEST_THRESHOLD: float = 1.0
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with timing."""
        start_time = time.time()
        
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Add timing header
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
        
        # Log slow requests
        if duration > self.SLOW_REQUEST_THRESHOLD:
            logger.warning(
                f"Slow request: {request.method} {request.url.path} "
                f"took {duration:.3f}s"
            )
        
        return response


def setup_cache_middleware(app):
    """
    Setup caching middleware for the FastAPI application.
    
    Usage:
        from services.response_cache import setup_cache_middleware
        setup_cache_middleware(app)
    """
    # Add timing middleware first (outermost)
    app.add_middleware(RequestTimingMiddleware)
    
    # Add response caching middleware
    # Note: Commented out by default as it can cause issues with dynamic responses
    # Uncomment to enable response-level caching
    # app.add_middleware(ResponseCacheMiddleware)
    
    logger.info("Cache middleware configured")

