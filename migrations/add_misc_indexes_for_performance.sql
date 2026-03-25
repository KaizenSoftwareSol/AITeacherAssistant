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
-- ============================================================================


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

-- For user queries (if not exist)
CREATE INDEX  IF NOT EXISTS  idx_user_email ON users(email);

-- ============================================================================
-- MEDIUM PRIORITY: Optimize other common queries
-- ============================================================================

-- For enrollment queries
CREATE INDEX IF NOT EXISTS idx_enrollment_student_course 
ON enrollment(student_id, course_id);

-- For active enrollments
CREATE INDEX IF NOT EXISTS idx_enrollment_course_active 
ON enrollment(course_id, is_active);

-- For lecture embedding lookups
CREATE INDEX IF NOT EXISTS idx_lecture_embedding_lecture_id 
ON lecture_embedding(lecture_id);

-- For document queries
CREATE INDEX IF NOT EXISTS idx_documents_teacher_id 
ON documents(teacher_id);
CREATE INDEX IF NOT EXISTS idx_documents_university_id
ON documents(university_id);

-- For AI conversation tracking
CREATE INDEX IF NOT EXISTS idx_ai_conversation_user_id 
ON ai_conversation(user_id);
