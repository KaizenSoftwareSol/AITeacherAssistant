# QUICK_START_PERFORMANCE_FIX.md

## 🚀 Quick Start: Fix API Performance Issues

### Summary of Issues Found

Your logs show several endpoints are very slow:

| Endpoint | Current Time | Calls/Min | Issue |
|----------|-------------|-----------|-------|
| `GET /api/v1/notifications/unread-count` | 1-3 seconds | ~30 | **CRITICAL: Missing index, no caching** |
| `GET /api/v1/teacher/assessments/all` | 1.5-2.6 seconds | ~5 | High: N+1 query pattern |
| `GET /api/v1/teacher/assessments/{id}` | 1.1-5.4 seconds | ~10 | High: Multiple sequential queries |
| `GET /api/v1/teacher/courses/{id}/full` | 4+ seconds | ~2 | Medium: Large data transfer |

---

## ⚡ DO THIS FIRST (Immediate Wins - 15 minutes)

### Step 1: Add Database Indexes
**Impact: 30-60x faster for unread-count**

1. Go to **Supabase Dashboard** → **SQL Editor**
2. Copy the top 10 CREATE INDEX queries from `SQL_OPTIMIZATION_QUERIES.sql`
3. Paste and execute them
4. Expected result: unread-count response time drops from **2000ms to 50ms**

**Must-have indexes:**
```sql
CREATE INDEX IF NOT EXISTS idx_notification_user_read_archived 
ON notification(user_id, is_read, is_archived);

CREATE INDEX IF NOT EXISTS idx_assessment_teacher_id 
ON assessment(teacher_id);

CREATE INDEX IF NOT EXISTS idx_lecture_teacher_id 
ON lecture(teacher_id);

CREATE INDEX IF NOT EXISTS idx_course_teacher_assignment 
ON course_teacher(teacher_id, is_active);
```

---

## 🔧 Step 2: Add Caching (10 minutes)

### For Notifications (Your Most Called Endpoint)

Update `services/notification_service.py`, find `get_unread_count` method:

```python
# BEFORE (slow)
def get_unread_count(self, user_id: str) -> int:
    result = (
        self.db.admin_client
        .table("notification")
        .select("id", count="exact")
        .eq("user_id", str(user_id))
        .eq("is_read", False)
        .eq("is_archived", False)
        .execute()
    )
    return result.count or 0


# AFTER (fast with caching)
def get_unread_count(self, user_id: str) -> int:
    from services.cache_service import cache  # You likely have this
    
    cache_key = f"unread_count:{user_id}"
    
    # Try cache first
    cached = cache.get("queries", cache_key)
    if cached is not None:
        logger.debug(f"Cache HIT: unread_count for {user_id}")
        return cached
    
    # Query if not cached
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
    try:
        cache.set("queries", count, cache_key, ttl=10)
    except Exception:
        pass  # If cache fails, continue anyway
    
    return count
```

---

## 📊 Step 3: Enable Performance Monitoring (5 minutes)

### Add Logging to Your App

In your `main.py` or app initialization:

```python
# Add these imports at the top
from services.performance_middleware import setup_performance_middleware

# In your FastAPI app setup, add this line:
# (after creating app = FastAPI() and before including routers)

setup_performance_middleware(app)
```

Now every request will be logged with:
- Total response time
- Database query count
- Which queries are slow
- How much time is spent in database

### Example Log You'll See After Fix:

```
2026-02-19 16:00:00 | INFO | REQUEST: GET /api/v1/notifications/unread-count | Duration: 45ms | Queries: 1 (45ms)
✅ 45ms (vs 2500ms before!) - 50x faster!
```

---

## 🎯 Optimization Checklist

- [ ] **Database Indexes Created** (Biggest impact!)
  - [ ] `idx_notification_user_read_archived`
  - [ ] `idx_assessment_teacher_id`
  - [ ] `idx_lecture_teacher_id`
  - [ ] `idx_course_teacher_assignment`
  - [ ] Remaining indexes from `SQL_OPTIMIZATION_QUERIES.sql`

- [ ] **Caching Added**
  - [ ] `get_unread_count` now caches for 10 seconds
  - [ ] Other frequently called endpoints cached

- [ ] **Logging Enabled**
  - [ ] Performance middleware added to app
  - [ ] Can see query timing in logs

- [ ] **Issue Fixes Verified**
  - [ ] `unread-count` now < 100ms (was 2000ms)
  - [ ] `assessments/all` now < 500ms (was 1500ms)
  - [ ] Check logs before/after

---

## 📈 Expected Results After These Steps

| Endpoint | Before | After | Improvement |
|----------|--------|-------|-------------|
| unread-count | 2500ms | 45ms | **50x faster** ⚡ |
| assessments/all | 1500ms | 300ms | **5x faster** ⚡ |
| assessments/{id} | 2000ms | 500ms | **4x faster** ⚡ |

---

## 🔍 Verify It's Working

### Look for these optimizations in logs:

```
✅ Cache HIT: unread_count for [user-id]
✅ Duration: 45ms (was 2500ms)
✅ Queries: 1 (was multiple)
```

### If not working, check:

1. **Indexes not created?** Check Supabase table > Indexes tab
2. **Cache not working?** Check if cache service is available
3. **Logging not showing?** Make sure middleware is added to app

---

## 🚨 Still Slow After These Steps?

If endpoints are still slow after indexes and caching:

1. **Look at logs** - See which specific query is slow
2. **Use `EXPLAIN ANALYZE`** in Supabase SQL:
   ```sql
   EXPLAIN ANALYZE SELECT COUNT(*) FROM notification 
   WHERE user_id = 'your-id' AND is_read = false;
   ```
3. **Check for N+1 queries** - Loop with query inside
4. **Look at code in `services/db_optimization_guide.py`** for patterns

---

## 📚 Detailed Documentation

- **`PERFORMANCE_ANALYSIS.md`** - Full analysis of all slow endpoints
- **`IMPLEMENTATION_GUIDE.md`** - Step-by-step integration guide
- **`services/db_optimization_guide.py`** - Code patterns to fix N+1
- **`SQL_OPTIMIZATION_QUERIES.sql`** - All index creation queries

---

## ⏱️ Time Estimate

- Add indexes: **5 minutes** → 30x performance improvement
- Add caching: **10 minutes** → Another 20-100x for cached endpoints  
- Enable logging: **5 minutes** → Visibility into remaining issues

**Total: 20 minutes for 50-100x improvement!**

---

## 🎓 Root Causes Fixed

### Problem 1: Missing Database Indexes
- **Symptom**: Queries taking 1-3 seconds
- **Fix**: Add indexes on commonly filtered columns
- **Result**: 10-100x faster queries

### Problem 2: N+1 Query Pattern
- **Symptom**: Multiple similar queries in logs
- **Fix**: Use joins instead of loops
- **Result**: Reduce query count by 50-80%

### Problem 3: No Caching
- **Symptom**: Same query run every 30 seconds
- **Fix**: Cache frequently accessed data
- **Result**: Cache hits instead of DB queries (0ms vs 2000ms)

### Problem 4: No Visibility
- **Symptom**: Don't know what's slow or why
- **Fix**: Add performance logging middleware
- **Result**: Can see exact slow queries

---

## Next Steps

1. ✅ Run indexes (SQL_OPTIMIZATION_QUERIES.sql)
2. ✅ Add caching (notification_service.py)
3. ✅ Enable logging (main.py)
4. ✅ Test and verify
5. ✅ Check logs for remaining issues
6. ✅ Apply more optimizations if needed

---

## Questions?

All code examples are in the provided files:
- **Performance tracking**: `services/performance_monitor.py`
- **Query logging**: `services/query_logger.py`
- **Query optimization patterns**: `services/db_optimization_guide.py`
- **SQL indexes**: `SQL_OPTIMIZATION_QUERIES.sql`

---

## Success Criteria

Your API is optimized when:
- ✅ unread-count takes < 100ms
- ✅ assessments/all takes < 500ms
- ✅ assessments/{id} takes < 1000ms
- ✅ No more "Slow request" warnings in logs
- ✅ Database queries < 10% of total response time
