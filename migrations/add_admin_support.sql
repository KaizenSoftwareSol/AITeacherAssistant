-- Migration: Add Admin Support
-- Description: Adds optional constraints and indexes to support admin users
-- Date: 2024

-- ============================================================
-- PART 1: Add Check Constraint for Admin Users
-- Ensures that ADMIN users must have a university_id
-- ============================================================

-- Add check constraint to ensure ADMIN users have university_id
ALTER TABLE public.users
ADD CONSTRAINT check_admin_has_university
CHECK (
    (role != 'ADMIN') OR (role = 'ADMIN' AND university_id IS NOT NULL)
);

-- Add comment explaining the constraint
COMMENT ON CONSTRAINT check_admin_has_university ON public.users IS 
'Ensures that users with ADMIN role must be associated with a university';

-- ============================================================
-- PART 2: Add Performance Index
-- Index for querying users by role and university (useful for admin queries)
-- ============================================================

-- Create composite index for role and university_id queries
CREATE INDEX IF NOT EXISTS idx_users_role_university_id 
ON public.users(role, university_id)
WHERE role = 'ADMIN';

-- Add comment explaining the index
COMMENT ON INDEX idx_users_role_university_id IS 
'Index for efficiently querying admin users by university';

-- ============================================================
-- PART 3: Add Documentation Comments
-- ============================================================

-- Add comment to role column explaining valid values
COMMENT ON COLUMN public.users.role IS 
'User role: STUDENT, TEACHER, or ADMIN. ADMIN users must have a university_id.';

-- Add comment to university_id column
COMMENT ON COLUMN public.users.university_id IS 
'Foreign key to university. Required for ADMIN users, optional for others.';
