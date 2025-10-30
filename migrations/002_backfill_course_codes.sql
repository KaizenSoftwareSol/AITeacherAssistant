-- Migration: Backfill course codes for existing courses
-- Date: 2025-10-27
-- Description: Ensures all existing courses have valid, unique course codes

-- ============================================================
-- STEP 1: Check for courses without codes
-- ============================================================

-- View courses that might need codes
SELECT 
  id, 
  name, 
  code, 
  university_id,
  created_at
FROM public.course
WHERE code IS NULL OR code = '' OR TRIM(code) = ''
ORDER BY created_at;

-- ============================================================
-- STEP 2: Generate codes for courses without them
-- ============================================================

-- Function to generate a course code from course name
CREATE OR REPLACE FUNCTION generate_course_code(course_name TEXT, university_id UUID)
RETURNS TEXT AS $$
DECLARE
  base_code TEXT;
  final_code TEXT;
  counter INTEGER := 1;
BEGIN
  -- Extract first letters from course name (e.g., "Introduction to Computer Science" -> "ITCS")
  base_code := UPPER(REGEXP_REPLACE(
    SUBSTRING(
      ARRAY_TO_STRING(
        ARRAY(
          SELECT SUBSTRING(word FROM 1 FOR 1)
          FROM UNNEST(STRING_TO_ARRAY(course_name, ' ')) AS word
          WHERE LENGTH(word) > 2  -- Skip short words like "to", "of", "and"
        ),
        ''
      )
    FROM 1 FOR 4),  -- Take first 4 letters
    '[^A-Z0-9]', '', 'g'
  ));
  
  -- If base_code is too short, pad with course name initials
  IF LENGTH(base_code) < 2 THEN
    base_code := UPPER(SUBSTRING(REGEXP_REPLACE(course_name, '[^A-Za-z0-9]', '', 'g') FROM 1 FOR 4));
  END IF;
  
  -- Add numeric suffix (101, 102, etc.)
  final_code := base_code || '101';
  
  -- Check for uniqueness and increment if needed
  WHILE EXISTS (
    SELECT 1 FROM public.course 
    WHERE code = final_code 
      AND university_id = generate_course_code.university_id
  ) LOOP
    counter := counter + 1;
    final_code := base_code || (100 + counter)::TEXT;
  END LOOP;
  
  RETURN final_code;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- STEP 3: Update courses without codes
-- ============================================================

-- Update courses that have NULL or empty codes
DO $$
DECLARE
  course_record RECORD;
  new_code TEXT;
BEGIN
  FOR course_record IN 
    SELECT id, name, university_id 
    FROM public.course 
    WHERE code IS NULL OR code = '' OR TRIM(code) = ''
  LOOP
    -- Generate a unique code
    new_code := generate_course_code(course_record.name, course_record.university_id);
    
    -- Update the course
    UPDATE public.course 
    SET code = new_code,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = course_record.id;
    
    RAISE NOTICE 'Updated course "%" with code: %', course_record.name, new_code;
  END LOOP;
END $$;

-- ============================================================
-- STEP 4: Handle duplicate codes (if any)
-- ============================================================

-- Find duplicate codes within the same university
WITH duplicates AS (
  SELECT code, university_id, COUNT(*) as count
  FROM public.course
  GROUP BY code, university_id
  HAVING COUNT(*) > 1
)
SELECT 
  c.id,
  c.name,
  c.code,
  c.university_id,
  d.count as duplicate_count
FROM public.course c
JOIN duplicates d ON c.code = d.code AND c.university_id = d.university_id
ORDER BY c.code, c.created_at;

-- Fix duplicates by adding suffix
DO $$
DECLARE
  dup_record RECORD;
  suffix INTEGER;
  new_code TEXT;
BEGIN
  FOR dup_record IN 
    WITH duplicates AS (
      SELECT code, university_id, COUNT(*) as count
      FROM public.course
      GROUP BY code, university_id
      HAVING COUNT(*) > 1
    ),
    ranked_courses AS (
      SELECT 
        c.id,
        c.name,
        c.code,
        c.university_id,
        ROW_NUMBER() OVER (PARTITION BY c.code, c.university_id ORDER BY c.created_at) as rn
      FROM public.course c
      JOIN duplicates d ON c.code = d.code AND c.university_id = d.university_id
    )
    SELECT id, name, code, university_id, rn
    FROM ranked_courses
    WHERE rn > 1
  LOOP
    -- Keep first occurrence, rename others
    suffix := dup_record.rn - 1;
    new_code := dup_record.code || '-' || suffix::TEXT;
    
    -- Make sure new code is unique
    WHILE EXISTS (
      SELECT 1 FROM public.course 
      WHERE code = new_code AND university_id = dup_record.university_id
    ) LOOP
      suffix := suffix + 1;
      new_code := dup_record.code || '-' || suffix::TEXT;
    END LOOP;
    
    -- Update the course
    UPDATE public.course 
    SET code = new_code,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = dup_record.id;
    
    RAISE NOTICE 'Renamed duplicate course "%" from % to %', 
      dup_record.name, dup_record.code, new_code;
  END LOOP;
END $$;

-- ============================================================
-- STEP 5: Verify all courses have valid codes
-- ============================================================

-- Check results
SELECT 
  COUNT(*) as total_courses,
  COUNT(CASE WHEN code IS NOT NULL AND code != '' THEN 1 END) as courses_with_codes,
  COUNT(CASE WHEN code IS NULL OR code = '' THEN 1 END) as courses_without_codes
FROM public.course;

-- Show sample of updated courses
SELECT 
  id,
  name,
  code,
  university_id,
  created_at,
  updated_at
FROM public.course
ORDER BY updated_at DESC
LIMIT 20;

-- ============================================================
-- STEP 6: Add constraint if not exists
-- ============================================================

-- Ensure code column is not nullable
ALTER TABLE public.course 
  ALTER COLUMN code SET NOT NULL;

-- Ensure code is unique within university (optional - comment out if codes should be globally unique)
-- DROP INDEX IF EXISTS idx_course_code_university;
-- CREATE UNIQUE INDEX idx_course_code_university ON public.course(code, university_id);

-- ============================================================
-- STEP 7: Add index for faster enrollment lookups
-- ============================================================

-- Index for course code lookups (used in enrollment)
CREATE INDEX IF NOT EXISTS idx_course_code_upper 
  ON public.course(UPPER(code), university_id);

-- ============================================================
-- STEP 8: Create view for course code management
-- ============================================================

CREATE OR REPLACE VIEW course_code_summary AS
SELECT 
  c.id as course_id,
  c.code,
  c.name as course_name,
  u.name as university_name,
  COUNT(DISTINCT e.id) as enrolled_students,
  COUNT(DISTINCT l.id) as total_lectures,
  c.created_at,
  c.updated_at
FROM public.course c
LEFT JOIN public.university u ON c.university_id = u.id
LEFT JOIN public.enrollment e ON e.course_id = c.id AND e.is_active = true
LEFT JOIN public.lecture l ON l.course_id = c.id
GROUP BY c.id, c.code, c.name, u.name, c.created_at, c.updated_at
ORDER BY u.name, c.code;

COMMENT ON VIEW course_code_summary IS 'Summary of courses with their codes, enrollment, and lecture counts';

-- ============================================================
-- COMPLETION MESSAGE
-- ============================================================

DO $$
BEGIN
  RAISE NOTICE '================================================================';
  RAISE NOTICE 'Course code backfill migration completed!';
  RAISE NOTICE 'All courses now have unique course codes.';
  RAISE NOTICE 'Teachers can now share these codes with students for enrollment.';
  RAISE NOTICE '================================================================';
END $$;

