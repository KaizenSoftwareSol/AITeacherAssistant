# services/db_optimization_guide.py
"""
Guide for optimizing slow database queries.
Contains patterns and examples for fixing common performance issues.
"""

# ==============================================================================
# PROBLEM 1: N+1 Query Pattern
# ==============================================================================
# SLOW (N+1 problem):
# Current code pattern where you loop and query for each item
"""
# Bad - this causes N+1 queries (1 for lectures + N for each course)
lectures = db.admin_client.table("lecture").select("*").eq("teacher_id", teacher_id).execute()
lecture_map = {}
for lecture in lectures.data:
    course = db.admin_client.table("course").select("*").eq("id", lecture["course_id"]).execute()
    lecture_map[lecture["id"]] = {
        **lecture,
        "course": course.data[0] if course.data else None
    }
"""

# FAST (Proper joins):
"""
# Good - single query with join
lectures = (
    db.admin_client
    .table("lecture")
    .select("*, course!inner(*)")  # Use join with course table
    .eq("teacher_id", teacher_id)
    .execute()
)
"""

# ==============================================================================
# PROBLEM 2: Missing Database Indexes
# ==============================================================================
# Create these indexes in Supabase:
"""
-- For notifications unread count (CRITICAL - this is your slowest endpoint)
CREATE INDEX idx_notification_user_read_archived 
ON notification(user_id, is_read, is_archived);

-- For lecture queries
CREATE INDEX idx_lecture_teacher_id ON lecture(teacher_id);
CREATE INDEX idx_lecture_course_id ON lecture(course_id);

-- For assessment queries
CREATE INDEX idx_assessment_teacher_id ON assessment(teacher_id);
CREATE INDEX idx_assessment_lecture_id ON assessment(lecture_id);
CREATE INDEX idx_question_assessment_id ON question(assessment_id);
CREATE INDEX idx_assessment_submission_assessment_id 
ON assessment_submission(assessment_id);

-- For course queries
CREATE INDEX idx_course_teacher_id ON course(created_by_teacher_id);
CREATE INDEX idx_course_teacher_assignment 
ON course_teacher(teacher_id, is_active);

-- For user queries (if not exist)
CREATE INDEX idx_user_email ON "user"(email);
"""

# ==============================================================================
# PROBLEM 3: Multiple Small Queries Instead of Batch
# ==============================================================================
# SLOW: Multiple queries for the same data
"""
# Bad - 3 separate queries
courses_data = db.admin_client.table("course").select("*").execute()
teachers_data = db.admin_client.table("teacher").select("*").execute()
students_data = db.admin_client.table("student").select("*").execute()
"""

# FAST: Single query with joins or batch operations
"""
# Good - single joined query if possible
data = (
    db.admin_client
    .table("course")
    .select("*, teacher!inner(*)")
    .execute()
)
"""

# ==============================================================================
# PROBLEM 4: Fetching Too Much Data (Lack of Projection)
# ==============================================================================
# SLOW: Fetching all columns when you only need a few
"""
# Bad - fetches all columns
result = db.admin_client.table("lecture").select("*").execute()

# Then accessing only specific fields
for lecture in result.data:
    print(lecture["id"], lecture["title"])
"""

# FAST: Select only needed columns
"""
# Good - only select needed columns
result = (
    db.admin_client
    .table("lecture")
    .select("id, title")  # Only select what you need
    .execute()
)
"""

# ==============================================================================
# PROBLEM 5: No Pagination for Large Result Sets
# ==============================================================================
# SLOW: Loading 10,000 records when you only show 20
"""
# Bad - loads all records
all_assessments = (
    db.admin_client
    .table("assessment")
    .select("*")
    .eq("teacher_id", teacher_id)
    .execute()
)

# Filter in application
results = all_assessments.data[:20]
"""

# FAST: Use limit and offset
"""
# Good - only load what's needed
page = 0
page_size = 20

assessments = (
    db.admin_client.table("assessment")
    .select("*")
    .eq("teacher_id", teacher_id)
    .order("created_at", desc=True)
    .limit(page_size)
    .offset(page * page_size)
    .execute()
)

total_count = (
    db.admin_client.table("assessment")
    .select("id", count="exact")
    .eq("teacher_id", teacher_id)
    .execute()
)
"""

# ==============================================================================
# PROBLEM 6: Repeated Queries for Same Data (No Caching)
# ==============================================================================
# SLOW: Querying same data multiple times per request
"""
# Bad - get_unread_count called multiple times per request
def get_notifications():
    count1 = get_unread_count(user_id)  # Query 1
    count2 = get_unread_count(user_id)  # Query 2 (same result)
    return count1 + count2
"""

# FAST: Cache results
"""
# Good - cache the count for 10 seconds
from functools import lru_cache
import time

@lru_cache(maxsize=1000)
def get_unread_count_cached(user_id: str, cache_time: int):
    return get_unread_count(user_id)

# Or use Redis
def get_unread_count(user_id: str, use_cache=True):
    if use_cache:
        cached = redis_client.get(f"unread_count:{user_id}")
        if cached:
            return int(cached)
    
    count = db.admin_client.table("notification").select("id", count="exact")\\
        .eq("user_id", user_id)\\
        .eq("is_read", False)\\
        .eq("is_archived", False)\\
        .execute().count
    
    # Cache for 10 seconds
    redis_client.setex(f"unread_count:{user_id}", 10, count)
    return count
"""

# ==============================================================================
# CODE TRANSFORMATION GUIDE FOR NOTIFICATION SERVICE
# ==============================================================================
"""
# Current slow implementation:
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

# Optimized implementation with caching:
def get_unread_count(self, user_id: str) -> int:
    cache_key = f"unread_count:{user_id}"
    
    # Try cache first (Redis or in-memory cache)
    cached = self.cache.get(cache_key)
    if cached is not None:
        return cached
    
    # Query database
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
    self.cache.set(cache_key, count, ttl=10)
    
    return count
"""

# ==============================================================================
# OPTIMIZATION CHECKLIST
# ==============================================================================
"""
For each slow endpoint:

☐ Check if all necessary database indexes exist
☐ Look for N+1 query patterns (loops with queries inside)
☐ Replace multiple queries with joins
☐ Only select columns you actually use
☐ Add pagination for list endpoints
☐ Cache frequently accessed data (notifications, user profiles, etc)
☐ Look for sequential queries that can be parallelized
☐ Check if you're fetching related data that could be joined
☐ Profile with query timing to find exact bottleneck
☐ Add query result caching for user-specific data with short TTL
"""

# ==============================================================================
# IMPLEMENTATION PATTERNS
# ==============================================================================

# Pattern 1: Batch query with joins (BEST for 1-N relationships)
pattern_1 = """
# Get lectures with course info in ONE query
lectures = (
    db.admin_client.table("lecture")
    .select("id, title, course_id, course!inner(id, name)")
    .eq("teacher_id", teacher_id)
    .execute()
)
# Result: [{id, title, course_id, course: {id, name}}, ...]
"""

# Pattern 2: Query with count (for counts/stats)
pattern_2 = """
# Get counts in one query
counts = (
    db.admin_client.table("notification")
    .select("id", count="exact")
    .eq("user_id", user_id)
    .eq("is_read", False)
    .execute()
)
count = counts.count  # Much faster than len(counts.data)
"""

# Pattern 3: With caching (for frequently accessed data)
pattern_3 = """
import redis

# Initialize cache
cache = redis.Redis(host='localhost', port=6379, db=0)

def get_user_courses(user_id: str):
    # Check cache first
    cached = cache.get(f"user_courses:{user_id}")
    if cached:
        return json.loads(cached)
    
    # Query if not cached
    result = db.admin_client.table("course")\\
        .select("*")\\
        .eq("teacher_id", user_id)\\
        .execute()
    
    # Cache for 5 minutes
    cache.setex(
        f"user_courses:{user_id}",
        300,
        json.dumps(result.data)
    )
    
    return result.data
"""

# Pattern 4: Pagination (for large result sets)
pattern_4 = """
def get_assessments_paginated(teacher_id: str, page: int = 0, page_size: int = 20):
    # Query only what's needed
    offset = page * page_size
    
    result = (
        db.admin_client.table("assessment")
        .select("*")
        .eq("teacher_id", teacher_id)
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    
    # Get total count
    count_result = (
        db.admin_client.table("assessment")
        .select("id", count="exact")
        .eq("teacher_id", teacher_id)
        .execute()
    )
    
    return {
        "data": result.data,
        "total": count_result.count,
        "page": page,
        "page_size": page_size,
        "pages": (count_result.count + page_size - 1) // page_size
    }
"""

print("""
✅ Optimization Guide Created
📍 Location: services/db_optimization_guide.py

Key Takeaways:
1. Use indexes on commonly filtered columns
2. Replace N+1 queries with joins
3. Only select needed columns
4. Cache frequent queries
5. Use pagination for large datasets
6. Profile slow endpoints to find exact bottleneck
""")
