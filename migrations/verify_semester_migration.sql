-- Verification Script: University-Level Semester Migration
-- Description: Verifies that the semester migration was successful
-- Run this after fix_semester_constraint_violation.sql to confirm everything is working
-- Date: 2026-01-21

-- ============================================================
-- PART 1: Check Column Structure
-- ============================================================

SELECT 
    'Column Check' as check_type,
    CASE 
        WHEN EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'semester' 
            AND column_name = 'university_id'
        ) THEN '✓ university_id column exists'
        ELSE '✗ university_id column MISSING'
    END as status
UNION ALL
SELECT 
    'Column Check',
    CASE 
        WHEN EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'semester' 
            AND column_name = 'course_id'
            AND is_nullable = 'YES'
        ) THEN '✓ course_id is nullable'
        ELSE '✗ course_id is NOT nullable'
    END;

-- ============================================================
-- PART 2: Check Constraint
-- ============================================================

SELECT 
    'Constraint Check' as check_type,
    CASE 
        WHEN EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE table_schema = 'public' 
            AND table_name = 'semester' 
            AND constraint_name = 'check_semester_scope'
        ) THEN '✓ check_semester_scope constraint exists'
        ELSE '✗ check_semester_scope constraint MISSING'
    END as status;

-- ============================================================
-- PART 3: Check Index
-- ============================================================

SELECT 
    'Index Check' as check_type,
    CASE 
        WHEN EXISTS (
            SELECT 1 FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND tablename = 'semester' 
            AND indexname = 'idx_semester_university_id'
        ) THEN '✓ idx_semester_university_id index exists'
        ELSE '✗ idx_semester_university_id index MISSING'
    END as status;

-- ============================================================
-- PART 4: Data Integrity Check
-- ============================================================

-- Check for any semesters that violate the constraint (should be 0)
SELECT 
    'Data Integrity' as check_type,
    CASE 
        WHEN COUNT(*) = 0 THEN '✓ No constraint violations found'
        ELSE '✗ Found ' || COUNT(*) || ' semesters violating constraint'
    END as status
FROM public.semester
WHERE NOT (
    (university_id IS NOT NULL AND course_id IS NULL) OR
    (university_id IS NULL AND course_id IS NOT NULL)
);

-- ============================================================
-- PART 5: Sample Data Overview
-- ============================================================

-- Count semesters by type
SELECT 
    'Data Overview' as check_type,
    'Total semesters: ' || COUNT(*)::text as status
FROM public.semester
UNION ALL
SELECT 
    'Data Overview',
    'University-level semesters: ' || COUNT(*)::text
FROM public.semester
WHERE university_id IS NOT NULL AND course_id IS NULL
UNION ALL
SELECT 
    'Data Overview',
    'Course-level semesters (legacy): ' || COUNT(*)::text
FROM public.semester
WHERE university_id IS NULL AND course_id IS NOT NULL
UNION ALL
SELECT 
    'Data Overview',
    'Invalid semesters (both or neither): ' || COUNT(*)::text
FROM public.semester
WHERE NOT (
    (university_id IS NOT NULL AND course_id IS NULL) OR
    (university_id IS NULL AND course_id IS NOT NULL)
);

-- ============================================================
-- PART 6: Sample University-Level Semesters
-- ============================================================

-- Show first 5 university-level semesters
SELECT 
    'Sample Data' as check_type,
    'Sample university-level semesters:' as status
UNION ALL
SELECT 
    'Sample Data',
    '  - ' || COALESCE(name, 'Unnamed') || ' (ID: ' || id::text || ', University: ' || COALESCE(university_id::text, 'NULL') || ')'
FROM public.semester
WHERE university_id IS NOT NULL 
  AND course_id IS NULL
LIMIT 5;

-- ============================================================
-- PART 7: Test Query (Verify API will work)
-- ============================================================

-- This simulates what the admin API does: get semesters for a university
-- Replace 'YOUR_UNIVERSITY_ID' with an actual university_id from your database
SELECT 
    'Test Query' as check_type,
    'To test: Run query below with your university_id' as status
UNION ALL
SELECT 
    'Test Query',
    'SELECT * FROM semester WHERE university_id = ''YOUR_UNIVERSITY_ID'' AND course_id IS NULL;';

-- Uncomment and replace YOUR_UNIVERSITY_ID to test:
-- SELECT id, name, start_date, end_date, university_id, course_id
-- FROM public.semester
-- WHERE university_id = 'YOUR_UNIVERSITY_ID'
--   AND course_id IS NULL
-- ORDER BY start_date DESC;
