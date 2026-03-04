-- Backfill "Default Module" for existing semesters that have no modules.
-- This ensures every semester has at least one module after making modules universal.
-- Safe to run multiple times (idempotent).

-- Step 1: Create "Default Module" for semesters that don't have any modules
INSERT INTO module (id, name, university_id, semester_id, display_order, created_at, updated_at)
SELECT
    gen_random_uuid(),
    'Default Module',
    s.university_id,
    s.id,
    1,
    NOW(),
    NOW()
FROM semester s
WHERE s.course_id IS NULL  -- Only university-level semesters
  AND NOT EXISTS (
    SELECT 1 FROM module m WHERE m.semester_id = s.id
  );

-- Step 2: Assign existing courses (that have no module assignment) to their
-- university's Default Module(s). Each course gets linked to every Default Module
-- in its university so it appears under every semester.
INSERT INTO module_course (module_id, course_id)
SELECT DISTINCT m.id, c.id
FROM course c
JOIN module m ON m.university_id = c.university_id AND m.name = 'Default Module'
WHERE NOT EXISTS (
    SELECT 1 FROM module_course mc WHERE mc.course_id = c.id
);
