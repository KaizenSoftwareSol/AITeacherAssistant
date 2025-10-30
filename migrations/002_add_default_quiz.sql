-- Migration: Add is_default column to assessment table
-- This allows marking default/saved quizzes vs temporary regenerated ones

-- Add is_default column to assessment table
ALTER TABLE public.assessment 
  ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT false;

-- Create index for quick lookup of default quizzes
CREATE INDEX IF NOT EXISTS idx_assessment_lecture_default 
  ON public.assessment(lecture_id, is_default);

-- Add comment
COMMENT ON COLUMN public.assessment.is_default IS 'Marks the default/saved quiz for a lecture that is shown to all students';

