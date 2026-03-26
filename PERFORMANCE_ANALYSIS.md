# Performance Analysis & Optimization Report

## 📊 Critical Performance Issues Identified

### 1. **GET /api/v1/notifications/unread-count** ⚠️ CRITICAL
- **Frequency**: Called every 30-60 seconds by UI
- **Response Time**: 1.0 - 3.2 seconds
- **Issue**: Simple count query taking way too long
- **Root Causes**:
  - Missing database index on `notification(user_id, is_read, is_archived)`
  - Possible N+1 issues in database or missing query optimization
  - Called repeatedly by frontend (polling pattern)
- **Impact**: HIGH - Affects every page load and UI interaction
- **Recommendation**: 
  - Add database indexes
  - Implement caching (Redis) with short TTL
  - Reduce frontend polling frequency

### 2. **GET /api/v1/teacher/assessments/all** ⚠️ HIGH
- **Response Time**: 1.5 - 2.6 seconds
- **Why It's Slow**:
  - Fetches all lectures by teacher (multiple queries)
  - Then loops through each lecture to get course info
  - Multiple Supabase table joins happening
  - N+1 query pattern: fetches lectures, then courses one by one
- **Recommendation**: Use batch queries with joins

### 3. **GET /api/v1/teacher/assessments/{id}** ⚠️ HIGH
- **Response Time**: 1.1 - 5.4 seconds (very inconsistent)
- **Why It's Slow**:
  - Multiple sequential table queries
  - Getting assessment, questions, submissions separately
  - No joined queries
- **Recommendation**: Use single query with joins

### 4. **GET /api/v1/teacher/courses/{id}/full** ⚠️ MEDIUM-HIGH
- **Response Time**: 4.3 seconds +
- **Why It's Slow**: Fetching complete course data, all lectures, enrollments
- **Recommendation**: Optimize joins and add pagination

### 5. **POST /api/v1/teacher/lectures/{id}/test-quiz** ⚠️ MEDIUM
- **Response Time**: 2.1 seconds
- **Recommendation**: Check quiz creation query optimization

## 🔧 Database Optimization Required

### Missing Indexes (High Priority)
```sql
-- For unread notification count queries
CREATE INDEX idx_notification_user_read_archived ON notification(user_id, is_read, is_archived);
CREATE INDEX idx_notification_user_id ON notification(user_id);

-- For lecture queries
CREATE INDEX idx_lecture_teacher_id ON lecture(teacher_id);
CREATE INDEX idx_lecture_course_id ON lecture(course_id);

-- For assessment queries
CREATE INDEX idx_assessment_teacher_id ON assessment(teacher_id);
CREATE INDEX idx_assessment_lecture_id ON assessment(lecture_id);
CREATE INDEX idx_question_assessment_id ON question(assessment_id);
CREATE INDEX idx_assessment_submission_assessment_id ON assessment_submission(assessment_id);

-- For course queries
CREATE INDEX idx_course_teacher_id ON course(created_by_teacher_id);
CREATE INDEX idx_course_teacher_assignment ON course_teacher(teacher_id, is_active);
```

## 📈 Proposed Solution

### Phase 1: Add Performance Monitoring (IMMEDIATE)
- Deploy performance decorator to all endpoints
- Log query execution times
- Identify exact slow queries
- Set up alerts for slow requests

### Phase 2: Quick Wins (1-2 days)
- Add database indexes
- Implement Redis caching for unread-count
- Batch queries where possible
- Reduce UI polling frequency

### Phase 3: Major Optimization (3-5 days)
- Refactor N+1 queries
- Optimize complex endpoints
- Implement query pagination
- Add query result caching

## 💡 Caching Strategy

### Short-lived Cache (< 30 seconds)
- `/unread-count` → 5-10 second cache per user
- Dashboard stats → 15-30 second cache

### Medium-lived Cache (1-5 minutes)
- Course lists → 2 minute cache
- Course full details → 2 minute cache

### Long-lived Cache (5+ minutes)
- Course structure → 5 minute cache
- Lecture metadata → 5 minute cache

## 📋 Action Items Ordered by Priority

1. ✅ **Deploy performance monitoring middleware** - Track all queries
2. ✅ **Add database indexes** - Biggest immediate performance gain
3. ✅ **Cache unread-count** - Most frequently called endpoint
4. ✅ **Implement query batching** - Eliminate N+1 patterns
5. ✅ **Add connection pooling** - If not already done
6. ✅ **Optimize Supabase queries** - Use proper joins instead of sequential calls
7. ✅ **Implement query result pagination** - For list endpoints
8. ✅ **Add frontend rate limiting** - Reduce polling frequency
