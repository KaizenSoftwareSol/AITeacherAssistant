-- Migration: Add System Role Support
-- Description: Adds SYSTEM role support and updates constraints to allow SYSTEM users without university_id
-- Date: 2024-01-15

-- ============================================================
-- PART 1: Add Check Constraint for Valid Roles
-- Ensures role column only accepts valid values: STUDENT, TEACHER, ADMIN, SYSTEM
-- ============================================================

-- Drop any existing constraint that validates role values (if exists)
-- We'll add our own constraint below
DO $$
DECLARE
    constraint_name text;
BEGIN
    -- Find any constraint that validates role values using IN clause
    SELECT conname INTO constraint_name
    FROM pg_constraint 
    WHERE conrelid = 'public.users'::regclass
    AND pg_get_constraintdef(oid) LIKE '%role%IN%'
    LIMIT 1;
    
    -- Drop it if found
    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE public.users DROP CONSTRAINT IF EXISTS %I', constraint_name);
        RAISE NOTICE 'Dropped existing role constraint: %', constraint_name;
    ELSE
        RAISE NOTICE 'No existing role constraint found, proceeding to add new one';
    END IF;
END
$$;

-- Add check constraint to ensure role is one of the valid values
-- This explicitly allows: STUDENT, TEACHER, ADMIN, SYSTEM
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'check_role_valid_values' 
        AND conrelid = 'public.users'::regclass
    ) THEN
        ALTER TABLE public.users
        ADD CONSTRAINT check_role_valid_values
        CHECK (role IN ('STUDENT', 'TEACHER', 'ADMIN', 'SYSTEM'));
        
        RAISE NOTICE 'Added check_role_valid_values constraint';
    ELSE
        RAISE NOTICE 'Constraint check_role_valid_values already exists';
    END IF;
END
$$;

-- Add comment explaining the constraint
COMMENT ON CONSTRAINT check_role_valid_values ON public.users IS 
'Ensures role column only accepts valid values: STUDENT, TEACHER, ADMIN, or SYSTEM';

-- ============================================================
-- PART 2: Update Check Constraint for Role and University
-- Allows SYSTEM users to have NULL university_id while requiring it for ADMIN users
-- ============================================================

-- Drop the existing constraint if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'check_admin_has_university' 
        AND conrelid = 'public.users'::regclass
    ) THEN
        ALTER TABLE public.users
        DROP CONSTRAINT check_admin_has_university;
        
        RAISE NOTICE 'Dropped existing check_admin_has_university constraint';
    ELSE
        RAISE NOTICE 'Constraint check_admin_has_university does not exist, skipping drop';
    END IF;
END
$$;

-- Add updated check constraint that allows SYSTEM users to have NULL university_id
-- ADMIN users must have university_id
-- Other roles (STUDENT, TEACHER) can have NULL (existing behavior)
ALTER TABLE public.users
ADD CONSTRAINT check_role_university_requirements
CHECK (
    -- SYSTEM users can have NULL university_id
    (role = 'SYSTEM') OR
    -- ADMIN users must have university_id
    (role != 'ADMIN') OR
    (role = 'ADMIN' AND university_id IS NOT NULL)
);

-- Add comment explaining the constraint
COMMENT ON CONSTRAINT check_role_university_requirements ON public.users IS 
'Ensures that: (1) SYSTEM users can have NULL university_id, (2) ADMIN users must have university_id, (3) Other roles follow existing rules';

-- ============================================================
-- PART 3: Update Performance Index
-- Add SYSTEM role to the index if needed (optional, for future queries)
-- ============================================================

-- Note: The existing index idx_users_role_university_id is filtered for ADMIN role only
-- We may want to create a separate index for SYSTEM users if needed, but for now
-- SYSTEM users are likely to be queried less frequently, so we'll skip a dedicated index

-- Update the index comment to clarify it's for ADMIN only (if index exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE schemaname = 'public' 
        AND tablename = 'users' 
        AND indexname = 'idx_users_role_university_id'
    ) THEN
        EXECUTE 'COMMENT ON INDEX public.idx_users_role_university_id IS ''Index for efficiently querying admin users by university. Does not include SYSTEM users.''';
        RAISE NOTICE 'Updated comment on idx_users_role_university_id';
    ELSE
        RAISE NOTICE 'Index idx_users_role_university_id does not exist, skipping comment update';
    END IF;
END
$$;

-- ============================================================
-- PART 4: Update Documentation Comments
-- ============================================================

-- Update comment on role column to include SYSTEM role
COMMENT ON COLUMN public.users.role IS 
'User role: STUDENT, TEACHER, ADMIN, or SYSTEM. ADMIN users must have a university_id. SYSTEM users can have NULL university_id.';

-- Update comment on university_id column to reflect SYSTEM role
COMMENT ON COLUMN public.users.university_id IS 
'Foreign key to university. Required for ADMIN users. NULL allowed for SYSTEM users. Optional for STUDENT and TEACHER.';

-- ============================================================
-- PART 5: Add Index for SYSTEM Role Queries (Optional Performance Enhancement)
-- ============================================================

-- Create index for SYSTEM role queries (if there will be many system users)
-- Note: Currently only one system user is expected, so this is optional
CREATE INDEX IF NOT EXISTS idx_users_role_system 
ON public.users(role)
WHERE role = 'SYSTEM';

COMMENT ON INDEX idx_users_role_system IS 
'Index for efficiently querying SYSTEM role users. Optional index for future scalability.';

-- ============================================================
-- VERIFICATION QUERIES (Run these to verify the migration)
-- ============================================================

-- Verify the role valid values constraint exists
-- SELECT conname, pg_get_constraintdef(oid) 
-- FROM pg_constraint 
-- WHERE conrelid = 'public.users'::regclass 
-- AND conname = 'check_role_valid_values';

-- Verify the role/university requirements constraint exists
-- SELECT conname, pg_get_constraintdef(oid) 
-- FROM pg_constraint 
-- WHERE conrelid = 'public.users'::regclass 
-- AND conname = 'check_role_university_requirements';

-- Verify all constraints on users table
-- SELECT conname, pg_get_constraintdef(oid) 
-- FROM pg_constraint 
-- WHERE conrelid = 'public.users'::regclass 
-- ORDER BY conname;

-- Verify indexes exist
-- SELECT indexname, indexdef 
-- FROM pg_indexes 
-- WHERE tablename = 'users' 
-- AND schemaname = 'public';

-- Check current role values in the database
-- SELECT DISTINCT role, COUNT(*) 
-- FROM public.users 
-- GROUP BY role;

-- Verify SYSTEM role can be used (this should work after migration)
-- SELECT role, university_id 
-- FROM public.users 
-- WHERE role = 'SYSTEM';
