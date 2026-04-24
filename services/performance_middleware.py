# services/performance_middleware.py
"""
Enhanced middleware for detailed performance monitoring and logging.
Tracks request time, database queries, and identifies bottlenecks.
"""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from logger import logger
from services.http_metrics import http_metrics
from services.query_logger import get_query_logger
from services.request_context import get_request_id


class DetailedPerformanceMiddleware(BaseHTTPMiddleware):
    """
    Enhanced middleware to track detailed performance metrics.
    Logs every request with:
    - Total response time
    - Database query count
    - Database query time
    - Percentage of time spent in database
    - Identified slow queries
    """
    
    # Endpoints to exclude from detailed logging
    EXCLUDED_PATHS = {
        "/api/v1/health",
        "/api/v1/healthz",
        "/api/v1/ready",
        "/api/v1/metrics",
        "/docs",
        "/openapi.json",
        "/favicon.ico",
    }
    
    # Threshold for warning logs (milliseconds)
    SLOW_REQUEST_THRESHOLD = 1000  # 1 second
    VERY_SLOW_REQUEST_THRESHOLD = 2000  # 2 seconds
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with detailed performance tracking."""
        
        # Skip logging for health checks and static files
        path = request.url.path
        should_log = not any(path.startswith(excluded) for excluded in self.EXCLUDED_PATHS)
        
        start_time = time.perf_counter()
        http_metrics.begin_request()
        
        # Get query logger
        query_logger = get_query_logger()
        query_logger.queries = []  # Reset for new request
        
        try:
            response = await call_next(request)
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            http_metrics.end_request(request.method, path, 500, duration_ms / 1000.0)
            if should_log:
                rid = get_request_id() or "-"
                logger.error(
                    f"REQUEST_ERROR: rid={rid} {request.method} {path} | "
                    f"Duration: {duration_ms:.0f}ms | Error: {str(e)}"
                )
            raise
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        status_code = response.status_code
        route = request.scope.get("route")
        metric_path = getattr(route, "path", path)
        http_metrics.end_request(request.method, metric_path, status_code, duration_ms / 1000.0)
        
        # Log performance metrics
        if should_log:
            self._log_performance(
                method=request.method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                query_logger=query_logger,
            )
        
        # Add timing header
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
        
        return response
    
    def _log_performance(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        query_logger,
    ):
        """Log performance metrics for a request."""
        rid = get_request_id() or "-"
        
        queries = query_logger.queries
        total_queries = len(queries)
        
        if total_queries == 0:
            # No database queries
            if duration_ms > self.SLOW_REQUEST_THRESHOLD:
                logger.warning(
                    f"SLOW_REQUEST_NO_DB: rid={rid} {method} {path} | "
                    f"Duration: {duration_ms:.0f}ms | Status: {status_code} | "
                    f"Reason: Likely application logic or external API calls"
                )
            return
        
        # Calculate database metrics
        total_query_ms = sum(q["duration_ms"] for q in queries if not q.get("error"))
        db_time_percent = (total_query_ms / duration_ms * 100) if duration_ms > 0 else 0
        other_time_ms = duration_ms - total_query_ms
        
        # Find slow queries
        slow_queries = [q for q in queries if q["duration_ms"] > 100]
        very_slow_queries = [q for q in queries if q["duration_ms"] > 500]
        errored_queries = [q for q in queries if q.get("error")]
        
        # Build query summary
        query_types = {}
        for q in queries:
            key = f"{q['operation']} {q['table']}"
            if key not in query_types:
                query_types[key] = {"count": 0, "total_ms": 0, "rows": 0}
            query_types[key]["count"] += 1
            query_types[key]["total_ms"] += q["duration_ms"]
            query_types[key]["rows"] += q["rows_count"]
        
        query_summary = " | ".join(
            f"{k}(n={v['count']}, {v['total_ms']:.0f}ms, r={v['rows']})"
            for k, v in sorted(query_types.items())
        )
        
        # Determine log level and message
        if status_code >= 400:
            # Error responses
            logger.warning(
                f"REQUEST_ERROR: rid={rid} {method} {path} | "
                f"Status: {status_code} | Duration: {duration_ms:.0f}ms | "
                f"Queries: {total_queries} ({total_query_ms:.0f}ms) | "
                f"{query_summary}"
            )
        
        elif duration_ms > self.VERY_SLOW_REQUEST_THRESHOLD:
            # Very slow requests (> 2 seconds)
            logger.warning(
                f"VERY_SLOW_REQUEST: rid={rid} {method} {path} | "
                f"Duration: {duration_ms:.0f}ms | "
                f"DB Time: {total_query_ms:.0f}ms ({db_time_percent:.1f}%) | "
                f"Other: {other_time_ms:.0f}ms | "
                f"Queries: {total_queries} "
                f"({len(very_slow_queries)} very slow, {len(slow_queries)} slow, "
                f"{len(errored_queries)} errors) | "
                f"{query_summary}"
            )
            
            # Log individual very slow queries
            for i, q in enumerate(very_slow_queries, 1):
                logger.warning(
                    f"  ├─ VERY_SLOW_QUERY[{i}]: {q['operation']} on {q['table']} | "
                    f"Time: {q['duration_ms']:.0f}ms | Rows: {q['rows_count']} | "
                    f"Filters: {self._format_filters(q['filters'])}"
                )
        
        elif duration_ms > self.SLOW_REQUEST_THRESHOLD:
            # Slow requests (> 1 second)
            logger.warning(
                f"SLOW_REQUEST: rid={rid} {method} {path} | "
                f"Duration: {duration_ms:.0f}ms | "
                f"DB Time: {total_query_ms:.0f}ms ({db_time_percent:.1f}%) | "
                f"Queries: {total_queries} "
                f"({len(slow_queries)} slow, {len(errored_queries)} errors) | "
                f"{query_summary}"
            )
            
            # Log individual slow queries
            for i, q in enumerate(slow_queries, 1):
                if q["duration_ms"] > 100:
                    logger.info(
                        f"  ├─ SLOW_QUERY[{i}]: {q['operation']} on {q['table']} | "
                        f"Time: {q['duration_ms']:.0f}ms | Rows: {q['rows_count']}"
                    )
        
        elif len(very_slow_queries) > 0 or len(errored_queries) > 0:
            # Request OK but has slow or errored queries
            logger.info(
                f"REQUEST_WITH_ISSUES: rid={rid} {method} {path} | "
                f"Duration: {duration_ms:.0f}ms | "
                f"Queries: {total_queries} "
                f"({len(very_slow_queries)} very slow, {len(slow_queries)} slow) | "
                f"{query_summary}"
            )
        
        else:
            # Normal request
            logger.debug(
                f"REQUEST: rid={rid} {method} {path} | "
                f"Duration: {duration_ms:.0f}ms | "
                f"Queries: {total_queries} ({total_query_ms:.0f}ms) | "
                f"{query_summary}"
            )
    
    def _format_filters(self, filters: dict) -> str:
        """Format filters for display."""
        if not filters:
            return "none"
        
        parts = []
        for k, v in filters.items():
            if isinstance(v, str) and len(v) > 20:
                v = v[:17] + "..."
            parts.append(f"{k}={v}")
        
        return " AND ".join(parts)


def setup_performance_middleware(app):
    """
    Setup detailed performance monitoring middleware.
    
    Usage:
        from services.performance_middleware import setup_performance_middleware
        setup_performance_middleware(app)
    """
    # Add detailed performance middleware
    app.add_middleware(DetailedPerformanceMiddleware)
