# services/performance_monitor.py
"""
Performance monitoring and profiling for API endpoints and database queries.

Provides decorators and utilities to track:
- Request execution time
- Database query execution time
- Query count per request
- Memory usage
- Bottlenecks
"""

import functools
import sys
import time
import tracemalloc
from typing import Any, Callable, Dict, Optional

from logger import logger


class QueryTimer:
    """Context manager to track query execution time."""
    
    def __init__(self, query_name: str, threshold_ms: float = 100):
        """
        Initialize query timer.
        
        Args:
            query_name: Name/description of the query
            threshold_ms: Log warning if query exceeds this time (milliseconds)
        """
        self.query_name = query_name
        self.threshold_ms = threshold_ms
        self.start_time = None
        self.duration_ms = 0
    
    def __enter__(self):
        """Start timing."""
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End timing and log results."""
        if self.start_time:
            self.duration_ms = (time.perf_counter() - self.start_time) * 1000
            
            if self.duration_ms > self.threshold_ms:
                logger.warning(
                    f"SLOW_QUERY: {self.query_name} took {self.duration_ms:.2f}ms "
                    f"(threshold: {self.threshold_ms}ms)"
                )
            else:
                logger.debug(f"QUERY: {self.query_name} took {self.duration_ms:.2f}ms")


class PerformanceMetrics:
    """Track performance metrics for a request."""
    
    def __init__(self):
        """Initialize metrics container."""
        self.request_start = time.perf_counter()
        self.queries: Dict[str, Dict[str, Any]] = {}
        self.query_order = []
        self.total_queries = 0
        self.memory_start = None
        self.memory_peak = None
        
        try:
            tracemalloc.start()
            self.memory_start = tracemalloc.get_traced_memory()[0]
        except Exception:
            pass
    
    def add_query(
        self,
        query_name: str,
        duration_ms: float,
        query_type: str = "SELECT",
        rows_affected: Optional[int] = None,
    ):
        """
        Record a query execution.
        
        Args:
            query_name: Name/description of query
            duration_ms: Execution time in milliseconds
            query_type: Type of query (SELECT, INSERT, UPDATE, DELETE)
            rows_affected: Number of rows affected
        """
        self.total_queries += 1
        query_id = f"{query_name}_{self.total_queries}"
        
        self.queries[query_id] = {
            "name": query_name,
            "type": query_type,
            "duration_ms": duration_ms,
            "rows_affected": rows_affected,
            "order": self.total_queries,
        }
        self.query_order.append(query_id)
    
    def get_request_duration_ms(self) -> float:
        """Get total request duration in milliseconds."""
        return (time.perf_counter() - self.request_start) * 1000
    
    def get_memory_used_mb(self) -> float:
        """Get estimated memory used in MB."""
        if not self.memory_start:
            return 0
        try:
            current = tracemalloc.get_traced_memory()[0]
            return (current - self.memory_start) / 1024 / 1024
        except Exception:
            return 0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        total_query_time = sum(q["duration_ms"] for q in self.queries.values())
        
        return {
            "total_duration_ms": self.get_request_duration_ms(),
            "total_queries": self.total_queries,
            "total_query_time_ms": total_query_time,
            "time_in_db_percent": (total_query_time / self.get_request_duration_ms() * 100)
            if self.get_request_duration_ms() > 0 else 0,
            "other_time_ms": self.get_request_duration_ms() - total_query_time,
            "memory_used_mb": self.get_memory_used_mb(),
            "queries": self.queries,
            "query_order": self.query_order,
        }
    
    def log_summary(self, endpoint: str, status_code: int = 200):
        """Log a formatted summary of metrics."""
        summary = self.get_summary()
        
        if summary["total_duration_ms"] > 1000:  # Log slow requests
            logger.warning(
                f"ENDPOINT_PERF: {endpoint} | "
                f"Duration: {summary['total_duration_ms']:.0f}ms | "
                f"Queries: {summary['total_queries']} | "
                f"DB Time: {summary['total_query_time_ms']:.0f}ms "
                f"({summary['time_in_db_percent']:.1f}%) | "
                f"Memory: {summary['memory_used_mb']:.2f}MB | "
                f"Status: {status_code}"
            )
        else:
            logger.info(
                f"ENDPOINT_PERF: {endpoint} | "
                f"Duration: {summary['total_duration_ms']:.0f}ms | "
                f"Queries: {summary['total_queries']} | "
                f"Status: {status_code}"
            )


# Global metrics storage (in production, use request context)
_current_metrics: Dict[int, PerformanceMetrics] = {}


def get_current_metrics() -> Optional[PerformanceMetrics]:
    """Get metrics for current request (thread-safe)."""
    thread_id = id(__import__("threading").current_thread())
    return _current_metrics.get(thread_id)


def set_current_metrics(metrics: PerformanceMetrics):
    """Set metrics for current request (thread-safe)."""
    thread_id = id(__import__("threading").current_thread())
    _current_metrics[thread_id] = metrics


def clear_current_metrics():
    """Clear metrics for current request."""
    thread_id = id(__import__("threading").current_thread())
    if thread_id in _current_metrics:
        del _current_metrics[thread_id]


def track_query(query_name: str, query_type: str = "SELECT", rows_affected: Optional[int] = None):
    """
    Decorator to track query execution time.
    
    Usage:
        @track_query("fetch_user_by_id")
        def get_user(user_id):
            ...
    
    Or use as context manager:
        with QueryTimer("complex_query", threshold_ms=500) as timer:
            # execute query
            ...
        metrics = get_current_metrics()
        if metrics:
            metrics.add_query("complex_query", timer.duration_ms)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            timer = QueryTimer(query_name, threshold_ms=100)
            with timer:
                result = func(*args, **kwargs)
            
            metrics = get_current_metrics()
            if metrics:
                metrics.add_query(query_name, timer.duration_ms, query_type, rows_affected)
            
            return result
        return wrapper
    return decorator


def track_endpoint(func: Callable) -> Callable:
    """
    Decorator to track endpoint performance.
    
    Automatically tracks:
    - Total request time
    - Database query count and time
    - Memory usage
    
    Usage:
        @router.get("/users/{user_id}")
        @track_endpoint
        async def get_user(user_id: str):
            ...
    """
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        metrics = PerformanceMetrics()
        set_current_metrics(metrics)
        
        try:
            result = await func(*args, **kwargs)
            status_code = 200
        except Exception as e:
            metrics.log_summary(func.__name__, 500)
            raise
        finally:
            # Log if not already logged
            try:
                metrics.log_summary(func.__name__, status_code)
            except Exception:
                pass
            clear_current_metrics()
        
        return result
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        metrics = PerformanceMetrics()
        set_current_metrics(metrics)
        
        try:
            result = func(*args, **kwargs)
            status_code = 200
        except Exception as e:
            metrics.log_summary(func.__name__, 500)
            raise
        finally:
            try:
                metrics.log_summary(func.__name__, status_code)
            except Exception:
                pass
            clear_current_metrics()
        
        return result
    
    # Return appropriate wrapper based on function type
    if "asyncio" in sys.modules and hasattr(func, "__code__"):
        if func.__code__.co_flags & 0x100:  # Check if coroutine
            return async_wrapper
    
    return sync_wrapper


class DatabaseClient:
    """Wrap database client to track query times."""
    
    def __init__(self, client):
        """Initialize database client wrapper."""
        self.client = client
    
    def table(self, table_name: str):
        """Get table with query tracking."""
        return TrackedTable(self.client.table(table_name), table_name)


class TrackedTable:
    """Wrap table operations to track query times."""
    
    def __init__(self, table, table_name: str):
        """Initialize tracked table."""
        self._table = table
        self._table_name = table_name
        self._query_parts = []
    
    def select(self, *columns):
        """Track select operation."""
        self._track_operation("SELECT", columns)
        self._table.select(*columns)
        return self
    
    def eq(self, column: str, value):
        """Track filter operation."""
        self._track_operation("FILTER", f"{column}={value}")
        self._table.eq(column, value)
        return self
    
    def execute(self):
        """Execute query with timing."""
        query_desc = f"{self._table_name}: {', '.join(self._query_parts)}"
        
        with QueryTimer(query_desc, threshold_ms=200) as timer:
            result = self._table.execute()
        
        metrics = get_current_metrics()
        if metrics:
            rows_affected = len(result.data) if hasattr(result, "data") and result.data else 0
            metrics.add_query(query_desc, timer.duration_ms, "SELECT", rows_affected)
        
        return result
    
    def _track_operation(self, op_type: str, details):
        """Track query operation part."""
        if isinstance(details, tuple):
            details = ", ".join(str(d) for d in details)
        self._query_parts.append(f"{op_type}({details})")
    
    def __getattr__(self, name):
        """Proxy other methods to wrapped table."""
        return getattr(self._table, name)
