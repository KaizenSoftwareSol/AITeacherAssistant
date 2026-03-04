-- Migration: Add University Type and Module Layer
-- Purpose: Support different university hierarchies
--   MEDICAL: Semester → Modules → Courses
--   Others:  Semester → Courses (no modules)

-- ============================================
-- PART 1: Add 'type' column to university
-- ============================================

ALTER TABLE public.university
ADD COLUMN IF NOT EXISTS type character varying DEFAULT 'GENERAL' NOT NULL;

ALTER TABLE public.university
ADD CONSTRAINT check_university_type CHECK (
  type IN ('MEDICAL', 'ENGINEERING', 'LAW', 'BUSINESS', 'ARTS', 'GENERAL')
);

CREATE INDEX IF NOT EXISTS idx_university_type ON public.university(type);

COMMENT ON COLUMN public.university.type IS
'University type determines organizational hierarchy. Modules are only used for MEDICAL universities.';


-- ============================================
-- PART 2: Create module table (lives inside a semester)
-- ============================================

CREATE TABLE IF NOT EXISTS public.module (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name character varying NOT NULL,
  description text,
  semester_id uuid NOT NULL,
  university_id uuid NOT NULL,
  display_order integer DEFAULT 0,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT module_pkey PRIMARY KEY (id),
  CONSTRAINT module_semester_id_fkey FOREIGN KEY (semester_id)
    REFERENCES public.semester(id) ON DELETE CASCADE,
  CONSTRAINT module_university_id_fkey FOREIGN KEY (university_id)
    REFERENCES public.university(id) ON DELETE CASCADE,
  CONSTRAINT uq_module_name_semester UNIQUE (name, semester_id)
);

COMMENT ON TABLE public.module IS
'Semester-specific grouping of courses for MEDICAL universities. E.g. Semester 3 → Module "Urology" → Courses [Anatomy, Community Health].';

CREATE INDEX IF NOT EXISTS idx_module_semester ON public.module(semester_id);
CREATE INDEX IF NOT EXISTS idx_module_university ON public.module(university_id);


-- ============================================
-- PART 3: Create module_course junction table
-- ============================================

CREATE TABLE IF NOT EXISTS public.module_course (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  module_id uuid NOT NULL,
  course_id uuid NOT NULL,
  display_order integer DEFAULT 0,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT module_course_pkey PRIMARY KEY (id),
  CONSTRAINT module_course_module_id_fkey FOREIGN KEY (module_id)
    REFERENCES public.module(id) ON DELETE CASCADE,
  CONSTRAINT module_course_course_id_fkey FOREIGN KEY (course_id)
    REFERENCES public.course(id) ON DELETE CASCADE,
  CONSTRAINT uq_module_course UNIQUE (module_id, course_id)
);

COMMENT ON TABLE public.module_course IS
'Junction table linking modules to courses. A course can appear in multiple modules across semesters.';

CREATE INDEX IF NOT EXISTS idx_module_course_module ON public.module_course(module_id);
CREATE INDEX IF NOT EXISTS idx_module_course_course ON public.module_course(course_id);
