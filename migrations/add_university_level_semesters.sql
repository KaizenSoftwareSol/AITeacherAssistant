-- Migration: Add University-Level Semester Support
-- Description: 
--   Adds university_id column to semester table to support university-level semesters
--   that can be shared across multiple courses. Makes course_id optional.
-- Date: 2026-01-21

-- ============================================================
-- PART 1: Add university_id column to semester table
-- ============================================================

-- Add university_id column (nullable for backward compatibility)
ALTER TABLE public.semester
ADD COLUMN IF NOT EXISTS university_id UUID REFERENCES public.university(id) ON DELETE CASCADE;

-- Make course_id nullable (for university-level semesters)
ALTER TABLE public.semester
ALTER COLUMN course_id DROP NOT NULL;

-- Add comment explaining the change
COMMENT ON COLUMN public.semester.university_id IS 
'Foreign key to university for university-level semesters. NULL for course-level semesters (legacy).';

COMMENT ON COLUMN public.semester.course_id IS 
'Foreign key to course for course-level semesters (legacy). NULL for university-level semesters managed by admin.';

-- Create index for efficient queries by university
CREATE INDEX IF NOT EXISTS idx_semester_university_id 
ON public.semester(university_id)
WHERE university_id IS NOT NULL;

-- Add comment explaining the index
COMMENT ON INDEX idx_semester_university_id IS 
'Index for efficiently querying university-level semesters';

-- ============================================================
-- PART 2: Update existing semesters BEFORE adding constraint
-- ============================================================

-- For existing course-level semesters, convert them to university-level semesters
-- This must be done BEFORE adding the constraint

-- Step 1: Set university_id from course (for existing semesters)
UPDATE public.semester s
SET university_id = c.university_id
FROM public.course c
WHERE s.course_id = c.id
  AND s.university_id IS NULL;

-- Step 2: Clear course_id to make them university-level semesters
-- This ensures the constraint will be satisfied (university_id set, course_id NULL)
UPDATE public.semester
SET course_id = NULL
WHERE university_id IS NOT NULL
  AND course_id IS NOT NULL;

-- Note: This converts all existing course-level semesters to university-level semesters
-- If you want to keep some as course-level, you'll need to manually set course_id back
-- for those specific semesters after this migration

-- ============================================================
-- PART 3: Add constraint to ensure either university_id or course_id is set
-- ============================================================

-- Add check constraint: either university_id or course_id must be set (but not both)
-- This is added AFTER data migration to avoid constraint violations
ALTER TABLE public.semester
ADD CONSTRAINT check_semester_scope 
CHECK (
    (university_id IS NOT NULL AND course_id IS NULL) OR
    (university_id IS NULL AND course_id IS NOT NULL)
);

COMMENT ON CONSTRAINT check_semester_scope ON public.semester IS 
'Ensures semester is either university-level (university_id set) or course-level (course_id set), but not both';
