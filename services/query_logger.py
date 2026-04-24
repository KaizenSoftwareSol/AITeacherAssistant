# services/query_logger.py
"""
Detailed query logging for database operations.
Logs every database query with execution time to help identify bottlenecks.
"""

import json
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from logger import logger
from services.request_context import get_request_id


class QueryLogger:
    """Log all database queries with timing information."""
    
    def __init__(self):
        """Initialize query logger."""
        self.queries: List[Dict[str, Any]] = []
        self.session_start = time.time()
    
    def log_query(
        self,
        operation: str,
        table: str,
        duration_ms: float,
        rows_count: int = 0,
        filters: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """
        Log a database query.
        
        Args:
            operation: Type of operation (SELECT, INSERT, UPDATE, DELETE, COUNT)
            table: Table name
            duration_ms: Query execution time in milliseconds
            rows_count: Number of rows affected/returned
            filters: Query filters applied
            error: Error message if query failed
        """
        query_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "operation": operation,
            "table": table,
            "duration_ms": duration_ms,
            "rows_count": rows_count,
            "filters": filters or {},
            "error": error,
            "level": self._determine_log_level(duration_ms, error),
        }
        
        self.queries.append(query_log)
        
        # Log immediately with appropriate level
        if error:
            rid = get_request_id() or "-"
            logger.error(
                f"DB_QUERY_ERROR: rid={rid} {operation} on {table} failed: {error} "
                f"(took {duration_ms:.2f}ms)"
            )
        elif duration_ms > 500:
            rid = get_request_id() or "-"
            logger.warning(
                f"DB_QUERY_SLOW: rid={rid} {operation} on {table} took {duration_ms:.2f}ms "
                f"(rows: {rows_count}) | Filters: {self._format_filters(filters)}"
            )
        elif duration_ms > 100:
            rid = get_request_id() or "-"
            logger.info(
                f"DB_QUERY: rid={rid} {operation} on {table} took {duration_ms:.2f}ms "
                f"(rows: {rows_count})"
            )
        else:
            logger.debug(
                f"DB_QUERY_FAST: {operation} on {table} took {duration_ms:.2f}ms"
            )
    
    def log_request_summary(
        self,
        endpoint: str,
        method: str,
        duration_ms: float,
        status_code: int = 200,
    ):
        """
        Log request summary with all queries.
        
        Args:
            endpoint: API endpoint path
            method: HTTP method
            duration_ms: Total request time
            status_code: HTTP response status
        """
        if not self.queries:
            return
        
        total_query_ms = sum(q["duration_ms"] for q in self.queries if not q.get("error"))
        slow_queries = [q for q in self.queries if q["duration_ms"] > 100]
        
        summary = {
            "endpoint": endpoint,
            "method": method,
            "duration_ms": duration_ms,
            "status_code": status_code,
            "total_queries": len(self.queries),
            "slow_queries_count": len(slow_queries),
            "total_query_time_ms": total_query_ms,
            "db_time_percent": (total_query_ms / duration_ms * 100) if duration_ms > 0 else 0,
        }
        
        if duration_ms > 1000 or len(slow_queries) > 0:
            logger.warning(
                f"REQUEST_SUMMARY: {method} {endpoint} | "
                f"Duration: {duration_ms:.0f}ms | "
                f"Queries: {summary['total_queries']} "
                f"({summary['slow_queries_count']} slow) | "
                f"DB Time: {total_query_ms:.0f}ms ({summary['db_time_percent']:.1f}%) | "
                f"Status: {status_code} | "
                f"Queries: {self._format_queries_summary()}"
            )
        
        self.queries = []  # Reset for next request
    
    def get_queries(self) -> List[Dict[str, Any]]:
        """Get all logged queries."""
        return self.queries.copy()
    
    def _determine_log_level(self, duration_ms: float, error: Optional[str]) -> str:
        """Determine log level based on query performance."""
        if error:
            return "ERROR"
        elif duration_ms > 500:
            return "WARNING"
        elif duration_ms > 100:
            return "INFO"
        else:
            return "DEBUG"
    
    def _format_filters(self, filters: Optional[Dict]) -> str:
        """Format filters for logging."""
        if not filters:
            return "none"
        return ", ".join(f"{k}={v}" for k, v in filters.items())
    
    def _format_queries_summary(self) -> str:
        """Format queries summary for log."""
        if not self.queries:
            return "none"
        
        query_summary = {}
        for q in self.queries:
            key = f"{q['operation']} {q['table']}"
            if key not in query_summary:
                query_summary[key] = {"count": 0, "total_ms": 0}
            query_summary[key]["count"] += 1
            query_summary[key]["total_ms"] += q["duration_ms"]
        
        return " | ".join(
            f"{k}(n={v['count']}, {v['total_ms']:.0f}ms)"
            for k, v in sorted(query_summary.items())
        )


# Global query logger instance
_query_logger = QueryLogger()


def get_query_logger() -> QueryLogger:
    """Get global query logger instance."""
    return _query_logger


class DatabaseQueryWrapper:
    """Wrap Supabase client methods to log query timing."""
    
    def __init__(self, client, query_logger: QueryLogger):
        """Initialize wrapper."""
        self.client = client
        self.query_logger = query_logger
    
    def table(self, table_name: str):
        """Get table with query tracking."""
        return WrappedTableQuery(self.client.table(table_name), table_name, self.query_logger)


class WrappedTableQuery:
    """Wrap table query builder to track timing."""
    
    def __init__(self, table_query, table_name: str, query_logger: QueryLogger):
        """Initialize wrapped table query."""
        self._table = table_query
        self._table_name = table_name
        self._query_logger = query_logger
        self._operation = "SELECT"
        self._filters = {}
        self._columns = []
    
    def select(self, *columns):
        """Track select operation."""
        self._operation = "SELECT"
        self._columns = list(columns)
        self._table = self._table.select(*columns)
        return self
    
    def eq(self, column: str, value: Any):
        """Track equality filter."""
        self._filters[column] = value
        self._table = self._table.eq(column, value)
        return self
    
    def neq(self, column: str, value: Any):
        """Track not equal filter."""
        self._table = self._table.neq(column, value)
        return self
    
    def gt(self, column: str, value: Any):
        """Track greater than filter."""
        self._table = self._table.gt(column, value)
        return self
    
    def gte(self, column: str, value: Any):
        """Track greater than or equal filter."""
        self._table = self._table.gte(column, value)
        return self
    
    def lt(self, column: str, value: Any):
        """Track less than filter."""
        self._table = self._table.lt(column, value)
        return self
    
    def lte(self, column: str, value: Any):
        """Track less than or equal filter."""
        self._table = self._table.lte(column, value)
        return self
    
    def order(self, column: str, desc: bool = False):
        """Track order operation."""
        self._table = self._table.order(column, desc=desc)
        return self
    
    def limit(self, count: int):
        """Track limit operation."""
        self._table = self._table.limit(count)
        return self
    
    def insert(self, data):
        """Track insert operation."""
        self._operation = "INSERT"
        self._table = self._table.insert(data)
        return self
    
    def update(self, data):
        """Track update operation."""
        self._operation = "UPDATE"
        self._table = self._table.update(data)
        return self
    
    def delete(self):
        """Track delete operation."""
        self._operation = "DELETE"
        self._table = self._table.delete()
        return self
    
    def execute(self):
        """Execute query with timing."""
        start_time = time.perf_counter()
        
        try:
            result = self._table.execute()
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Determine rows count from result
            rows_count = 0
            if hasattr(result, "count") and result.count is not None:
                rows_count = result.count
            elif hasattr(result, "data") and result.data:
                rows_count = len(result.data)
            
            # Log the query
            self._query_logger.log_query(
                operation=self._operation,
                table=self._table_name,
                duration_ms=duration_ms,
                rows_count=rows_count,
                filters=self._filters if self._filters else None,
            )
            
            return result
        
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._query_logger.log_query(
                operation=self._operation,
                table=self._table_name,
                duration_ms=duration_ms,
                filters=self._filters if self._filters else None,
                error=str(e),
            )
            raise
    
    def __getattr__(self, name):
        """Proxy other methods to wrapped table."""
        return getattr(self._table, name)
