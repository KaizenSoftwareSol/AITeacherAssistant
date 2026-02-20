# IMPLEMENTATION_GUIDE.md

## Performance Monitoring Implementation Guide

### Overview
I've created a comprehensive performance monitoring system to help you identify and fix slow queries. This guide shows you how to implement it step-by-step.

## Files Created

1. **`services/performance_monitor.py`** - Core performance tracking decorators
2. **`services/query_logger.py`** - Detailed query execution logging
3. **`services/performance_middleware.py`** - Enhanced request middleware
4. **`services/db_optimization_guide.py`** - Optimization patterns and examples
5. **`PERFORMANCE_ANALYSIS.md`** - Analysis of current performance issues

## Step 1: Update Dependencies

Make sure you have in `requirements.txt`:
```
fastapi>=0.95.0
starlette>=0.26.0
```

## Step 2: Integration Guide

### Option A: Simple Integration (Recommended for immediate use)

**Update your `main.py` or application startup:**

```python
# In your main.py or app initialization

from fastapi import FastAPI
from services.performance_middleware import setup_performance_middleware
from services.query_logger import get_query_logger

app = FastAPI()

# Setup performance middleware
setup_performance_middleware(app)

# Initialize query logger
query_logger = get_query_logger()
```

### Option B: Decorator-based Integration (For specific endpoints)

For endpoints you want to deeply profile, add the decorator:

```python
from services.performance_monitor import track_endpoint
from fastapi import APIRouter

router = APIRouter()

@router.get("/assessments/all")
@track_endpoint  # Add this decorator
async def get_all_teacher_assessments(
    current_user: Annotated[User, Depends(require_teacher)],
    db=Depends(get_db),
):
    # Your existing code
    ...
```

## Step 3: Query-Level Logging

For detailed query tracking, wrap database queries:

```python
from services.query_logger import get_query_logger

def get_unread_count(self, user_id: str) -> int:
    query_logger = get_query_logger()
    
    # Existing query
    result = (
        self.db.admin_client
        .table("notification")
        .select("id", count="exact")
        .eq("user_id", str(user_id))
        .eq("is_read", False)
        .eq("is_archived", False)
        .execute()
    )
    
    # Log query
    query_logger.log_query(
        operation="COUNT",
        table="notification",
        duration_ms=0.0,  # Calculate from timer
        rows_count=result.count or 0,
        filters={"user_id": user_id, "is_read": False, "is_archived": False}
    )
    
    return result.count or 0
```

Or use context manager for automatic timing:

```python
from services.query_logger import QueryLogger, QueryTimer
import time

def get_unread_count(self, user_id: str) -> int:
    start = time.perf_counter()
    
    result = (
        self.db.admin_client
        .table("notification")
        .select("id", count="exact")
        .eq("user_id", str(user_id))
        .eq("is_read", False)
        .eq("is_archived", False)
        .execute()
    )
    
    duration_ms = (time.perf_counter() - start) * 1000
    
    query_logger = get_query_logger()
    query_logger.log_query(
        operation="COUNT",
        table="notification",
        duration_ms=duration_ms,
        rows_count=result.count or 0,
        filters={"user_id": user_id, "is_read": False, "is_archived": False}
    )
    
    return result.count or 0
```

## Step 4: Monitor Logs

After integration, run your application and make requests. You'll see detailed logs like:

### Example Log Output:

```
2026-02-19 16:00:00.123 | WARNING  | services.performance_middleware - SLOW_REQUEST: GET /api/v1/notifications/unread-count | Duration: 2500ms | DB Time: 2100ms (84.0%) | Queries: 3 (2 slow, 0 errors) | SELECT notification(n=1, 2100ms) | COUNT user(n=2, 400ms)
  ├─ SLOW_QUERY[1]: COUNT on notification | Time: 2100ms | Rows: 35
  ├─ SLOW_QUERY[2]: SELECT on user | Time: 350ms | Rows: 1

2026-02-19 16:00:01.456 | WARNING  | services.query_logger - DB_QUERY_SLOW: SELECT on assessment took 1850.25ms (rows: 124) | Filters: teacher_id=3275c563-23a3-457b-b24c-9f04bf116480, status=published

2026-02-19 16:00:02.789 | INFO     | services.query_logger - DB_QUERY: INSERT on assessment_submission took 45.12ms (rows: 1)
```

## Step 5: Identify Bottlenecks

Look for patterns in logs:

### Pattern 1: Single Slow Query
```
SLOW_QUERY: SELECT on notification took 2100ms
→ Solution: Add index on notification(user_id, is_read, is_archived)
```

### Pattern 2: Many Small Slow Queries
```
SELECT on assessment took 150ms (rows: 1)
SELECT on assessment took 145ms (rows: 1)
SELECT on assessment took 152ms (rows: 1)
SELECT on assessment took 148ms (rows: 1)
→ Solution: Use batch query with join instead of loop
```

### Pattern 3: High % of Time in Database
```
Duration: 2500ms | DB Time: 2450ms (98.0%)
→ Solution: Optimize query or add caching
```

### Pattern 4: Inconsistent Performance
```
First call: 500ms
Second call: 1500ms
Third call: 2500ms
→ Solution: Memory leak or unbounded result set
```

## Step 6: Fix Slow Endpoints

### CRITICAL: Fix `/api/v1/notifications/unread-count`

**Current Code Issue:**
- Called every 30-60 seconds
- Takes 1-3 seconds
- No caching

**Fix #1: Add Database Index (IMMEDIATE)**

In Supabase SQL editor:
```sql
CREATE INDEX idx_notification_user_read_archived 
ON notification(user_id, is_read, is_archived);
```

**Fix #2: Add Caching**

Update `services/notification_service.py`:

```python
from services.cache_service import cache  # Assuming you have this

def get_unread_count(self, user_id: str) -> int:
    """Get the count of unread notifications for a user."""
    cache_key = f"unread_count:{user_id}"
    
    # Try cache first
    cached_count = cache.get("queries", cache_key)
    if cached_count is not None:
        logger.debug(f"Unread count cache HIT for user {user_id}")
        return cached_count
    
    # Query database
    try:
        result = (
            self.db.admin_client
            .table("notification")
            .select("id", count="exact")
            .eq("user_id", str(user_id))
            .eq("is_read", False)
            .eq("is_archived", False)
            .execute()
        )
        
        count = result.count or 0
        
        # Cache for 10 seconds
        cache.set("queries", count, cache_key, ttl=10)
        logger.debug(f"Unread count cache MISS for user {user_id}: {count}")
        
        return count
        
    except Exception as e:
        logger.error(f"Error getting unread count: {str(e)}")
        return 0
```

**Fix #3: Reduce UI Polling Frequency**

In your frontend, change polling from every 30 seconds to every 60 seconds:
```javascript
// Old
setInterval(() => getUnreadCount(), 30000);

// New
setInterval(() => getUnreadCount(), 60000);  // Or 120000 for less frequent
```

### HIGH PRIORITY: Fix `/api/v1/teacher/assessments/all`

**Current Issue:** N+1 queries - fetches all lectures, then loops through to get course info

**Fix:**

Replace this:
```python
# SLOW: Get lectures, then query courses in loop
lectures_result = db.admin_client.table("lecture").select("*").eq("teacher_id", teacher.id).execute()
lecture_map = {lec["id"]: lec for lec in lectures_result.data}

course_ids = list(set(lec["course_id"] for lec in lectures_result.data if lec.get("course_id")))

# This loops and causes N+1
for course_id in course_ids:
    course_result = db.admin_client.table("course").select("*").eq("id", course_id).execute()
    # ...
```

With this:
```python
# FAST: Get lectures with joined course info in ONE query
lectures_result = (
    db.admin_client
    .table("lecture")
    .select(" id, title, course_id, status, topic, lecture_number, created_at, course!inner(id, name, code)")
    .eq("teacher_id", teacher.id)
    .order("created_at", desc=True)
    .execute()
)

# Now access as: lectures_result.data[0]["course"]["name"]
```

## Step 7: Monitor Improvements

After implementing fixes, compare logs:

### Before Optimization
```
SLOW_REQUEST: GET /api/v1/notifications/unread-count | Duration: 2500ms | Queries: 3
```

### After Optimization
```
REQUEST: GET /api/v1/notifications/unread-count | Duration: 45ms | Queries: 1
```

## Step 8: Set Up Alerts

Add alert thresholds to `services/performance_middleware.py`:

```python
# For critical endpoints
if "unread-count" in path and duration_ms > 500:
    send_alert(f"Unread count endpoint slow: {duration_ms}ms")

# For all endpoints
if duration_ms > 5000:
    send_alert(f"Very slow request detected: {path} took {duration_ms}ms")
```

## Performance Metrics Reference

### Good Performance
- Unread count: < 100ms
- Course list: < 500ms  
- Assessment details: < 1000ms
- Dashboard: < 2000ms

### Warning Thresholds
- Any endpoint: > 2000ms
- Count query: > 500ms
- List endpoint: > 1500ms

### Critical Thresholds (Fix immediately)
- Any endpoint: > 5000ms
- Frequently called endpoint: > 1000ms
- Count query: > 1000ms

## Troubleshooting

### Issue: Still slow after adding index
**Solution:**
1. Verify index was created: Check Supabase SQL tab
2. Check if index is being used: Run `EXPLAIN ANALYZE` on query
3. May need to analyze statistics: `ANALYZE notification;`

### Issue: Cache hit but still slow initial load
**Solution:**
1. Implement warm-up cache on application startup
2. Pre-load common queries
3. Increase cache TTL

### Issue: Logs show application code is slow, not database
**Solution:**
1. Check for loops or inefficient algorithms
2. Profile Python code with `cProfile`
3. Look for external API calls in request path

## Next Steps

1. ✅ Integrate the logging system
2. ✅ Run your application and collect metrics
3. ✅ Identify bottlenecks from logs
4. ✅ Apply optimization patterns from `db_optimization_guide.py`
5. ✅ Create database indexes for slow queries
6. ✅ Verify improvements in logs
7. ✅ Set up continuous monitoring

## Additional Resources

- `PERFORMANCE_ANALYSIS.md` - Detailed analysis of current issues
- `services/db_optimization_guide.py` - Code patterns for optimization
- `services/performance_monitor.py` - Decorator implementation
- `services/query_logger.py` - Query-level logging

## Questions?

Look at the actual implementation:
- Check log format in `performance_middleware.py`
- See query tracking in `query_logger.py`
- Review decorator patterns in `performance_monitor.py`
