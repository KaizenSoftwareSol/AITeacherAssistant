-- ============================================================
-- MIGRATION: Add Test Quiz Features
-- Run this in your Supabase SQL Editor
-- ============================================================
--
-- This migration adds support for:
-- 1. Test quizzes with deadlines (vs practice quizzes)
-- 2. Difficulty levels for AI-generated questions
-- 3. Leaderboard visibility control
--
-- ============================================================

-- Add new columns to assessment table
ALTER TABLE public.assessment 
ADD COLUMN IF NOT EXISTS quiz_mode VARCHAR(20) DEFAULT 'PRACTICE';

ALTER TABLE public.assessment 
ADD COLUMN IF NOT EXISTS difficulty VARCHAR(10) DEFAULT 'MEDIUM';

ALTER TABLE public.assessment 
ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE;

ALTER TABLE public.assessment 
ADD COLUMN IF NOT EXISTS show_leaderboard BOOLEAN DEFAULT TRUE;

-- Add comments for documentation
COMMENT ON COLUMN public.assessment.quiz_mode IS 
'Quiz mode: PRACTICE (no deadline, unlimited attempts) or TEST (with deadline, graded)';

COMMENT ON COLUMN public.assessment.difficulty IS 
'Difficulty level for AI question generation: EASY, MEDIUM, HARD';

COMMENT ON COLUMN public.assessment.is_default IS 
'True for auto-generated practice quizzes created when a lecture is published';

COMMENT ON COLUMN public.assessment.show_leaderboard IS 
'Whether to show the leaderboard to students for TEST quizzes';

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_assessment_quiz_mode 
ON public.assessment(quiz_mode);

CREATE INDEX IF NOT EXISTS idx_assessment_course_quiz_mode 
ON public.assessment(course_id, quiz_mode);

CREATE INDEX IF NOT EXISTS idx_assessment_due_date 
ON public.assessment(due_date) 
WHERE due_date IS NOT NULL;

-- Create index for leaderboard queries (getting ranked submissions)
CREATE INDEX IF NOT EXISTS idx_submission_assessment_score 
ON public.assessment_submission(assessment_id, score DESC) 
WHERE is_submitted = TRUE;

-- Create index for student's best submission
CREATE INDEX IF NOT EXISTS idx_submission_student_assessment 
ON public.assessment_submission(student_id, assessment_id, score DESC);

-- ============================================================
-- VERIFY THE CHANGES
-- ============================================================

-- Check the new columns exist
SELECT column_name, data_type, column_default 
FROM information_schema.columns 
WHERE table_name = 'assessment' 
AND column_name IN ('quiz_mode', 'difficulty', 'is_default', 'show_leaderboard');

-- Update existing assessments to have default values
-- Practice quizzes (is_default = true) are the auto-generated ones
UPDATE public.assessment 
SET quiz_mode = 'PRACTICE', 
    is_default = TRUE 
WHERE quiz_mode IS NULL OR quiz_mode = '';

-- ============================================================
-- OPTIONAL: Sample Test Quiz Data (for testing)
-- Uncomment if you want to create sample data
-- ============================================================

/*
-- Create a sample test quiz
INSERT INTO public.assessment (
    id,
    title,
    description,
    assessment_type,
    course_id,
    lecture_id,
    teacher_id,
    time_limit,
    max_attempts,
    passing_score,
    is_published,
    quiz_mode,
    difficulty,
    is_default,
    show_leaderboard,
    due_date,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'Midterm Quiz - Chapter 1',
    'Test your understanding of the first chapter',
    'QUIZ',
    'YOUR_COURSE_ID',  -- Replace with actual course_id
    'YOUR_LECTURE_ID', -- Replace with actual lecture_id
    'YOUR_TEACHER_ID', -- Replace with actual teacher_id
    30,
    2,
    60.0,
    true,
    'TEST',
    'MEDIUM',
    false,
    true,
    NOW() + INTERVAL '7 days',
    NOW(),
    NOW()
);
*/

