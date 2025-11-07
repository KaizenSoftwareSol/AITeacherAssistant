-- Add document_id to lecture table to track source document
-- This enables duplicate detection based on document + course + semester

ALTER TABLE public.lecture
ADD COLUMN document_id uuid;

-- Add foreign key constraint
ALTER TABLE public.lecture
ADD CONSTRAINT lecture_document_id_fkey 
FOREIGN KEY (document_id) 
REFERENCES public.documents(id) 
ON DELETE SET NULL;

-- Add index for faster duplicate checks
CREATE INDEX idx_lecture_document_course_semester 
ON public.lecture(document_id, course_id, semester_id);

COMMENT ON COLUMN public.lecture.document_id IS 'Source document used to generate this lecture. Used for duplicate detection.';

