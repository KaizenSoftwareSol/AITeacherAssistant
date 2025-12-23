-- ============================================================
-- SUPABASE SECURITY FIX - SIMPLE VERSION
-- Run this in your Supabase SQL Editor
-- ============================================================
--
-- USE THIS VERSION IF:
-- - You ONLY access the database through your FastAPI backend
-- - Your backend uses the service_role key (which bypasses RLS)
-- - You don't allow direct client access to Supabase
--
-- This script:
-- 1. Fixes the SECURITY DEFINER views
-- 2. Enables RLS on all tables (no policies needed for service_role)
--
-- ============================================================

-- ============================================================
-- PART 1: FIX SECURITY DEFINER VIEWS
-- ============================================================

-- Drop and recreate course_code_summary view
DROP VIEW IF EXISTS public.course_code_summary;
CREATE VIEW public.course_code_summary 
WITH (security_invoker = true) AS
SELECT 
    c.id AS course_id,
    c.code,
    c.name AS course_name,
    u.name AS university_name,
    count(DISTINCT e.id) AS enrolled_students,
    count(DISTINCT l.id) AS total_lectures,
    c.created_at,
    c.updated_at
FROM public.course c
LEFT JOIN public.university u ON c.university_id = u.id
LEFT JOIN public.enrollment e ON e.course_id = c.id AND e.is_active = true
LEFT JOIN public.lecture l ON l.course_id = c.id
GROUP BY c.id, c.code, c.name, u.name, c.created_at, c.updated_at
ORDER BY u.name, c.code;

COMMENT ON VIEW public.course_code_summary IS 'Summary of courses with their codes, enrollment, and lecture counts';

-- Drop and recreate student_course_lectures view
DROP VIEW IF EXISTS public.student_course_lectures;
CREATE VIEW public.student_course_lectures 
WITH (security_invoker = true) AS
SELECT 
    e.student_id,
    e.course_id,
    c.code AS course_code,
    c.name AS course_name,
    l.id AS lecture_id,
    l.title AS lecture_title,
    l.description AS lecture_description,
    l.summary AS lecture_summary,
    l.status AS lecture_status,
    l.has_embeddings,
    l.created_at AS lecture_created_at,
    t.id AS teacher_id,
    u.first_name || ' ' || u.last_name AS teacher_name
FROM public.enrollment e
JOIN public.course c ON e.course_id = c.id
JOIN public.lecture l ON l.course_id = c.id
JOIN public.teacher t ON l.teacher_id = t.id
JOIN public.users u ON t.user_id = u.id
WHERE e.is_active = true 
  AND l.status IN ('PUBLISHED', 'DELIVERED');

COMMENT ON VIEW public.student_course_lectures IS 'View that shows all published lectures accessible to enrolled students with teacher information.';

-- ============================================================
-- PART 2: ENABLE ROW LEVEL SECURITY ON ALL TABLES
-- (service_role bypasses RLS, so no policies needed)
-- ============================================================

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.university ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.teacher ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.student ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.course ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.semester ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.enrollment ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lecture ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lecture_content ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lecture_chunk ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lecture_embedding ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lecture_analytics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_conversation ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_message ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assessment ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assessment_submission ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.question ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_processing_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.student_engagement ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.flashcard ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_assignment ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- VERIFICATION QUERY
-- ============================================================

-- Check RLS is enabled on all tables
SELECT 
    schemaname, 
    tablename, 
    rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY tablename;

