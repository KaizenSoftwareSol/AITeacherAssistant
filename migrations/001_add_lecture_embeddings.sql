-- Migration: Add lecture embeddings and chunks for RAG implementation
-- Date: 2025-10-27
-- Description: Creates tables for storing lecture chunks and their vector embeddings
--              to enable semantic search and RAG-based chatbot functionality

-- ============================================================
-- STEP 1: Enable pgvector extension for vector operations
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- STEP 2: Create lecture_chunk table
-- ============================================================
CREATE TABLE IF NOT EXISTS public.lecture_chunk (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  lecture_id uuid NOT NULL,
  chunk_index integer NOT NULL DEFAULT 0,
  content text NOT NULL,
  chunk_type character varying DEFAULT 'CONTENT'::character varying,
  tokens_count integer DEFAULT 0,
  chunk_metadata text,  -- JSON metadata (page numbers, section titles, etc.)
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT lecture_chunk_pkey PRIMARY KEY (id),
  CONSTRAINT lecture_chunk_lecture_id_fkey FOREIGN KEY (lecture_id) 
    REFERENCES public.lecture(id) ON DELETE CASCADE
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_lecture_chunk_lecture_id ON public.lecture_chunk(lecture_id);
CREATE INDEX IF NOT EXISTS idx_lecture_chunk_index ON public.lecture_chunk(lecture_id, chunk_index);

-- ============================================================
-- STEP 3: Create lecture_embedding table with vector column
-- ============================================================
CREATE TABLE IF NOT EXISTS public.lecture_embedding (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  lecture_id uuid NOT NULL,
  chunk_id uuid,
  embedding vector(1536),  -- OpenAI text-embedding-3-small produces 1536 dimensions
  embedding_model character varying DEFAULT 'text-embedding-3-small'::character varying,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT lecture_embedding_pkey PRIMARY KEY (id),
  CONSTRAINT lecture_embedding_lecture_id_fkey FOREIGN KEY (lecture_id) 
    REFERENCES public.lecture(id) ON DELETE CASCADE,
  CONSTRAINT lecture_embedding_chunk_id_fkey FOREIGN KEY (chunk_id) 
    REFERENCES public.lecture_chunk(id) ON DELETE CASCADE
);

-- Create indexes for efficient vector similarity search
CREATE INDEX IF NOT EXISTS idx_lecture_embedding_lecture_id ON public.lecture_embedding(lecture_id);
CREATE INDEX IF NOT EXISTS idx_lecture_embedding_chunk_id ON public.lecture_embedding(chunk_id);

-- Create HNSW index for fast approximate nearest neighbor search
-- This dramatically speeds up vector similarity queries
CREATE INDEX IF NOT EXISTS idx_lecture_embedding_vector_cosine 
  ON public.lecture_embedding 
  USING hnsw (embedding vector_cosine_ops);

-- Alternative: IVFFlat index (use if HNSW is not available)
-- CREATE INDEX IF NOT EXISTS idx_lecture_embedding_vector_ivfflat 
--   ON public.lecture_embedding 
--   USING ivfflat (embedding vector_cosine_ops)
--   WITH (lists = 100);

-- ============================================================
-- STEP 4: Add summary field to lecture table
-- ============================================================
ALTER TABLE public.lecture 
  ADD COLUMN IF NOT EXISTS summary text;

ALTER TABLE public.lecture 
  ADD COLUMN IF NOT EXISTS has_embeddings boolean DEFAULT false;

-- ============================================================
-- STEP 5: Create helper function for cosine similarity search
-- ============================================================
CREATE OR REPLACE FUNCTION search_lecture_chunks(
  p_lecture_id uuid,
  p_query_embedding vector(1536),
  p_limit integer DEFAULT 5
)
RETURNS TABLE (
  chunk_id uuid,
  chunk_content text,
  chunk_index integer,
  chunk_metadata text,
  similarity_score float
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    lc.id AS chunk_id,
    lc.content AS chunk_content,
    lc.chunk_index AS chunk_index,
    lc.chunk_metadata AS chunk_metadata,
    1 - (le.embedding <=> p_query_embedding) AS similarity_score
  FROM public.lecture_embedding le
  JOIN public.lecture_chunk lc ON le.chunk_id = lc.id
  WHERE le.lecture_id = p_lecture_id
  ORDER BY le.embedding <=> p_query_embedding
  LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- STEP 6: Create function to update has_embeddings flag
-- ============================================================
CREATE OR REPLACE FUNCTION update_lecture_embeddings_flag()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE public.lecture
  SET has_embeddings = EXISTS (
    SELECT 1 FROM public.lecture_embedding 
    WHERE lecture_id = NEW.lecture_id
    LIMIT 1
  )
  WHERE id = NEW.lecture_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update has_embeddings flag
DROP TRIGGER IF EXISTS trigger_update_lecture_embeddings_flag ON public.lecture_embedding;
CREATE TRIGGER trigger_update_lecture_embeddings_flag
  AFTER INSERT OR DELETE ON public.lecture_embedding
  FOR EACH ROW
  EXECUTE FUNCTION update_lecture_embeddings_flag();

-- ============================================================
-- STEP 7: Add indexes for student course enrollment queries
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_enrollment_student_active 
  ON public.enrollment(student_id, is_active);

CREATE INDEX IF NOT EXISTS idx_lecture_course_status 
  ON public.lecture(course_id, status);

-- ============================================================
-- STEP 8: Create view for student course access
-- ============================================================
CREATE OR REPLACE VIEW student_course_lectures AS
SELECT 
  e.student_id,
  e.course_id,
  c.code AS course_code,
  c.name AS course_name,
  l.id AS lecture_id,
  l.title AS lecture_title,
  l.description AS lecture_description,
  l.summary AS lecture_summary,
  l.status AS lecture_status,
  l.has_embeddings,
  l.created_at AS lecture_created_at,
  t.id AS teacher_id,
  u.first_name || ' ' || u.last_name AS teacher_name
FROM public.enrollment e
JOIN public.course c ON e.course_id = c.id
JOIN public.lecture l ON l.course_id = c.id
JOIN public.teacher t ON l.teacher_id = t.id
JOIN public.users u ON t.user_id = u.id
WHERE e.is_active = true 
  AND l.status IN ('PUBLISHED', 'DELIVERED');

-- ============================================================
-- STEP 9: Add comments for documentation
-- ============================================================
COMMENT ON TABLE public.lecture_chunk IS 
  'Stores chunked lecture content for RAG (Retrieval-Augmented Generation). Each lecture is split into smaller chunks for efficient semantic search.';

COMMENT ON TABLE public.lecture_embedding IS 
  'Stores vector embeddings for lecture chunks to enable semantic search. Used for RAG-based chatbot responses.';

COMMENT ON COLUMN public.lecture_embedding.embedding IS 
  'Vector embedding of the chunk content. Default dimension is 1536 for OpenAI text-embedding-3-small model.';

COMMENT ON FUNCTION search_lecture_chunks IS 
  'Performs cosine similarity search to find the most relevant lecture chunks for a given query embedding.';

COMMENT ON VIEW student_course_lectures IS 
  'View that shows all published lectures accessible to enrolled students with teacher information.';

