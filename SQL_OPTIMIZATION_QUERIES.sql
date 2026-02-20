# SQL_OPTIMIZATION_QUERIES.sql

-- ============================================================================
-- DATABASE OPTIMIZATION SCRIPT FOR AITA PLATFORM
-- ============================================================================
-- 
-- INSTRUCTIONS:
-- 1. Copy all CREATE INDEX queries from this file
-- 2. Go to Supabase Dashboard → SQL Editor
-- 3. Paste and run each query
-- 4. Verify index appears in "Indexes" tab of each table
--
-- PRIORITY: Run all queries before investigating other performance issues
-- Expected improvement: 50-70% reduction in response time for slow endpoints
-- ============================================================================

-- ============================================================================
-- CRITICAL PRIORITY: Fix unread-count endpoint (2-3 second responses)
-- ============================================================================

-- This is your MOST called and SLOWEST endpoint
-- Adding this single index should drop response time from 1-3s to < 100ms
CREATE INDEX IF NOT EXISTS idx_notification_user_read_archived 
ON notification(user_id, is_read, is_archived);

-- Alternative simpler index if above doesn't help
CREATE INDEX IF NOT EXISTS idx_notification_user_id 
ON notification(user_id);

-- For faster count queries on archived notifications
CREATE INDEX IF NOT EXISTS idx_notification_user_archived 
ON notification(user_id, is_archived);

-- ============================================================================
-- HIGH PRIORITY: Fix assessments endpoints (1.5-5 second responses)
-- ============================================================================

-- For get_all_teacher_assessments endpoint
CREATE INDEX IF NOT EXISTS idx_assessment_teacher_id 
ON assessment(teacher_id);

-- For lecture-based queries
CREATE INDEX IF NOT EXISTS idx_assessment_lecture_id 
ON assessment(lecture_id);

-- For combined teacher + status queries
CREATE INDEX IF NOT EXISTS idx_assessment_teacher_status 
ON assessment(teacher_id, is_published);

-- For questions by assessment
CREATE INDEX IF NOT EXISTS idx_question_assessment_id 
ON question(assessment_id);

-- For quiz submissions queries
CREATE INDEX IF NOT EXISTS idx_assessment_submission_assessment_id 
ON assessment_submission(assessment_id);

-- For counting student submissions
CREATE INDEX IF NOT EXISTS idx_assessment_submission_student 
ON assessment_submission(student_id, assessment_id);

-- ============================================================================
-- HIGH PRIORITY: Fix lecture and course endpoints
-- ============================================================================

-- For get_all_teacher_assessments (fetches all lectures)
CREATE INDEX IF NOT EXISTS idx_lecture_teacher_id 
ON lecture(teacher_id);

-- For course-to-lecture relationships
CREATE INDEX IF NOT EXISTS idx_lecture_course_id 
ON lecture(course_id);

-- For teacher course access
CREATE INDEX IF NOT EXISTS idx_lecture_teacher_course 
ON lecture(teacher_id, course_id);

-- For course queries
CREATE INDEX IF NOT EXISTS idx_course_teacher_created_by 
ON course(created_by_teacher_id);

-- For course-teacher assignments
CREATE INDEX IF NOT EXISTS idx_course_teacher_assignment 
ON course_teacher(teacher_id, is_active);

-- For course-teacher by course side
CREATE INDEX IF NOT EXISTS idx_course_teacher_course_active 
ON course_teacher(course_id, is_active);

-- ============================================================================
-- MEDIUM PRIORITY: Optimize other common queries
-- ============================================================================

-- For enrollment queries
CREATE INDEX IF NOT EXISTS idx_enrollment_student_course 
ON enrollment(student_id, course_id);

-- For active enrollments
CREATE INDEX IF NOT EXISTS idx_enrollment_course_active 
ON enrollment(course_id, status);

-- For lecture embedding lookups
CREATE INDEX IF NOT EXISTS idx_lecture_embedding_lecture_id 
ON lecture_embedding(lecture_id);

-- For document queries
CREATE INDEX IF NOT EXISTS idx_document_course_id 
ON document(course_id);

-- For AI conversation tracking
CREATE INDEX IF NOT EXISTS idx_ai_conversation_user_id 
ON ai_conversation(user_id);

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Run these to verify indexes were created successfully

-- Check all indexes on notification table
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'notification' 
ORDER BY indexname;

-- Check all indexes on assessment table
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'assessment' 
ORDER BY indexname;

-- Check all indexes on lecture table
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'lecture' 
ORDER BY indexname;

-- ============================================================================
-- PERFORMANCE QUERY ANALYSIS
-- ============================================================================
-- Use these to verify query performance after adding indexes

-- Test notification count query (should now be < 50ms)
-- Before: ~2000ms, After: ~20-50ms
EXPLAIN ANALYZE
SELECT COUNT(*) 
FROM notification 
WHERE user_id = 'YOUR_USER_ID'
AND is_read = false 
AND is_archived = false;

-- Test assessment listing (should now be < 500ms)
-- Before: ~1500ms, After: ~100-300ms
EXPLAIN ANALYZE
SELECT * 
FROM assessment 
WHERE teacher_id = 'YOUR_TEACHER_ID'
ORDER BY created_at DESC 
LIMIT 20;

-- ============================================================================
-- STATS ANALYSIS
-- ============================================================================
-- Update table statistics for query planner optimization

ANALYZE notification;
ANALYZE assessment;
ANALYZE lecture;
ANALYZE course;
ANALYZE course_teacher;
ANALYZE enrollment;
ANALYZE lecture_embedding;
ANALYZE document;
ANALYZE ai_conversation;

-- ============================================================================
-- POST-OPTIMIZATION VERIFICATION
-- ============================================================================
-- After running all indexes, run these checks

-- 1. Verify index sizes (should be reasonable)
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_indexes pg
JOIN pg_class c ON c.relname = indexname
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;

-- 2. Check for unused indexes (these might be redundant)
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as num_scans
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan ASC;

-- 3. Monitor index creation progress (for large tables)
-- Note: Run this while indexes are being created
SELECT * FROM pg_stat_activity 
WHERE state = 'active' AND query LIKE '%CREATE INDEX%';

-- ============================================================================
-- TROUBLESHOOTING
-- ============================================================================

-- If a query is still slow after adding index:

-- 1. Check if index is actually being used
EXPLAIN (ANALYZE, BUFFERS) 
SELECT COUNT(*) FROM notification 
WHERE user_id = 'USER_ID' 
AND is_read = false 
AND is_archived = false;
-- Look for "Index" in output. If sees "Seq Scan" instead, index not used.

-- 2. Rebuild index if it's bloated
REINDEX INDEX idx_notification_user_read_archived;

-- 3. Check table statistics
SELECT 
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables 
WHERE relname = 'notification';

-- 4. Force ANALYZE to update statistics
ANALYZE notification;

-- ============================================================================
-- DROP OLD INDEXES (if needed to clean up)
-- ============================================================================
-- Only run if you need to remove an index

-- DROP INDEX IF EXISTS old_index_name;

-- ============================================================================
-- EXPECTED IMPROVEMENTS
-- ============================================================================
-- After implementing all indexes:
--
-- GET /api/v1/notifications/unread-count
--   Before: 2000-3200ms (called very frequently)
--   After: 20-100ms (with caching, < 50ms)
--   Improvement: ~30-60x faster ✅
--
-- GET /api/v1/teacher/assessments/all
--   Before: 1500-2600ms
--   After: 200-500ms
--   Improvement: 3-8x faster ✅
--
-- GET /api/v1/teacher/assessments/{id}
--   Before: 1100-5400ms
--   After: 200-1000ms
--   Improvement: 5-20x faster ✅
--
-- GET /api/v1/teacher/courses/{id}/full
--   Before: 4300ms+
--   After: 500-1500ms
--   Improvement: 3-10x faster ✅

-- ============================================================================
-- INDEX NAMING CONVENTION
-- ============================================================================
-- All indexes follow this naming pattern:
-- idx_[table]_[columns]_[optional_qualifier]
--
-- Examples:
-- idx_notifications_user_read_archived - composite index on 3 columns
-- idx_lecture_teacher_id - single column index
-- idx_assessment_teacher_status - composite index with status qualifier

-- ============================================================================
-- CREATION DATE AND NOTES
-- ============================================================================
-- Created: 2026-02-19
-- For: AITeacherAssistant Platform
-- Priority: HIGH - Execute ASAP for immediate 3-10x performance improvement
-- Estimated execution time: 2-5 minutes
-- ============================================================================
