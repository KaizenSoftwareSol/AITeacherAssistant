-- Fix: Complete University-Level Semester Migration
-- Description: 
--   This script completes the migration to add university-level semester support.
--   It handles cases where the migration was partially run or failed.
-- Date: 2026-01-21

-- ============================================================
-- PART 1: Add university_id column if it doesn't exist
-- ============================================================

-- Add university_id column (nullable for backward compatibility)
ALTER TABLE public.semester
ADD COLUMN IF NOT EXISTS university_id UUID REFERENCES public.university(id) ON DELETE CASCADE;

-- Make course_id nullable (for university-level semesters)
-- This is safe to run multiple times
DO $$
BEGIN
    -- Check if course_id is NOT NULL, then make it nullable
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'semester' 
        AND column_name = 'course_id' 
        AND is_nullable = 'NO'
    ) THEN
        ALTER TABLE public.semester ALTER COLUMN course_id DROP NOT NULL;
    END IF;
END $$;

-- Add comment explaining the change
COMMENT ON COLUMN public.semester.university_id IS 
'Foreign key to university for university-level semesters. NULL for course-level semesters (legacy).';

COMMENT ON COLUMN public.semester.course_id IS 
'Foreign key to course for course-level semesters (legacy). NULL for university-level semesters managed by admin.';

-- Create index for efficient queries by university
CREATE INDEX IF NOT EXISTS idx_semester_university_id 
ON public.semester(university_id)
WHERE university_id IS NOT NULL;

-- ============================================================
-- PART 2: Drop constraint if it exists (to allow data fixes)
-- ============================================================

ALTER TABLE public.semester
DROP CONSTRAINT IF EXISTS check_semester_scope;

-- ============================================================
-- PART 3: Fix the data - migrate existing semesters
-- ============================================================

-- Step 1: Set university_id from course (for existing semesters that don't have it)
UPDATE public.semester s
SET university_id = c.university_id
FROM public.course c
WHERE s.course_id = c.id
  AND s.university_id IS NULL;

-- Step 2: Clear course_id for semesters that have both university_id and course_id set
-- This converts them to university-level semesters
UPDATE public.semester
SET course_id = NULL
WHERE university_id IS NOT NULL
  AND course_id IS NOT NULL;

-- ============================================================
-- PART 4: Re-add the constraint
-- ============================================================

-- Add check constraint: either university_id or course_id must be set (but not both)
ALTER TABLE public.semester
ADD CONSTRAINT check_semester_scope 
CHECK (
    (university_id IS NOT NULL AND course_id IS NULL) OR
    (university_id IS NULL AND course_id IS NOT NULL)
);

COMMENT ON CONSTRAINT check_semester_scope ON public.semester IS 
'Ensures semester is either university-level (university_id set) or course-level (course_id set), but not both';
