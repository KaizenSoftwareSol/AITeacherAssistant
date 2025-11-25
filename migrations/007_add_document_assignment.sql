-- Migration: Add document_assignment table for linking documents to courses
-- This allows teachers to assign documents to courses with optional topics

-- Create document_assignment table
CREATE TABLE IF NOT EXISTS public.document_assignment (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL,
  course_id uuid NOT NULL,
  topic VARCHAR(255),
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  
  CONSTRAINT document_assignment_pkey PRIMARY KEY (id),
  CONSTRAINT document_assignment_document_id_fkey FOREIGN KEY (document_id) 
    REFERENCES public.documents(id) ON DELETE CASCADE,
  CONSTRAINT document_assignment_course_id_fkey FOREIGN KEY (course_id) 
    REFERENCES public.course(id) ON DELETE CASCADE,
  CONSTRAINT document_assignment_unique UNIQUE (document_id, course_id)
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_document_assignment_document_id 
  ON public.document_assignment(document_id);

CREATE INDEX IF NOT EXISTS idx_document_assignment_course_id 
  ON public.document_assignment(course_id);

CREATE INDEX IF NOT EXISTS idx_document_assignment_topic 
  ON public.document_assignment(topic) WHERE topic IS NOT NULL;

-- Add comments
COMMENT ON TABLE public.document_assignment IS 'Links documents to courses, allowing teachers to assign documents to specific courses with optional topics';
COMMENT ON COLUMN public.document_assignment.document_id IS 'The document being assigned';
COMMENT ON COLUMN public.document_assignment.course_id IS 'The course the document is assigned to';
COMMENT ON COLUMN public.document_assignment.topic IS 'Optional topic/category for the assignment (e.g., "Law Prevelance")';

