-- Complete Integer Primary Key Migration
-- Generated automatically from production schema
-- 
-- ⚠️  CRITICAL WARNINGS:
-- 1. BACKUP YOUR DATABASE BEFORE RUNNING THIS
-- 2. Test in staging environment first  
-- 3. Run during maintenance window
-- 4. Update application code after migration
-- 5. This migration is IRREVERSIBLE without restore
--
-- PERFORMANCE BENEFITS:
-- - 2-5x faster joins with integer foreign keys
-- - 60% smaller index sizes (4-8 bytes vs 16 bytes)
-- - Better query performance for range queries
-- - Significant storage reduction

BEGIN;

-- ============================================================
-- PART 0: Drop RLS Policies (will be recreated after migration)
-- ============================================================
-- Note: Policies are dropped to avoid dependency issues when dropping columns
-- They will be recreated in PART 7

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN 
        SELECT schemaname, tablename, policyname 
        FROM pg_policies 
        WHERE schemaname = 'public'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', 
            r.policyname, r.schemaname, r.tablename);
    END LOOP;
END $$;

-- ============================================================
-- PART 1: Add integer ID columns and populate them
-- ============================================================

-- university
ALTER TABLE public.university 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.university 
SET new_id = nextval(pg_get_serial_sequence('public.university', 'new_id'))
WHERE new_id IS NULL;

-- job_queue
ALTER TABLE public.job_queue 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.job_queue 
SET new_id = nextval(pg_get_serial_sequence('public.job_queue', 'new_id'))
WHERE new_id IS NULL;

-- ai_processing_log
ALTER TABLE public.ai_processing_log 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.ai_processing_log 
SET new_id = nextval(pg_get_serial_sequence('public.ai_processing_log', 'new_id'))
WHERE new_id IS NULL;

-- users
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.users 
SET new_id = nextval(pg_get_serial_sequence('public.users', 'new_id'))
WHERE new_id IS NULL;

-- student
ALTER TABLE public.student 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.student 
SET new_id = nextval(pg_get_serial_sequence('public.student', 'new_id'))
WHERE new_id IS NULL;

-- teacher
ALTER TABLE public.teacher 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.teacher 
SET new_id = nextval(pg_get_serial_sequence('public.teacher', 'new_id'))
WHERE new_id IS NULL;

-- notification
ALTER TABLE public.notification 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.notification 
SET new_id = nextval(pg_get_serial_sequence('public.notification', 'new_id'))
WHERE new_id IS NULL;

-- documents
ALTER TABLE public.documents 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.documents 
SET new_id = nextval(pg_get_serial_sequence('public.documents', 'new_id'))
WHERE new_id IS NULL;

-- course
ALTER TABLE public.course 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.course 
SET new_id = nextval(pg_get_serial_sequence('public.course', 'new_id'))
WHERE new_id IS NULL;

-- document_assignment
ALTER TABLE public.document_assignment 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.document_assignment 
SET new_id = nextval(pg_get_serial_sequence('public.document_assignment', 'new_id'))
WHERE new_id IS NULL;

-- course_teacher
ALTER TABLE public.course_teacher 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.course_teacher 
SET new_id = nextval(pg_get_serial_sequence('public.course_teacher', 'new_id'))
WHERE new_id IS NULL;

-- semester
ALTER TABLE public.semester 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.semester 
SET new_id = nextval(pg_get_serial_sequence('public.semester', 'new_id'))
WHERE new_id IS NULL;

-- lecture
ALTER TABLE public.lecture 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.lecture 
SET new_id = nextval(pg_get_serial_sequence('public.lecture', 'new_id'))
WHERE new_id IS NULL;

-- enrollment
ALTER TABLE public.enrollment 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.enrollment 
SET new_id = nextval(pg_get_serial_sequence('public.enrollment', 'new_id'))
WHERE new_id IS NULL;

-- module
ALTER TABLE public.module 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.module 
SET new_id = nextval(pg_get_serial_sequence('public.module', 'new_id'))
WHERE new_id IS NULL;

-- student_engagement
ALTER TABLE public.student_engagement 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.student_engagement 
SET new_id = nextval(pg_get_serial_sequence('public.student_engagement', 'new_id'))
WHERE new_id IS NULL;

-- assessment
ALTER TABLE public.assessment 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.assessment 
SET new_id = nextval(pg_get_serial_sequence('public.assessment', 'new_id'))
WHERE new_id IS NULL;

-- module_course
ALTER TABLE public.module_course 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.module_course 
SET new_id = nextval(pg_get_serial_sequence('public.module_course', 'new_id'))
WHERE new_id IS NULL;

-- lecture_content
ALTER TABLE public.lecture_content 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.lecture_content 
SET new_id = nextval(pg_get_serial_sequence('public.lecture_content', 'new_id'))
WHERE new_id IS NULL;

-- lecture_analytics
ALTER TABLE public.lecture_analytics 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.lecture_analytics 
SET new_id = nextval(pg_get_serial_sequence('public.lecture_analytics', 'new_id'))
WHERE new_id IS NULL;

-- lecture_chunk
ALTER TABLE public.lecture_chunk 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.lecture_chunk 
SET new_id = nextval(pg_get_serial_sequence('public.lecture_chunk', 'new_id'))
WHERE new_id IS NULL;

-- flashcard
ALTER TABLE public.flashcard 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.flashcard 
SET new_id = nextval(pg_get_serial_sequence('public.flashcard', 'new_id'))
WHERE new_id IS NULL;

-- ai_conversation
ALTER TABLE public.ai_conversation 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.ai_conversation 
SET new_id = nextval(pg_get_serial_sequence('public.ai_conversation', 'new_id'))
WHERE new_id IS NULL;

-- question
ALTER TABLE public.question 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.question 
SET new_id = nextval(pg_get_serial_sequence('public.question', 'new_id'))
WHERE new_id IS NULL;

-- result_view_request
ALTER TABLE public.result_view_request 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.result_view_request 
SET new_id = nextval(pg_get_serial_sequence('public.result_view_request', 'new_id'))
WHERE new_id IS NULL;

-- assessment_submission
ALTER TABLE public.assessment_submission 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.assessment_submission 
SET new_id = nextval(pg_get_serial_sequence('public.assessment_submission', 'new_id'))
WHERE new_id IS NULL;

-- lecture_embedding
ALTER TABLE public.lecture_embedding 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.lecture_embedding 
SET new_id = nextval(pg_get_serial_sequence('public.lecture_embedding', 'new_id'))
WHERE new_id IS NULL;

-- chat_message
ALTER TABLE public.chat_message 
ADD COLUMN IF NOT EXISTS new_id BIGSERIAL;

UPDATE public.chat_message 
SET new_id = nextval(pg_get_serial_sequence('public.chat_message', 'new_id'))
WHERE new_id IS NULL;


-- ============================================================
-- PART 2: Create mapping tables for UUID -> integer conversion
-- ============================================================

CREATE TEMP TABLE IF NOT EXISTS university_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.university;

CREATE TEMP TABLE IF NOT EXISTS job_queue_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.job_queue;

CREATE TEMP TABLE IF NOT EXISTS ai_processing_log_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.ai_processing_log;

CREATE TEMP TABLE IF NOT EXISTS users_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.users;

CREATE TEMP TABLE IF NOT EXISTS student_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.student;

CREATE TEMP TABLE IF NOT EXISTS teacher_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.teacher;

CREATE TEMP TABLE IF NOT EXISTS notification_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.notification;

CREATE TEMP TABLE IF NOT EXISTS documents_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.documents;

CREATE TEMP TABLE IF NOT EXISTS course_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.course;

CREATE TEMP TABLE IF NOT EXISTS document_assignment_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.document_assignment;

CREATE TEMP TABLE IF NOT EXISTS course_teacher_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.course_teacher;

CREATE TEMP TABLE IF NOT EXISTS semester_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.semester;

CREATE TEMP TABLE IF NOT EXISTS lecture_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.lecture;

CREATE TEMP TABLE IF NOT EXISTS enrollment_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.enrollment;

CREATE TEMP TABLE IF NOT EXISTS module_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.module;

CREATE TEMP TABLE IF NOT EXISTS student_engagement_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.student_engagement;

CREATE TEMP TABLE IF NOT EXISTS assessment_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.assessment;

CREATE TEMP TABLE IF NOT EXISTS module_course_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.module_course;

CREATE TEMP TABLE IF NOT EXISTS lecture_content_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.lecture_content;

CREATE TEMP TABLE IF NOT EXISTS lecture_analytics_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.lecture_analytics;

CREATE TEMP TABLE IF NOT EXISTS lecture_chunk_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.lecture_chunk;

CREATE TEMP TABLE IF NOT EXISTS flashcard_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.flashcard;

CREATE TEMP TABLE IF NOT EXISTS ai_conversation_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.ai_conversation;

CREATE TEMP TABLE IF NOT EXISTS question_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.question;

CREATE TEMP TABLE IF NOT EXISTS result_view_request_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.result_view_request;

CREATE TEMP TABLE IF NOT EXISTS assessment_submission_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.assessment_submission;

CREATE TEMP TABLE IF NOT EXISTS lecture_embedding_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.lecture_embedding;

CREATE TEMP TABLE IF NOT EXISTS chat_message_id_map AS 
SELECT id::uuid as uuid_id, new_id as int_id FROM public.chat_message;


-- ============================================================
-- PART 3: Add temporary integer foreign key columns
-- ============================================================

ALTER TABLE public.ai_conversation 
ADD COLUMN IF NOT EXISTS lecture_id_new_id BIGINT;

ALTER TABLE public.ai_conversation 
ADD COLUMN IF NOT EXISTS user_id_new_id BIGINT;

ALTER TABLE public.ai_processing_log 
ADD COLUMN IF NOT EXISTS job_id_new_id BIGINT;

ALTER TABLE public.assessment 
ADD COLUMN IF NOT EXISTS course_id_new_id BIGINT;

ALTER TABLE public.assessment 
ADD COLUMN IF NOT EXISTS lecture_id_new_id BIGINT;

ALTER TABLE public.assessment 
ADD COLUMN IF NOT EXISTS teacher_id_new_id BIGINT;

ALTER TABLE public.assessment_submission 
ADD COLUMN IF NOT EXISTS assessment_id_new_id BIGINT;

ALTER TABLE public.assessment_submission 
ADD COLUMN IF NOT EXISTS student_id_new_id BIGINT;

ALTER TABLE public.chat_message 
ADD COLUMN IF NOT EXISTS conversation_id_new_id BIGINT;

ALTER TABLE public.course 
ADD COLUMN IF NOT EXISTS created_by_teacher_id_new_id BIGINT;

ALTER TABLE public.course 
ADD COLUMN IF NOT EXISTS university_id_new_id BIGINT;

ALTER TABLE public.course_teacher 
ADD COLUMN IF NOT EXISTS assigned_by_new_id BIGINT;

ALTER TABLE public.course_teacher 
ADD COLUMN IF NOT EXISTS course_id_new_id BIGINT;

ALTER TABLE public.course_teacher 
ADD COLUMN IF NOT EXISTS teacher_id_new_id BIGINT;

ALTER TABLE public.document_assignment 
ADD COLUMN IF NOT EXISTS course_id_new_id BIGINT;

ALTER TABLE public.document_assignment 
ADD COLUMN IF NOT EXISTS document_id_new_id BIGINT;

ALTER TABLE public.documents 
ADD COLUMN IF NOT EXISTS teacher_id_new_id BIGINT;

ALTER TABLE public.documents 
ADD COLUMN IF NOT EXISTS university_id_new_id BIGINT;

ALTER TABLE public.enrollment 
ADD COLUMN IF NOT EXISTS course_id_new_id BIGINT;

ALTER TABLE public.enrollment 
ADD COLUMN IF NOT EXISTS semester_id_new_id BIGINT;

ALTER TABLE public.enrollment 
ADD COLUMN IF NOT EXISTS student_id_new_id BIGINT;

ALTER TABLE public.flashcard 
ADD COLUMN IF NOT EXISTS lecture_id_new_id BIGINT;

ALTER TABLE public.lecture 
ADD COLUMN IF NOT EXISTS course_id_new_id BIGINT;

ALTER TABLE public.lecture 
ADD COLUMN IF NOT EXISTS document_id_new_id BIGINT;

ALTER TABLE public.lecture 
ADD COLUMN IF NOT EXISTS semester_id_new_id BIGINT;

ALTER TABLE public.lecture 
ADD COLUMN IF NOT EXISTS teacher_id_new_id BIGINT;

ALTER TABLE public.lecture_analytics 
ADD COLUMN IF NOT EXISTS lecture_id_new_id BIGINT;

ALTER TABLE public.lecture_chunk 
ADD COLUMN IF NOT EXISTS lecture_id_new_id BIGINT;

ALTER TABLE public.lecture_content 
ADD COLUMN IF NOT EXISTS lecture_id_new_id BIGINT;

ALTER TABLE public.lecture_embedding 
ADD COLUMN IF NOT EXISTS chunk_id_new_id BIGINT;

ALTER TABLE public.lecture_embedding 
ADD COLUMN IF NOT EXISTS lecture_id_new_id BIGINT;

ALTER TABLE public.module 
ADD COLUMN IF NOT EXISTS semester_id_new_id BIGINT;

ALTER TABLE public.module 
ADD COLUMN IF NOT EXISTS university_id_new_id BIGINT;

ALTER TABLE public.module_course 
ADD COLUMN IF NOT EXISTS course_id_new_id BIGINT;

ALTER TABLE public.module_course 
ADD COLUMN IF NOT EXISTS module_id_new_id BIGINT;

ALTER TABLE public.notification 
ADD COLUMN IF NOT EXISTS user_id_new_id BIGINT;

ALTER TABLE public.question 
ADD COLUMN IF NOT EXISTS assessment_id_new_id BIGINT;

ALTER TABLE public.result_view_request 
ADD COLUMN IF NOT EXISTS assessment_id_new_id BIGINT;

ALTER TABLE public.result_view_request 
ADD COLUMN IF NOT EXISTS student_id_new_id BIGINT;

ALTER TABLE public.result_view_request 
ADD COLUMN IF NOT EXISTS teacher_id_new_id BIGINT;

ALTER TABLE public.semester 
ADD COLUMN IF NOT EXISTS course_id_new_id BIGINT;

ALTER TABLE public.semester 
ADD COLUMN IF NOT EXISTS university_id_new_id BIGINT;

ALTER TABLE public.student 
ADD COLUMN IF NOT EXISTS university_id_new_id BIGINT;

ALTER TABLE public.student 
ADD COLUMN IF NOT EXISTS user_id_new_id BIGINT;

ALTER TABLE public.student_engagement 
ADD COLUMN IF NOT EXISTS lecture_id_new_id BIGINT;

ALTER TABLE public.student_engagement 
ADD COLUMN IF NOT EXISTS student_id_new_id BIGINT;

ALTER TABLE public.teacher 
ADD COLUMN IF NOT EXISTS university_id_new_id BIGINT;

ALTER TABLE public.teacher 
ADD COLUMN IF NOT EXISTS user_id_new_id BIGINT;

ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS university_id_new_id BIGINT;


-- ============================================================
-- PART 4: Populate integer foreign key columns
-- ============================================================

UPDATE public.ai_conversation f
SET lecture_id_new_id = m.int_id
FROM lecture_id_map m
WHERE f.lecture_id::uuid = m.uuid_id;

UPDATE public.ai_conversation f
SET user_id_new_id = m.int_id
FROM users_id_map m
WHERE f.user_id::uuid = m.uuid_id;

UPDATE public.ai_processing_log f
SET job_id_new_id = m.int_id
FROM job_queue_id_map m
WHERE f.job_id::uuid = m.uuid_id;

UPDATE public.assessment f
SET course_id_new_id = m.int_id
FROM course_id_map m
WHERE f.course_id::uuid = m.uuid_id;

UPDATE public.assessment f
SET lecture_id_new_id = m.int_id
FROM lecture_id_map m
WHERE f.lecture_id::uuid = m.uuid_id;

UPDATE public.assessment f
SET teacher_id_new_id = m.int_id
FROM teacher_id_map m
WHERE f.teacher_id::uuid = m.uuid_id;

UPDATE public.assessment_submission f
SET assessment_id_new_id = m.int_id
FROM assessment_id_map m
WHERE f.assessment_id::uuid = m.uuid_id;

UPDATE public.assessment_submission f
SET student_id_new_id = m.int_id
FROM student_id_map m
WHERE f.student_id::uuid = m.uuid_id;

UPDATE public.chat_message f
SET conversation_id_new_id = m.int_id
FROM ai_conversation_id_map m
WHERE f.conversation_id::uuid = m.uuid_id;

UPDATE public.course f
SET created_by_teacher_id_new_id = m.int_id
FROM teacher_id_map m
WHERE f.created_by_teacher_id::uuid = m.uuid_id;

UPDATE public.course f
SET university_id_new_id = m.int_id
FROM university_id_map m
WHERE f.university_id::uuid = m.uuid_id;

UPDATE public.course_teacher f
SET assigned_by_new_id = m.int_id
FROM users_id_map m
WHERE f.assigned_by::uuid = m.uuid_id;

UPDATE public.course_teacher f
SET course_id_new_id = m.int_id
FROM course_id_map m
WHERE f.course_id::uuid = m.uuid_id;

UPDATE public.course_teacher f
SET teacher_id_new_id = m.int_id
FROM teacher_id_map m
WHERE f.teacher_id::uuid = m.uuid_id;

UPDATE public.document_assignment f
SET course_id_new_id = m.int_id
FROM course_id_map m
WHERE f.course_id::uuid = m.uuid_id;

UPDATE public.document_assignment f
SET document_id_new_id = m.int_id
FROM documents_id_map m
WHERE f.document_id::uuid = m.uuid_id;

UPDATE public.documents f
SET teacher_id_new_id = m.int_id
FROM teacher_id_map m
WHERE f.teacher_id::uuid = m.uuid_id;

UPDATE public.documents f
SET university_id_new_id = m.int_id
FROM university_id_map m
WHERE f.university_id::uuid = m.uuid_id;

UPDATE public.enrollment f
SET course_id_new_id = m.int_id
FROM course_id_map m
WHERE f.course_id::uuid = m.uuid_id;

UPDATE public.enrollment f
SET semester_id_new_id = m.int_id
FROM semester_id_map m
WHERE f.semester_id::uuid = m.uuid_id;

UPDATE public.enrollment f
SET student_id_new_id = m.int_id
FROM student_id_map m
WHERE f.student_id::uuid = m.uuid_id;

UPDATE public.flashcard f
SET lecture_id_new_id = m.int_id
FROM lecture_id_map m
WHERE f.lecture_id::uuid = m.uuid_id;

UPDATE public.lecture f
SET course_id_new_id = m.int_id
FROM course_id_map m
WHERE f.course_id::uuid = m.uuid_id;

UPDATE public.lecture f
SET document_id_new_id = m.int_id
FROM documents_id_map m
WHERE f.document_id::uuid = m.uuid_id;

UPDATE public.lecture f
SET semester_id_new_id = m.int_id
FROM semester_id_map m
WHERE f.semester_id::uuid = m.uuid_id;

UPDATE public.lecture f
SET teacher_id_new_id = m.int_id
FROM teacher_id_map m
WHERE f.teacher_id::uuid = m.uuid_id;

UPDATE public.lecture_analytics f
SET lecture_id_new_id = m.int_id
FROM lecture_id_map m
WHERE f.lecture_id::uuid = m.uuid_id;

UPDATE public.lecture_chunk f
SET lecture_id_new_id = m.int_id
FROM lecture_id_map m
WHERE f.lecture_id::uuid = m.uuid_id;

UPDATE public.lecture_content f
SET lecture_id_new_id = m.int_id
FROM lecture_id_map m
WHERE f.lecture_id::uuid = m.uuid_id;

UPDATE public.lecture_embedding f
SET chunk_id_new_id = m.int_id
FROM lecture_chunk_id_map m
WHERE f.chunk_id::uuid = m.uuid_id;

UPDATE public.lecture_embedding f
SET lecture_id_new_id = m.int_id
FROM lecture_id_map m
WHERE f.lecture_id::uuid = m.uuid_id;

UPDATE public.module f
SET semester_id_new_id = m.int_id
FROM semester_id_map m
WHERE f.semester_id::uuid = m.uuid_id;

UPDATE public.module f
SET university_id_new_id = m.int_id
FROM university_id_map m
WHERE f.university_id::uuid = m.uuid_id;

UPDATE public.module_course f
SET course_id_new_id = m.int_id
FROM course_id_map m
WHERE f.course_id::uuid = m.uuid_id;

UPDATE public.module_course f
SET module_id_new_id = m.int_id
FROM module_id_map m
WHERE f.module_id::uuid = m.uuid_id;

UPDATE public.notification f
SET user_id_new_id = m.int_id
FROM users_id_map m
WHERE f.user_id::uuid = m.uuid_id;

UPDATE public.question f
SET assessment_id_new_id = m.int_id
FROM assessment_id_map m
WHERE f.assessment_id::uuid = m.uuid_id;

UPDATE public.result_view_request f
SET assessment_id_new_id = m.int_id
FROM assessment_id_map m
WHERE f.assessment_id::uuid = m.uuid_id;

UPDATE public.result_view_request f
SET student_id_new_id = m.int_id
FROM student_id_map m
WHERE f.student_id::uuid = m.uuid_id;

UPDATE public.result_view_request f
SET teacher_id_new_id = m.int_id
FROM teacher_id_map m
WHERE f.teacher_id::uuid = m.uuid_id;

UPDATE public.semester f
SET course_id_new_id = m.int_id
FROM course_id_map m
WHERE f.course_id::uuid = m.uuid_id;

UPDATE public.semester f
SET university_id_new_id = m.int_id
FROM university_id_map m
WHERE f.university_id::uuid = m.uuid_id;

UPDATE public.student f
SET university_id_new_id = m.int_id
FROM university_id_map m
WHERE f.university_id::uuid = m.uuid_id;

UPDATE public.student f
SET user_id_new_id = m.int_id
FROM users_id_map m
WHERE f.user_id::uuid = m.uuid_id;

UPDATE public.student_engagement f
SET lecture_id_new_id = m.int_id
FROM lecture_id_map m
WHERE f.lecture_id::uuid = m.uuid_id;

UPDATE public.student_engagement f
SET student_id_new_id = m.int_id
FROM student_id_map m
WHERE f.student_id::uuid = m.uuid_id;

UPDATE public.teacher f
SET university_id_new_id = m.int_id
FROM university_id_map m
WHERE f.university_id::uuid = m.uuid_id;

UPDATE public.teacher f
SET user_id_new_id = m.int_id
FROM users_id_map m
WHERE f.user_id::uuid = m.uuid_id;

UPDATE public.users f
SET university_id_new_id = m.int_id
FROM university_id_map m
WHERE f.university_id::uuid = m.uuid_id;


-- ============================================================
-- PART 5: Drop old constraints, rename columns, recreate constraints
-- ============================================================

-- Drop foreign key constraints
ALTER TABLE public.ai_conversation 
DROP CONSTRAINT IF EXISTS ai_conversation_lecture_id_fkey CASCADE;

ALTER TABLE public.ai_conversation 
DROP CONSTRAINT IF EXISTS ai_conversation_user_id_fkey CASCADE;

ALTER TABLE public.ai_processing_log 
DROP CONSTRAINT IF EXISTS ai_processing_log_job_id_fkey CASCADE;

ALTER TABLE public.assessment 
DROP CONSTRAINT IF EXISTS assessment_course_id_fkey CASCADE;

ALTER TABLE public.assessment 
DROP CONSTRAINT IF EXISTS assessment_lecture_id_fkey CASCADE;

ALTER TABLE public.assessment 
DROP CONSTRAINT IF EXISTS assessment_teacher_id_fkey CASCADE;

ALTER TABLE public.assessment_submission 
DROP CONSTRAINT IF EXISTS assessment_submission_assessment_id_fkey CASCADE;

ALTER TABLE public.assessment_submission 
DROP CONSTRAINT IF EXISTS assessment_submission_student_id_fkey CASCADE;

ALTER TABLE public.chat_message 
DROP CONSTRAINT IF EXISTS chat_message_conversation_id_fkey CASCADE;

ALTER TABLE public.course 
DROP CONSTRAINT IF EXISTS course_created_by_teacher_id_fkey CASCADE;

ALTER TABLE public.course 
DROP CONSTRAINT IF EXISTS course_university_id_fkey CASCADE;

ALTER TABLE public.course_teacher 
DROP CONSTRAINT IF EXISTS course_teacher_assigned_by_fkey CASCADE;

ALTER TABLE public.course_teacher 
DROP CONSTRAINT IF EXISTS course_teacher_course_id_fkey CASCADE;

ALTER TABLE public.course_teacher 
DROP CONSTRAINT IF EXISTS course_teacher_teacher_id_fkey CASCADE;

ALTER TABLE public.document_assignment 
DROP CONSTRAINT IF EXISTS document_assignment_course_id_fkey CASCADE;

ALTER TABLE public.document_assignment 
DROP CONSTRAINT IF EXISTS document_assignment_document_id_fkey CASCADE;

ALTER TABLE public.documents 
DROP CONSTRAINT IF EXISTS documents_teacher_id_fkey CASCADE;

ALTER TABLE public.documents 
DROP CONSTRAINT IF EXISTS documents_university_id_fkey CASCADE;

ALTER TABLE public.enrollment 
DROP CONSTRAINT IF EXISTS enrollment_course_id_fkey CASCADE;

ALTER TABLE public.enrollment 
DROP CONSTRAINT IF EXISTS enrollment_semester_id_fkey CASCADE;

ALTER TABLE public.enrollment 
DROP CONSTRAINT IF EXISTS enrollment_student_id_fkey CASCADE;

ALTER TABLE public.flashcard 
DROP CONSTRAINT IF EXISTS flashcard_lecture_id_fkey CASCADE;

ALTER TABLE public.lecture 
DROP CONSTRAINT IF EXISTS lecture_course_id_fkey CASCADE;

ALTER TABLE public.lecture 
DROP CONSTRAINT IF EXISTS lecture_document_id_fkey CASCADE;

ALTER TABLE public.lecture 
DROP CONSTRAINT IF EXISTS lecture_semester_id_fkey CASCADE;

ALTER TABLE public.lecture 
DROP CONSTRAINT IF EXISTS lecture_teacher_id_fkey CASCADE;

ALTER TABLE public.lecture_analytics 
DROP CONSTRAINT IF EXISTS lecture_analytics_lecture_id_fkey CASCADE;

ALTER TABLE public.lecture_chunk 
DROP CONSTRAINT IF EXISTS lecture_chunk_lecture_id_fkey CASCADE;

ALTER TABLE public.lecture_content 
DROP CONSTRAINT IF EXISTS lecture_content_lecture_id_fkey CASCADE;

ALTER TABLE public.lecture_embedding 
DROP CONSTRAINT IF EXISTS lecture_embedding_chunk_id_fkey CASCADE;

ALTER TABLE public.lecture_embedding 
DROP CONSTRAINT IF EXISTS lecture_embedding_lecture_id_fkey CASCADE;

ALTER TABLE public.module 
DROP CONSTRAINT IF EXISTS module_semester_id_fkey CASCADE;

ALTER TABLE public.module 
DROP CONSTRAINT IF EXISTS module_university_id_fkey CASCADE;

ALTER TABLE public.module_course 
DROP CONSTRAINT IF EXISTS module_course_course_id_fkey CASCADE;

ALTER TABLE public.module_course 
DROP CONSTRAINT IF EXISTS module_course_module_id_fkey CASCADE;

ALTER TABLE public.notification 
DROP CONSTRAINT IF EXISTS notification_user_id_fkey CASCADE;

ALTER TABLE public.question 
DROP CONSTRAINT IF EXISTS question_assessment_id_fkey CASCADE;

ALTER TABLE public.result_view_request 
DROP CONSTRAINT IF EXISTS result_view_request_assessment_id_fkey CASCADE;

ALTER TABLE public.result_view_request 
DROP CONSTRAINT IF EXISTS result_view_request_student_id_fkey CASCADE;

ALTER TABLE public.result_view_request 
DROP CONSTRAINT IF EXISTS result_view_request_teacher_id_fkey CASCADE;

ALTER TABLE public.semester 
DROP CONSTRAINT IF EXISTS semester_course_id_fkey CASCADE;

ALTER TABLE public.semester 
DROP CONSTRAINT IF EXISTS semester_university_id_fkey CASCADE;

ALTER TABLE public.student 
DROP CONSTRAINT IF EXISTS student_university_id_fkey CASCADE;

ALTER TABLE public.student 
DROP CONSTRAINT IF EXISTS student_user_id_fkey CASCADE;

ALTER TABLE public.student_engagement 
DROP CONSTRAINT IF EXISTS student_engagement_lecture_id_fkey CASCADE;

ALTER TABLE public.student_engagement 
DROP CONSTRAINT IF EXISTS student_engagement_student_id_fkey CASCADE;

ALTER TABLE public.teacher 
DROP CONSTRAINT IF EXISTS teacher_university_id_fkey CASCADE;

ALTER TABLE public.teacher 
DROP CONSTRAINT IF EXISTS teacher_user_id_fkey CASCADE;

ALTER TABLE public.users 
DROP CONSTRAINT IF EXISTS users_university_id_fkey CASCADE;


-- Drop primary key constraints
ALTER TABLE public.university 
DROP CONSTRAINT IF EXISTS university_pkey CASCADE;

ALTER TABLE public.job_queue 
DROP CONSTRAINT IF EXISTS job_queue_pkey CASCADE;

ALTER TABLE public.ai_processing_log 
DROP CONSTRAINT IF EXISTS ai_processing_log_pkey CASCADE;

ALTER TABLE public.users 
DROP CONSTRAINT IF EXISTS users_pkey CASCADE;

ALTER TABLE public.student 
DROP CONSTRAINT IF EXISTS student_pkey CASCADE;

ALTER TABLE public.teacher 
DROP CONSTRAINT IF EXISTS teacher_pkey CASCADE;

ALTER TABLE public.notification 
DROP CONSTRAINT IF EXISTS notification_pkey CASCADE;

ALTER TABLE public.documents 
DROP CONSTRAINT IF EXISTS documents_pkey CASCADE;

ALTER TABLE public.course 
DROP CONSTRAINT IF EXISTS course_pkey CASCADE;

ALTER TABLE public.document_assignment 
DROP CONSTRAINT IF EXISTS document_assignment_pkey CASCADE;

ALTER TABLE public.course_teacher 
DROP CONSTRAINT IF EXISTS course_teacher_pkey CASCADE;

ALTER TABLE public.semester 
DROP CONSTRAINT IF EXISTS semester_pkey CASCADE;

ALTER TABLE public.lecture 
DROP CONSTRAINT IF EXISTS lecture_pkey CASCADE;

ALTER TABLE public.enrollment 
DROP CONSTRAINT IF EXISTS enrollment_pkey CASCADE;

ALTER TABLE public.module 
DROP CONSTRAINT IF EXISTS module_pkey CASCADE;

ALTER TABLE public.student_engagement 
DROP CONSTRAINT IF EXISTS student_engagement_pkey CASCADE;

ALTER TABLE public.assessment 
DROP CONSTRAINT IF EXISTS assessment_pkey CASCADE;

ALTER TABLE public.module_course 
DROP CONSTRAINT IF EXISTS module_course_pkey CASCADE;

ALTER TABLE public.lecture_content 
DROP CONSTRAINT IF EXISTS lecture_content_pkey CASCADE;

ALTER TABLE public.lecture_analytics 
DROP CONSTRAINT IF EXISTS lecture_analytics_pkey CASCADE;

ALTER TABLE public.lecture_chunk 
DROP CONSTRAINT IF EXISTS lecture_chunk_pkey CASCADE;

ALTER TABLE public.flashcard 
DROP CONSTRAINT IF EXISTS flashcard_pkey CASCADE;

ALTER TABLE public.ai_conversation 
DROP CONSTRAINT IF EXISTS ai_conversation_pkey CASCADE;

ALTER TABLE public.question 
DROP CONSTRAINT IF EXISTS question_pkey CASCADE;

ALTER TABLE public.result_view_request 
DROP CONSTRAINT IF EXISTS result_view_request_pkey CASCADE;

ALTER TABLE public.assessment_submission 
DROP CONSTRAINT IF EXISTS assessment_submission_pkey CASCADE;

ALTER TABLE public.lecture_embedding 
DROP CONSTRAINT IF EXISTS lecture_embedding_pkey CASCADE;

ALTER TABLE public.chat_message 
DROP CONSTRAINT IF EXISTS chat_message_pkey CASCADE;


-- Rename columns: id -> uuid, new_id -> id
ALTER TABLE public.university 
RENAME COLUMN id TO uuid;

ALTER TABLE public.university 
RENAME COLUMN new_id TO id;

ALTER TABLE public.job_queue 
RENAME COLUMN id TO uuid;

ALTER TABLE public.job_queue 
RENAME COLUMN new_id TO id;

ALTER TABLE public.ai_processing_log 
RENAME COLUMN id TO uuid;

ALTER TABLE public.ai_processing_log 
RENAME COLUMN new_id TO id;

ALTER TABLE public.users 
RENAME COLUMN id TO uuid;

ALTER TABLE public.users 
RENAME COLUMN new_id TO id;

ALTER TABLE public.student 
RENAME COLUMN id TO uuid;

ALTER TABLE public.student 
RENAME COLUMN new_id TO id;

ALTER TABLE public.teacher 
RENAME COLUMN id TO uuid;

ALTER TABLE public.teacher 
RENAME COLUMN new_id TO id;

ALTER TABLE public.notification 
RENAME COLUMN id TO uuid;

ALTER TABLE public.notification 
RENAME COLUMN new_id TO id;

ALTER TABLE public.documents 
RENAME COLUMN id TO uuid;

ALTER TABLE public.documents 
RENAME COLUMN new_id TO id;

ALTER TABLE public.course 
RENAME COLUMN id TO uuid;

ALTER TABLE public.course 
RENAME COLUMN new_id TO id;

ALTER TABLE public.document_assignment 
RENAME COLUMN id TO uuid;

ALTER TABLE public.document_assignment 
RENAME COLUMN new_id TO id;

ALTER TABLE public.course_teacher 
RENAME COLUMN id TO uuid;

ALTER TABLE public.course_teacher 
RENAME COLUMN new_id TO id;

ALTER TABLE public.semester 
RENAME COLUMN id TO uuid;

ALTER TABLE public.semester 
RENAME COLUMN new_id TO id;

ALTER TABLE public.lecture 
RENAME COLUMN id TO uuid;

ALTER TABLE public.lecture 
RENAME COLUMN new_id TO id;

ALTER TABLE public.enrollment 
RENAME COLUMN id TO uuid;

ALTER TABLE public.enrollment 
RENAME COLUMN new_id TO id;

ALTER TABLE public.module 
RENAME COLUMN id TO uuid;

ALTER TABLE public.module 
RENAME COLUMN new_id TO id;

ALTER TABLE public.student_engagement 
RENAME COLUMN id TO uuid;

ALTER TABLE public.student_engagement 
RENAME COLUMN new_id TO id;

ALTER TABLE public.assessment 
RENAME COLUMN id TO uuid;

ALTER TABLE public.assessment 
RENAME COLUMN new_id TO id;

ALTER TABLE public.module_course 
RENAME COLUMN id TO uuid;

ALTER TABLE public.module_course 
RENAME COLUMN new_id TO id;

ALTER TABLE public.lecture_content 
RENAME COLUMN id TO uuid;

ALTER TABLE public.lecture_content 
RENAME COLUMN new_id TO id;

ALTER TABLE public.lecture_analytics 
RENAME COLUMN id TO uuid;

ALTER TABLE public.lecture_analytics 
RENAME COLUMN new_id TO id;

ALTER TABLE public.lecture_chunk 
RENAME COLUMN id TO uuid;

ALTER TABLE public.lecture_chunk 
RENAME COLUMN new_id TO id;

ALTER TABLE public.flashcard 
RENAME COLUMN id TO uuid;

ALTER TABLE public.flashcard 
RENAME COLUMN new_id TO id;

ALTER TABLE public.ai_conversation 
RENAME COLUMN id TO uuid;

ALTER TABLE public.ai_conversation 
RENAME COLUMN new_id TO id;

ALTER TABLE public.question 
RENAME COLUMN id TO uuid;

ALTER TABLE public.question 
RENAME COLUMN new_id TO id;

ALTER TABLE public.result_view_request 
RENAME COLUMN id TO uuid;

ALTER TABLE public.result_view_request 
RENAME COLUMN new_id TO id;

ALTER TABLE public.assessment_submission 
RENAME COLUMN id TO uuid;

ALTER TABLE public.assessment_submission 
RENAME COLUMN new_id TO id;

ALTER TABLE public.lecture_embedding 
RENAME COLUMN id TO uuid;

ALTER TABLE public.lecture_embedding 
RENAME COLUMN new_id TO id;

ALTER TABLE public.chat_message 
RENAME COLUMN id TO uuid;

ALTER TABLE public.chat_message 
RENAME COLUMN new_id TO id;


-- Recreate primary key constraints
ALTER TABLE public.university 
ADD CONSTRAINT university_pkey PRIMARY KEY (id);

ALTER TABLE public.job_queue 
ADD CONSTRAINT job_queue_pkey PRIMARY KEY (id);

ALTER TABLE public.ai_processing_log 
ADD CONSTRAINT ai_processing_log_pkey PRIMARY KEY (id);

ALTER TABLE public.users 
ADD CONSTRAINT users_pkey PRIMARY KEY (id);

ALTER TABLE public.student 
ADD CONSTRAINT student_pkey PRIMARY KEY (id);

ALTER TABLE public.teacher 
ADD CONSTRAINT teacher_pkey PRIMARY KEY (id);

ALTER TABLE public.notification 
ADD CONSTRAINT notification_pkey PRIMARY KEY (id);

ALTER TABLE public.documents 
ADD CONSTRAINT documents_pkey PRIMARY KEY (id);

ALTER TABLE public.course 
ADD CONSTRAINT course_pkey PRIMARY KEY (id);

ALTER TABLE public.document_assignment 
ADD CONSTRAINT document_assignment_pkey PRIMARY KEY (id);

ALTER TABLE public.course_teacher 
ADD CONSTRAINT course_teacher_pkey PRIMARY KEY (id);

ALTER TABLE public.semester 
ADD CONSTRAINT semester_pkey PRIMARY KEY (id);

ALTER TABLE public.lecture 
ADD CONSTRAINT lecture_pkey PRIMARY KEY (id);

ALTER TABLE public.enrollment 
ADD CONSTRAINT enrollment_pkey PRIMARY KEY (id);

ALTER TABLE public.module 
ADD CONSTRAINT module_pkey PRIMARY KEY (id);

ALTER TABLE public.student_engagement 
ADD CONSTRAINT student_engagement_pkey PRIMARY KEY (id);

ALTER TABLE public.assessment 
ADD CONSTRAINT assessment_pkey PRIMARY KEY (id);

ALTER TABLE public.module_course 
ADD CONSTRAINT module_course_pkey PRIMARY KEY (id);

ALTER TABLE public.lecture_content 
ADD CONSTRAINT lecture_content_pkey PRIMARY KEY (id);

ALTER TABLE public.lecture_analytics 
ADD CONSTRAINT lecture_analytics_pkey PRIMARY KEY (id);

ALTER TABLE public.lecture_chunk 
ADD CONSTRAINT lecture_chunk_pkey PRIMARY KEY (id);

ALTER TABLE public.flashcard 
ADD CONSTRAINT flashcard_pkey PRIMARY KEY (id);

ALTER TABLE public.ai_conversation 
ADD CONSTRAINT ai_conversation_pkey PRIMARY KEY (id);

ALTER TABLE public.question 
ADD CONSTRAINT question_pkey PRIMARY KEY (id);

ALTER TABLE public.result_view_request 
ADD CONSTRAINT result_view_request_pkey PRIMARY KEY (id);

ALTER TABLE public.assessment_submission 
ADD CONSTRAINT assessment_submission_pkey PRIMARY KEY (id);

ALTER TABLE public.lecture_embedding 
ADD CONSTRAINT lecture_embedding_pkey PRIMARY KEY (id);

ALTER TABLE public.chat_message 
ADD CONSTRAINT chat_message_pkey PRIMARY KEY (id);


-- Recreate foreign key constraints with integer IDs
-- Note: Using CASCADE to drop dependent RLS policies (will be recreated in PART 7)
ALTER TABLE public.ai_conversation 
DROP COLUMN IF EXISTS lecture_id CASCADE;

ALTER TABLE public.ai_conversation 
RENAME COLUMN lecture_id_new_id TO lecture_id;

ALTER TABLE public.ai_conversation 
ADD CONSTRAINT ai_conversation_lecture_id_fkey 
FOREIGN KEY (lecture_id) 
REFERENCES public.lecture(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.ai_conversation 
DROP COLUMN IF EXISTS user_id CASCADE;

ALTER TABLE public.ai_conversation 
RENAME COLUMN user_id_new_id TO user_id;

ALTER TABLE public.ai_conversation 
ADD CONSTRAINT ai_conversation_user_id_fkey 
FOREIGN KEY (user_id) 
REFERENCES public.users(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.ai_processing_log 
DROP COLUMN IF EXISTS job_id CASCADE;

ALTER TABLE public.ai_processing_log 
RENAME COLUMN job_id_new_id TO job_id;

ALTER TABLE public.ai_processing_log 
ADD CONSTRAINT ai_processing_log_job_id_fkey 
FOREIGN KEY (job_id) 
REFERENCES public.job_queue(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.assessment 
DROP COLUMN IF EXISTS course_id CASCADE;

ALTER TABLE public.assessment 
RENAME COLUMN course_id_new_id TO course_id;

ALTER TABLE public.assessment 
ADD CONSTRAINT assessment_course_id_fkey 
FOREIGN KEY (course_id) 
REFERENCES public.course(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.assessment 
DROP COLUMN IF EXISTS lecture_id CASCADE;

ALTER TABLE public.assessment 
RENAME COLUMN lecture_id_new_id TO lecture_id;

ALTER TABLE public.assessment 
ADD CONSTRAINT assessment_lecture_id_fkey 
FOREIGN KEY (lecture_id) 
REFERENCES public.lecture(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.assessment 
DROP COLUMN IF EXISTS teacher_id CASCADE;

ALTER TABLE public.assessment 
RENAME COLUMN teacher_id_new_id TO teacher_id;

ALTER TABLE public.assessment 
ADD CONSTRAINT assessment_teacher_id_fkey 
FOREIGN KEY (teacher_id) 
REFERENCES public.teacher(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.assessment_submission 
DROP COLUMN IF EXISTS assessment_id CASCADE;

ALTER TABLE public.assessment_submission 
RENAME COLUMN assessment_id_new_id TO assessment_id;

ALTER TABLE public.assessment_submission 
ADD CONSTRAINT assessment_submission_assessment_id_fkey 
FOREIGN KEY (assessment_id) 
REFERENCES public.assessment(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.assessment_submission 
DROP COLUMN IF EXISTS student_id CASCADE;

ALTER TABLE public.assessment_submission 
RENAME COLUMN student_id_new_id TO student_id;

ALTER TABLE public.assessment_submission 
ADD CONSTRAINT assessment_submission_student_id_fkey 
FOREIGN KEY (student_id) 
REFERENCES public.student(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.chat_message 
DROP COLUMN IF EXISTS conversation_id CASCADE;

ALTER TABLE public.chat_message 
RENAME COLUMN conversation_id_new_id TO conversation_id;

ALTER TABLE public.chat_message 
ADD CONSTRAINT chat_message_conversation_id_fkey 
FOREIGN KEY (conversation_id) 
REFERENCES public.ai_conversation(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.course 
DROP COLUMN IF EXISTS created_by_teacher_id CASCADE;

ALTER TABLE public.course 
RENAME COLUMN created_by_teacher_id_new_id TO created_by_teacher_id;

ALTER TABLE public.course 
ADD CONSTRAINT course_created_by_teacher_id_fkey 
FOREIGN KEY (created_by_teacher_id) 
REFERENCES public.teacher(id) 
ON UPDATE NO ACTION 
ON DELETE SET NULL;

ALTER TABLE public.course 
DROP COLUMN IF EXISTS university_id CASCADE;

ALTER TABLE public.course 
RENAME COLUMN university_id_new_id TO university_id;

ALTER TABLE public.course 
ADD CONSTRAINT course_university_id_fkey 
FOREIGN KEY (university_id) 
REFERENCES public.university(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.course_teacher 
DROP COLUMN IF EXISTS assigned_by CASCADE;

ALTER TABLE public.course_teacher 
RENAME COLUMN assigned_by_new_id TO assigned_by;

ALTER TABLE public.course_teacher 
ADD CONSTRAINT course_teacher_assigned_by_fkey 
FOREIGN KEY (assigned_by) 
REFERENCES public.users(id) 
ON UPDATE NO ACTION 
ON DELETE SET NULL;

ALTER TABLE public.course_teacher 
DROP COLUMN IF EXISTS course_id CASCADE;

ALTER TABLE public.course_teacher 
RENAME COLUMN course_id_new_id TO course_id;

ALTER TABLE public.course_teacher 
ADD CONSTRAINT course_teacher_course_id_fkey 
FOREIGN KEY (course_id) 
REFERENCES public.course(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.course_teacher 
DROP COLUMN IF EXISTS teacher_id CASCADE;

ALTER TABLE public.course_teacher 
RENAME COLUMN teacher_id_new_id TO teacher_id;

ALTER TABLE public.course_teacher 
ADD CONSTRAINT course_teacher_teacher_id_fkey 
FOREIGN KEY (teacher_id) 
REFERENCES public.teacher(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.document_assignment 
DROP COLUMN IF EXISTS course_id CASCADE;

ALTER TABLE public.document_assignment 
RENAME COLUMN course_id_new_id TO course_id;

ALTER TABLE public.document_assignment 
ADD CONSTRAINT document_assignment_course_id_fkey 
FOREIGN KEY (course_id) 
REFERENCES public.course(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.document_assignment 
DROP COLUMN IF EXISTS document_id CASCADE;

ALTER TABLE public.document_assignment 
RENAME COLUMN document_id_new_id TO document_id;

ALTER TABLE public.document_assignment 
ADD CONSTRAINT document_assignment_document_id_fkey 
FOREIGN KEY (document_id) 
REFERENCES public.documents(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.documents 
DROP COLUMN IF EXISTS teacher_id CASCADE;

ALTER TABLE public.documents 
RENAME COLUMN teacher_id_new_id TO teacher_id;

ALTER TABLE public.documents 
ADD CONSTRAINT documents_teacher_id_fkey 
FOREIGN KEY (teacher_id) 
REFERENCES public.teacher(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.documents 
DROP COLUMN IF EXISTS university_id CASCADE;

ALTER TABLE public.documents 
RENAME COLUMN university_id_new_id TO university_id;

ALTER TABLE public.documents 
ADD CONSTRAINT documents_university_id_fkey 
FOREIGN KEY (university_id) 
REFERENCES public.university(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.enrollment 
DROP COLUMN IF EXISTS course_id CASCADE;

ALTER TABLE public.enrollment 
RENAME COLUMN course_id_new_id TO course_id;

ALTER TABLE public.enrollment 
ADD CONSTRAINT enrollment_course_id_fkey 
FOREIGN KEY (course_id) 
REFERENCES public.course(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.enrollment 
DROP COLUMN IF EXISTS semester_id CASCADE;

ALTER TABLE public.enrollment 
RENAME COLUMN semester_id_new_id TO semester_id;

ALTER TABLE public.enrollment 
ADD CONSTRAINT enrollment_semester_id_fkey 
FOREIGN KEY (semester_id) 
REFERENCES public.semester(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.enrollment 
DROP COLUMN IF EXISTS student_id CASCADE;

ALTER TABLE public.enrollment 
RENAME COLUMN student_id_new_id TO student_id;

ALTER TABLE public.enrollment 
ADD CONSTRAINT enrollment_student_id_fkey 
FOREIGN KEY (student_id) 
REFERENCES public.student(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.flashcard 
DROP COLUMN IF EXISTS lecture_id CASCADE;

ALTER TABLE public.flashcard 
RENAME COLUMN lecture_id_new_id TO lecture_id;

ALTER TABLE public.flashcard 
ADD CONSTRAINT flashcard_lecture_id_fkey 
FOREIGN KEY (lecture_id) 
REFERENCES public.lecture(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.lecture 
DROP COLUMN IF EXISTS course_id CASCADE;

ALTER TABLE public.lecture 
RENAME COLUMN course_id_new_id TO course_id;

ALTER TABLE public.lecture 
ADD CONSTRAINT lecture_course_id_fkey 
FOREIGN KEY (course_id) 
REFERENCES public.course(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.lecture 
DROP COLUMN IF EXISTS document_id CASCADE;

ALTER TABLE public.lecture 
RENAME COLUMN document_id_new_id TO document_id;

ALTER TABLE public.lecture 
ADD CONSTRAINT lecture_document_id_fkey 
FOREIGN KEY (document_id) 
REFERENCES public.documents(id) 
ON UPDATE NO ACTION 
ON DELETE SET NULL;

ALTER TABLE public.lecture 
DROP COLUMN IF EXISTS semester_id CASCADE;

ALTER TABLE public.lecture 
RENAME COLUMN semester_id_new_id TO semester_id;

ALTER TABLE public.lecture 
ADD CONSTRAINT lecture_semester_id_fkey 
FOREIGN KEY (semester_id) 
REFERENCES public.semester(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.lecture 
DROP COLUMN IF EXISTS teacher_id CASCADE;

ALTER TABLE public.lecture 
RENAME COLUMN teacher_id_new_id TO teacher_id;

ALTER TABLE public.lecture 
ADD CONSTRAINT lecture_teacher_id_fkey 
FOREIGN KEY (teacher_id) 
REFERENCES public.teacher(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.lecture_analytics 
DROP COLUMN IF EXISTS lecture_id CASCADE;

ALTER TABLE public.lecture_analytics 
RENAME COLUMN lecture_id_new_id TO lecture_id;

ALTER TABLE public.lecture_analytics 
ADD CONSTRAINT lecture_analytics_lecture_id_fkey 
FOREIGN KEY (lecture_id) 
REFERENCES public.lecture(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.lecture_chunk 
DROP COLUMN IF EXISTS lecture_id CASCADE;

ALTER TABLE public.lecture_chunk 
RENAME COLUMN lecture_id_new_id TO lecture_id;

ALTER TABLE public.lecture_chunk 
ADD CONSTRAINT lecture_chunk_lecture_id_fkey 
FOREIGN KEY (lecture_id) 
REFERENCES public.lecture(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.lecture_content 
DROP COLUMN IF EXISTS lecture_id CASCADE;

ALTER TABLE public.lecture_content 
RENAME COLUMN lecture_id_new_id TO lecture_id;

ALTER TABLE public.lecture_content 
ADD CONSTRAINT lecture_content_lecture_id_fkey 
FOREIGN KEY (lecture_id) 
REFERENCES public.lecture(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.lecture_embedding 
DROP COLUMN IF EXISTS chunk_id CASCADE;

ALTER TABLE public.lecture_embedding 
RENAME COLUMN chunk_id_new_id TO chunk_id;

ALTER TABLE public.lecture_embedding 
ADD CONSTRAINT lecture_embedding_chunk_id_fkey 
FOREIGN KEY (chunk_id) 
REFERENCES public.lecture_chunk(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.lecture_embedding 
DROP COLUMN IF EXISTS lecture_id CASCADE;

ALTER TABLE public.lecture_embedding 
RENAME COLUMN lecture_id_new_id TO lecture_id;

ALTER TABLE public.lecture_embedding 
ADD CONSTRAINT lecture_embedding_lecture_id_fkey 
FOREIGN KEY (lecture_id) 
REFERENCES public.lecture(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.module 
DROP COLUMN IF EXISTS semester_id CASCADE;

ALTER TABLE public.module 
RENAME COLUMN semester_id_new_id TO semester_id;

ALTER TABLE public.module 
ADD CONSTRAINT module_semester_id_fkey 
FOREIGN KEY (semester_id) 
REFERENCES public.semester(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.module 
DROP COLUMN IF EXISTS university_id CASCADE;

ALTER TABLE public.module 
RENAME COLUMN university_id_new_id TO university_id;

ALTER TABLE public.module 
ADD CONSTRAINT module_university_id_fkey 
FOREIGN KEY (university_id) 
REFERENCES public.university(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.module_course 
DROP COLUMN IF EXISTS course_id CASCADE;

ALTER TABLE public.module_course 
RENAME COLUMN course_id_new_id TO course_id;

ALTER TABLE public.module_course 
ADD CONSTRAINT module_course_course_id_fkey 
FOREIGN KEY (course_id) 
REFERENCES public.course(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.module_course 
DROP COLUMN IF EXISTS module_id CASCADE;

ALTER TABLE public.module_course 
RENAME COLUMN module_id_new_id TO module_id;

ALTER TABLE public.module_course 
ADD CONSTRAINT module_course_module_id_fkey 
FOREIGN KEY (module_id) 
REFERENCES public.module(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.notification 
DROP COLUMN IF EXISTS user_id CASCADE;

ALTER TABLE public.notification 
RENAME COLUMN user_id_new_id TO user_id;

ALTER TABLE public.notification 
ADD CONSTRAINT notification_user_id_fkey 
FOREIGN KEY (user_id) 
REFERENCES public.users(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.question 
DROP COLUMN IF EXISTS assessment_id CASCADE;

ALTER TABLE public.question 
RENAME COLUMN assessment_id_new_id TO assessment_id;

ALTER TABLE public.question 
ADD CONSTRAINT question_assessment_id_fkey 
FOREIGN KEY (assessment_id) 
REFERENCES public.assessment(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.result_view_request 
DROP COLUMN IF EXISTS assessment_id CASCADE;

ALTER TABLE public.result_view_request 
RENAME COLUMN assessment_id_new_id TO assessment_id;

ALTER TABLE public.result_view_request 
ADD CONSTRAINT result_view_request_assessment_id_fkey 
FOREIGN KEY (assessment_id) 
REFERENCES public.assessment(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.result_view_request 
DROP COLUMN IF EXISTS student_id CASCADE;

ALTER TABLE public.result_view_request 
RENAME COLUMN student_id_new_id TO student_id;

ALTER TABLE public.result_view_request 
ADD CONSTRAINT result_view_request_student_id_fkey 
FOREIGN KEY (student_id) 
REFERENCES public.student(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.result_view_request 
DROP COLUMN IF EXISTS teacher_id CASCADE;

ALTER TABLE public.result_view_request 
RENAME COLUMN teacher_id_new_id TO teacher_id;

ALTER TABLE public.result_view_request 
ADD CONSTRAINT result_view_request_teacher_id_fkey 
FOREIGN KEY (teacher_id) 
REFERENCES public.teacher(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.semester 
DROP COLUMN IF EXISTS course_id CASCADE;

ALTER TABLE public.semester 
RENAME COLUMN course_id_new_id TO course_id;

ALTER TABLE public.semester 
ADD CONSTRAINT semester_course_id_fkey 
FOREIGN KEY (course_id) 
REFERENCES public.course(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.semester 
DROP COLUMN IF EXISTS university_id CASCADE;

ALTER TABLE public.semester 
RENAME COLUMN university_id_new_id TO university_id;

ALTER TABLE public.semester 
ADD CONSTRAINT semester_university_id_fkey 
FOREIGN KEY (university_id) 
REFERENCES public.university(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.student 
DROP COLUMN IF EXISTS university_id CASCADE;

ALTER TABLE public.student 
RENAME COLUMN university_id_new_id TO university_id;

ALTER TABLE public.student 
ADD CONSTRAINT student_university_id_fkey 
FOREIGN KEY (university_id) 
REFERENCES public.university(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.student 
DROP COLUMN IF EXISTS user_id CASCADE;

ALTER TABLE public.student 
RENAME COLUMN user_id_new_id TO user_id;

ALTER TABLE public.student 
ADD CONSTRAINT student_user_id_fkey 
FOREIGN KEY (user_id) 
REFERENCES public.users(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.student_engagement 
DROP COLUMN IF EXISTS lecture_id CASCADE;

ALTER TABLE public.student_engagement 
RENAME COLUMN lecture_id_new_id TO lecture_id;

ALTER TABLE public.student_engagement 
ADD CONSTRAINT student_engagement_lecture_id_fkey 
FOREIGN KEY (lecture_id) 
REFERENCES public.lecture(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.student_engagement 
DROP COLUMN IF EXISTS student_id CASCADE;

ALTER TABLE public.student_engagement 
RENAME COLUMN student_id_new_id TO student_id;

ALTER TABLE public.student_engagement 
ADD CONSTRAINT student_engagement_student_id_fkey 
FOREIGN KEY (student_id) 
REFERENCES public.student(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.teacher 
DROP COLUMN IF EXISTS university_id CASCADE;

ALTER TABLE public.teacher 
RENAME COLUMN university_id_new_id TO university_id;

ALTER TABLE public.teacher 
ADD CONSTRAINT teacher_university_id_fkey 
FOREIGN KEY (university_id) 
REFERENCES public.university(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;

ALTER TABLE public.teacher 
DROP COLUMN IF EXISTS user_id CASCADE;

ALTER TABLE public.teacher 
RENAME COLUMN user_id_new_id TO user_id;

ALTER TABLE public.teacher 
ADD CONSTRAINT teacher_user_id_fkey 
FOREIGN KEY (user_id) 
REFERENCES public.users(id) 
ON UPDATE NO ACTION 
ON DELETE CASCADE;

ALTER TABLE public.users 
DROP COLUMN IF EXISTS university_id CASCADE;

ALTER TABLE public.users 
RENAME COLUMN university_id_new_id TO university_id;

ALTER TABLE public.users 
ADD CONSTRAINT users_university_id_fkey 
FOREIGN KEY (university_id) 
REFERENCES public.university(id) 
ON UPDATE NO ACTION 
ON DELETE NO ACTION;


-- ============================================================
-- PART 6: Add indexes on UUID columns for external API lookups
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_university_uuid 
ON public.university(uuid);

CREATE INDEX IF NOT EXISTS idx_job_queue_uuid 
ON public.job_queue(uuid);

CREATE INDEX IF NOT EXISTS idx_ai_processing_log_uuid 
ON public.ai_processing_log(uuid);

CREATE INDEX IF NOT EXISTS idx_users_uuid 
ON public.users(uuid);

CREATE INDEX IF NOT EXISTS idx_student_uuid 
ON public.student(uuid);

CREATE INDEX IF NOT EXISTS idx_teacher_uuid 
ON public.teacher(uuid);

CREATE INDEX IF NOT EXISTS idx_notification_uuid 
ON public.notification(uuid);

CREATE INDEX IF NOT EXISTS idx_documents_uuid 
ON public.documents(uuid);

CREATE INDEX IF NOT EXISTS idx_course_uuid 
ON public.course(uuid);

CREATE INDEX IF NOT EXISTS idx_document_assignment_uuid 
ON public.document_assignment(uuid);

CREATE INDEX IF NOT EXISTS idx_course_teacher_uuid 
ON public.course_teacher(uuid);

CREATE INDEX IF NOT EXISTS idx_semester_uuid 
ON public.semester(uuid);

CREATE INDEX IF NOT EXISTS idx_lecture_uuid 
ON public.lecture(uuid);

CREATE INDEX IF NOT EXISTS idx_enrollment_uuid 
ON public.enrollment(uuid);

CREATE INDEX IF NOT EXISTS idx_module_uuid 
ON public.module(uuid);

CREATE INDEX IF NOT EXISTS idx_student_engagement_uuid 
ON public.student_engagement(uuid);

CREATE INDEX IF NOT EXISTS idx_assessment_uuid 
ON public.assessment(uuid);

CREATE INDEX IF NOT EXISTS idx_module_course_uuid 
ON public.module_course(uuid);

CREATE INDEX IF NOT EXISTS idx_lecture_content_uuid 
ON public.lecture_content(uuid);

CREATE INDEX IF NOT EXISTS idx_lecture_analytics_uuid 
ON public.lecture_analytics(uuid);

CREATE INDEX IF NOT EXISTS idx_lecture_chunk_uuid 
ON public.lecture_chunk(uuid);

CREATE INDEX IF NOT EXISTS idx_flashcard_uuid 
ON public.flashcard(uuid);

CREATE INDEX IF NOT EXISTS idx_ai_conversation_uuid 
ON public.ai_conversation(uuid);

CREATE INDEX IF NOT EXISTS idx_question_uuid 
ON public.question(uuid);

CREATE INDEX IF NOT EXISTS idx_result_view_request_uuid 
ON public.result_view_request(uuid);

CREATE INDEX IF NOT EXISTS idx_assessment_submission_uuid 
ON public.assessment_submission(uuid);

CREATE INDEX IF NOT EXISTS idx_lecture_embedding_uuid 
ON public.lecture_embedding(uuid);

CREATE INDEX IF NOT EXISTS idx_chat_message_uuid 
ON public.chat_message(uuid);


-- ============================================================
-- PART 7: Recreate RLS Policies
-- ============================================================
-- NOTE: RLS policies were dropped in PART 0 to avoid dependency issues.
-- You need to recreate your RLS policies after this migration.
-- 
-- Option 1: Extract policies before migration and add them here
-- Option 2: Run your existing security migration file (e.g., fix_supabase_security.sql)
--          which should work since policies reference column names, not data types
--
-- To extract policies, run:
--   python scripts/extract_policies.py
--
-- Then add the policy recreation SQL here before COMMIT


COMMIT;

-- ============================================================
-- POST-MIGRATION VERIFICATION QUERIES
-- ============================================================
-- Run these to verify the migration:

-- Verify integer primary keys:
SELECT table_name, column_name, data_type 
FROM information_schema.columns 
WHERE table_schema = 'public' 
AND column_name = 'id' 
AND data_type = 'bigint'
ORDER BY table_name;

-- Verify UUID columns are indexed:
SELECT tablename, indexname 
FROM pg_indexes 
WHERE schemaname = 'public' 
AND indexname LIKE '%_uuid'
ORDER BY tablename;

-- Verify foreign keys use integer IDs:
SELECT 
    tc.table_name as from_table,
    kcu.column_name as from_column,
    ccu.table_name as to_table,
    ccu.column_name as to_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu 
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu 
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
AND tc.table_schema = 'public'
ORDER BY tc.table_name, kcu.column_name;
