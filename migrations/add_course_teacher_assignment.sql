-- Migration: Add Course-Teacher Assignment Support
-- Description: 
--   1. Adds created_by_teacher_id column to course table to track course creators
--   2. Creates course_teacher junction table for admin-assigned course-teacher relationships
-- Date: 2025-01-14

-- ============================================================
-- PART 1: Add created_by_teacher_id to course table
-- ============================================================

-- Add created_by_teacher_id column to track which teacher created the course
ALTER TABLE public.course
ADD COLUMN IF NOT EXISTS created_by_teacher_id UUID REFERENCES public.teacher(id) ON DELETE SET NULL;

-- Add comment explaining the column
COMMENT ON COLUMN public.course.created_by_teacher_id IS 
'Foreign key to teacher who created this course. NULL for courses created before this migration or by admins.';

-- Create index for efficient queries by creator
CREATE INDEX IF NOT EXISTS idx_course_created_by_teacher 
ON public.course(created_by_teacher_id)
WHERE created_by_teacher_id IS NOT NULL;

-- Add comment explaining the index
COMMENT ON INDEX idx_course_created_by_teacher IS 
'Index for efficiently querying courses by their creator teacher';

-- ============================================================
-- PART 2: Create course_teacher junction table
-- ============================================================

-- Create the course_teacher table for admin-assigned course-teacher relationships
CREATE TABLE IF NOT EXISTS public.course_teacher (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID NOT NULL REFERENCES public.course(id) ON DELETE CASCADE,
    teacher_id UUID NOT NULL REFERENCES public.teacher(id) ON DELETE CASCADE,
    assigned_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true,
    
    -- Ensure one active assignment per course-teacher pair
    UNIQUE(course_id, teacher_id)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_course_teacher_course_id 
ON public.course_teacher(course_id);

CREATE INDEX IF NOT EXISTS idx_course_teacher_teacher_id 
ON public.course_teacher(teacher_id);

CREATE INDEX IF NOT EXISTS idx_course_teacher_active 
ON public.course_teacher(teacher_id, is_active)
WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_course_teacher_assigned_by 
ON public.course_teacher(assigned_by)
WHERE assigned_by IS NOT NULL;

-- Add comments for documentation
COMMENT ON TABLE public.course_teacher IS 
'Junction table for course-teacher assignments. Allows admins to assign courses to teachers. Teachers can be assigned to courses they did not create.';

COMMENT ON COLUMN public.course_teacher.course_id IS 
'Foreign key to the course being assigned';

COMMENT ON COLUMN public.course_teacher.teacher_id IS 
'Foreign key to the teacher being assigned to the course';

COMMENT ON COLUMN public.course_teacher.assigned_by IS 
'Foreign key to the admin user who made this assignment. NULL if assigned before this field was added.';

COMMENT ON COLUMN public.course_teacher.assigned_at IS 
'Timestamp when the course was assigned to the teacher';

COMMENT ON COLUMN public.course_teacher.is_active IS 
'Whether this assignment is currently active. Can be set to false to deactivate without deleting.';

-- ============================================================
-- PART 3: Enable Row Level Security (RLS)
-- ============================================================

-- Enable RLS on course_teacher table
ALTER TABLE public.course_teacher ENABLE ROW LEVEL SECURITY;

-- RLS Policies for course_teacher table

-- Teachers can view their own course assignments
CREATE POLICY "Teachers can view own course assignments" ON public.course_teacher
    FOR SELECT
    USING (
        teacher_id IN (
            SELECT id FROM public.teacher WHERE user_id = auth.uid()
        )
    );

-- Admins can view all assignments in their university
CREATE POLICY "Admins can view course assignments in their university" ON public.course_teacher
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.users
            WHERE id = auth.uid()
            AND role = 'ADMIN'
            AND university_id IN (
                SELECT university_id FROM public.course WHERE id = course_teacher.course_id
            )
        )
    );

-- Admins can create course assignments in their university
CREATE POLICY "Admins can create course assignments" ON public.course_teacher
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.users
            WHERE id = auth.uid()
            AND role = 'ADMIN'
            AND university_id IN (
                SELECT university_id FROM public.course WHERE id = course_teacher.course_id
            )
        )
        AND EXISTS (
            SELECT 1 FROM public.teacher
            WHERE id = course_teacher.teacher_id
            AND university_id IN (
                SELECT university_id FROM public.course WHERE id = course_teacher.course_id
            )
        )
    );

-- Admins can update course assignments in their university
CREATE POLICY "Admins can update course assignments" ON public.course_teacher
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM public.users
            WHERE id = auth.uid()
            AND role = 'ADMIN'
            AND university_id IN (
                SELECT university_id FROM public.course WHERE id = course_teacher.course_id
            )
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.users
            WHERE id = auth.uid()
            AND role = 'ADMIN'
            AND university_id IN (
                SELECT university_id FROM public.course WHERE id = course_teacher.course_id
            )
        )
    );

-- Admins can delete course assignments in their university
CREATE POLICY "Admins can delete course assignments" ON public.course_teacher
    FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM public.users
            WHERE id = auth.uid()
            AND role = 'ADMIN'
            AND university_id IN (
                SELECT university_id FROM public.course WHERE id = course_teacher.course_id
            )
        )
    );

-- Grant permissions to authenticated users
GRANT SELECT, INSERT, UPDATE, DELETE ON public.course_teacher TO authenticated;

-- ============================================================
-- PART 4: Update course table RLS (if needed)
-- ============================================================

-- Note: The course table should already have RLS enabled
-- This migration assumes existing RLS policies are in place
-- Teachers can now see courses where:
--   1. created_by_teacher_id matches their teacher.id
--   2. They have an active entry in course_teacher table
--   3. They have created lectures for the course (existing logic)
