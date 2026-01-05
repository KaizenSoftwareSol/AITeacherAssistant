-- Migration: Add chunk_type to search_lecture_chunks function
-- This allows the AI chatbot to distinguish between lecture content and source material
-- Date: 2025-01-02

-- Drop the old function
DROP FUNCTION IF EXISTS public.search_lecture_chunks(uuid, public.vector, integer);

-- Create the updated function that returns chunk_type
CREATE OR REPLACE FUNCTION public.search_lecture_chunks(
    p_lecture_id uuid, 
    p_query_embedding public.vector, 
    p_limit integer DEFAULT 5
) 
RETURNS TABLE(
    chunk_id uuid, 
    chunk_content text, 
    chunk_index integer, 
    chunk_type text,
    chunk_metadata text, 
    similarity_score double precision
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT 
    lc.id AS chunk_id,
    lc.content AS chunk_content,
    lc.chunk_index AS chunk_index,
    lc.chunk_type::text AS chunk_type,
    lc.chunk_metadata::text AS chunk_metadata,
    1 - (le.embedding <=> p_query_embedding) AS similarity_score
  FROM public.lecture_embedding le
  JOIN public.lecture_chunk lc ON le.chunk_id = lc.id
  WHERE le.lecture_id = p_lecture_id
  ORDER BY le.embedding <=> p_query_embedding
  LIMIT p_limit;
END;
$$;

-- Add comment
COMMENT ON FUNCTION public.search_lecture_chunks(uuid, public.vector, integer) 
IS 'Performs cosine similarity search to find the most relevant lecture chunks for a given query embedding. Returns chunk_type to distinguish between LECTURE_CONTENT and SOURCE_MATERIAL.';

