-- ============================================================
-- SUPABASE SECURITY FIX MIGRATION
-- Run this in your Supabase SQL Editor
-- ============================================================
--
-- This migration fixes the following security issues:
--
-- 1. SECURITY DEFINER VIEWS (2 issues)
--    - public.student_course_lectures
--    - public.course_code_summary
--
-- 2. RLS DISABLED ON TABLES (22+ issues)
--    - All public tables need RLS enabled
--
-- IMPORTANT NOTES:
-- - Your FastAPI backend uses the service_role key, which bypasses RLS
-- - RLS policies only affect direct client access (anon/authenticated roles)
-- - If you ONLY access the database through your FastAPI backend, you can
--   simply enable RLS without creating policies (see PART 2)
-- - The policies in PART 3 are for cases where clients access Supabase directly
--
-- ============================================================

-- ============================================================
-- PART 1: FIX SECURITY DEFINER VIEWS
-- Recreate views with SECURITY INVOKER (default behavior)
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
-- PART 3: CREATE RLS POLICIES
-- These policies allow the service role (used by your FastAPI backend)
-- to access all data, while restricting direct client access
-- ============================================================

-- ------------------------------------
-- USERS TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to users"
ON public.users FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Users can view their own profile"
ON public.users FOR SELECT
TO authenticated
USING (auth.uid()::text = id::text);

CREATE POLICY "Users can update their own profile"
ON public.users FOR UPDATE
TO authenticated
USING (auth.uid()::text = id::text)
WITH CHECK (auth.uid()::text = id::text);

-- ------------------------------------
-- UNIVERSITY TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to university"
ON public.university FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Anyone can view universities"
ON public.university FOR SELECT
TO authenticated, anon
USING (true);

-- ------------------------------------
-- TEACHER TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to teacher"
ON public.teacher FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Teachers can view their own profile"
ON public.teacher FOR SELECT
TO authenticated
USING (user_id::text = auth.uid()::text);

CREATE POLICY "Teachers can update their own profile"
ON public.teacher FOR UPDATE
TO authenticated
USING (user_id::text = auth.uid()::text)
WITH CHECK (user_id::text = auth.uid()::text);

-- ------------------------------------
-- STUDENT TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to student"
ON public.student FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Students can view their own profile"
ON public.student FOR SELECT
TO authenticated
USING (user_id::text = auth.uid()::text);

CREATE POLICY "Students can update their own profile"
ON public.student FOR UPDATE
TO authenticated
USING (user_id::text = auth.uid()::text)
WITH CHECK (user_id::text = auth.uid()::text);

-- ------------------------------------
-- COURSE TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to course"
ON public.course FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Anyone can view courses"
ON public.course FOR SELECT
TO authenticated, anon
USING (true);

CREATE POLICY "Teachers can manage their university courses"
ON public.course FOR ALL
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.teacher t
        WHERE t.user_id::text = auth.uid()::text
        AND t.university_id = course.university_id
    )
);

-- ------------------------------------
-- SEMESTER TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to semester"
ON public.semester FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Anyone can view semesters"
ON public.semester FOR SELECT
TO authenticated
USING (true);

-- ------------------------------------
-- ENROLLMENT TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to enrollment"
ON public.enrollment FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Students can view their own enrollments"
ON public.enrollment FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.student s
        WHERE s.id = enrollment.student_id
        AND s.user_id::text = auth.uid()::text
    )
);

CREATE POLICY "Students can enroll themselves"
ON public.enrollment FOR INSERT
TO authenticated
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.student s
        WHERE s.id = enrollment.student_id
        AND s.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- LECTURE TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to lecture"
ON public.lecture FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Teachers can manage their own lectures"
ON public.lecture FOR ALL
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.teacher t
        WHERE t.id = lecture.teacher_id
        AND t.user_id::text = auth.uid()::text
    )
);

CREATE POLICY "Students can view published lectures in enrolled courses"
ON public.lecture FOR SELECT
TO authenticated
USING (
    status IN ('PUBLISHED', 'DELIVERED')
    AND EXISTS (
        SELECT 1 FROM public.enrollment e
        JOIN public.student s ON s.id = e.student_id
        WHERE e.course_id = lecture.course_id
        AND e.is_active = true
        AND s.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- LECTURE_CONTENT TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to lecture_content"
ON public.lecture_content FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Users can view lecture content for accessible lectures"
ON public.lecture_content FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.lecture l
        JOIN public.enrollment e ON e.course_id = l.course_id
        JOIN public.student s ON s.id = e.student_id
        WHERE l.id = lecture_content.lecture_id
        AND l.status IN ('PUBLISHED', 'DELIVERED')
        AND e.is_active = true
        AND s.user_id::text = auth.uid()::text
    )
    OR EXISTS (
        SELECT 1 FROM public.lecture l
        JOIN public.teacher t ON t.id = l.teacher_id
        WHERE l.id = lecture_content.lecture_id
        AND t.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- LECTURE_CHUNK TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to lecture_chunk"
ON public.lecture_chunk FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Users can view chunks for accessible lectures"
ON public.lecture_chunk FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.lecture l
        JOIN public.enrollment e ON e.course_id = l.course_id
        JOIN public.student s ON s.id = e.student_id
        WHERE l.id = lecture_chunk.lecture_id
        AND l.status IN ('PUBLISHED', 'DELIVERED')
        AND e.is_active = true
        AND s.user_id::text = auth.uid()::text
    )
    OR EXISTS (
        SELECT 1 FROM public.lecture l
        JOIN public.teacher t ON t.id = l.teacher_id
        WHERE l.id = lecture_chunk.lecture_id
        AND t.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- LECTURE_EMBEDDING TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to lecture_embedding"
ON public.lecture_embedding FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Users can view embeddings for accessible lectures"
ON public.lecture_embedding FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.lecture l
        JOIN public.enrollment e ON e.course_id = l.course_id
        JOIN public.student s ON s.id = e.student_id
        WHERE l.id = lecture_embedding.lecture_id
        AND l.status IN ('PUBLISHED', 'DELIVERED')
        AND e.is_active = true
        AND s.user_id::text = auth.uid()::text
    )
    OR EXISTS (
        SELECT 1 FROM public.lecture l
        JOIN public.teacher t ON t.id = l.teacher_id
        WHERE l.id = lecture_embedding.lecture_id
        AND t.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- LECTURE_ANALYTICS TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to lecture_analytics"
ON public.lecture_analytics FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Teachers can view analytics for their lectures"
ON public.lecture_analytics FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.lecture l
        JOIN public.teacher t ON t.id = l.teacher_id
        WHERE l.id = lecture_analytics.lecture_id
        AND t.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- AI_CONVERSATION TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to ai_conversation"
ON public.ai_conversation FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Users can view their own conversations"
ON public.ai_conversation FOR SELECT
TO authenticated
USING (user_id::text = auth.uid()::text);

CREATE POLICY "Users can create their own conversations"
ON public.ai_conversation FOR INSERT
TO authenticated
WITH CHECK (user_id::text = auth.uid()::text);

CREATE POLICY "Users can update their own conversations"
ON public.ai_conversation FOR UPDATE
TO authenticated
USING (user_id::text = auth.uid()::text)
WITH CHECK (user_id::text = auth.uid()::text);

-- ------------------------------------
-- CHAT_MESSAGE TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to chat_message"
ON public.chat_message FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Users can view messages in their conversations"
ON public.chat_message FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.ai_conversation ac
        WHERE ac.id = chat_message.conversation_id
        AND ac.user_id::text = auth.uid()::text
    )
);

CREATE POLICY "Users can create messages in their conversations"
ON public.chat_message FOR INSERT
TO authenticated
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.ai_conversation ac
        WHERE ac.id = chat_message.conversation_id
        AND ac.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- ASSESSMENT TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to assessment"
ON public.assessment FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Teachers can manage their own assessments"
ON public.assessment FOR ALL
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.teacher t
        WHERE t.id = assessment.teacher_id
        AND t.user_id::text = auth.uid()::text
    )
);

CREATE POLICY "Students can view published assessments in enrolled courses"
ON public.assessment FOR SELECT
TO authenticated
USING (
    is_published = true
    AND EXISTS (
        SELECT 1 FROM public.enrollment e
        JOIN public.student s ON s.id = e.student_id
        WHERE e.course_id = assessment.course_id
        AND e.is_active = true
        AND s.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- ASSESSMENT_SUBMISSION TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to assessment_submission"
ON public.assessment_submission FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Students can view their own submissions"
ON public.assessment_submission FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.student s
        WHERE s.id = assessment_submission.student_id
        AND s.user_id::text = auth.uid()::text
    )
);

CREATE POLICY "Students can create their own submissions"
ON public.assessment_submission FOR INSERT
TO authenticated
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.student s
        WHERE s.id = assessment_submission.student_id
        AND s.user_id::text = auth.uid()::text
    )
);

CREATE POLICY "Students can update their own submissions"
ON public.assessment_submission FOR UPDATE
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.student s
        WHERE s.id = assessment_submission.student_id
        AND s.user_id::text = auth.uid()::text
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.student s
        WHERE s.id = assessment_submission.student_id
        AND s.user_id::text = auth.uid()::text
    )
);

CREATE POLICY "Teachers can view submissions for their assessments"
ON public.assessment_submission FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.assessment a
        JOIN public.teacher t ON t.id = a.teacher_id
        WHERE a.id = assessment_submission.assessment_id
        AND t.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- QUESTION TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to question"
ON public.question FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Teachers can manage questions in their assessments"
ON public.question FOR ALL
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.assessment a
        JOIN public.teacher t ON t.id = a.teacher_id
        WHERE a.id = question.assessment_id
        AND t.user_id::text = auth.uid()::text
    )
);

CREATE POLICY "Students can view questions in accessible assessments"
ON public.question FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.assessment a
        JOIN public.enrollment e ON e.course_id = a.course_id
        JOIN public.student s ON s.id = e.student_id
        WHERE a.id = question.assessment_id
        AND a.is_published = true
        AND e.is_active = true
        AND s.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- JOB_QUEUE TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to job_queue"
ON public.job_queue FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Job queue should only be accessible by service role (backend)
-- No direct client access policies needed

-- ------------------------------------
-- AI_PROCESSING_LOG TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to ai_processing_log"
ON public.ai_processing_log FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Processing logs should only be accessible by service role (backend)
-- No direct client access policies needed

-- ------------------------------------
-- STUDENT_ENGAGEMENT TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to student_engagement"
ON public.student_engagement FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Students can view their own engagement data"
ON public.student_engagement FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.student s
        WHERE s.id = student_engagement.student_id
        AND s.user_id::text = auth.uid()::text
    )
);

CREATE POLICY "Teachers can view engagement for their lectures"
ON public.student_engagement FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.lecture l
        JOIN public.teacher t ON t.id = l.teacher_id
        WHERE l.id = student_engagement.lecture_id
        AND t.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- FLASHCARD TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to flashcard"
ON public.flashcard FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Users can view flashcards for accessible lectures"
ON public.flashcard FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.lecture l
        JOIN public.enrollment e ON e.course_id = l.course_id
        JOIN public.student s ON s.id = e.student_id
        WHERE l.id = flashcard.lecture_id
        AND l.status IN ('PUBLISHED', 'DELIVERED')
        AND e.is_active = true
        AND s.user_id::text = auth.uid()::text
    )
    OR EXISTS (
        SELECT 1 FROM public.lecture l
        JOIN public.teacher t ON t.id = l.teacher_id
        WHERE l.id = flashcard.lecture_id
        AND t.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- DOCUMENT_ASSIGNMENT TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to document_assignment"
ON public.document_assignment FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Teachers can manage document assignments for their courses"
ON public.document_assignment FOR ALL
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.course c
        JOIN public.teacher t ON t.university_id = c.university_id
        WHERE c.id = document_assignment.course_id
        AND t.user_id::text = auth.uid()::text
    )
);

CREATE POLICY "Students can view document assignments in enrolled courses"
ON public.document_assignment FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.enrollment e
        JOIN public.student s ON s.id = e.student_id
        WHERE e.course_id = document_assignment.course_id
        AND e.is_active = true
        AND s.user_id::text = auth.uid()::text
    )
);

-- ------------------------------------
-- DOCUMENTS TABLE POLICIES
-- ------------------------------------
CREATE POLICY "Service role has full access to documents"
ON public.documents FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Teachers can manage their own documents"
ON public.documents FOR ALL
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.teacher t
        WHERE t.id = documents.teacher_id
        AND t.user_id::text = auth.uid()::text
    )
);

CREATE POLICY "Students can view documents assigned to their enrolled courses"
ON public.documents FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.document_assignment da
        JOIN public.enrollment e ON e.course_id = da.course_id
        JOIN public.student s ON s.id = e.student_id
        WHERE da.document_id = documents.id
        AND e.is_active = true
        AND s.user_id::text = auth.uid()::text
    )
);

-- ============================================================
-- VERIFICATION QUERIES
-- Run these to verify the changes were applied
-- ============================================================

-- Check RLS is enabled on all tables
SELECT 
    schemaname, 
    tablename, 
    rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY tablename;

-- Check views don't have security_definer
SELECT 
    viewname,
    pg_get_viewdef(c.oid, true) as definition
FROM pg_views v
JOIN pg_class c ON c.relname = v.viewname
WHERE schemaname = 'public'
AND viewname IN ('course_code_summary', 'student_course_lectures');

