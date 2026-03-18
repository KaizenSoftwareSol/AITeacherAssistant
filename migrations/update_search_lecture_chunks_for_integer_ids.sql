-- Migration: Update search_lecture_chunks function to use bigint instead of uuid
-- This is required after migrating lecture_id columns from uuid to bigint
-- Date: 2026-03-10

-- Drop the old function
DROP FUNCTION IF EXISTS public.search_lecture_chunks(uuid, public.vector, integer);

-- Create the updated function that accepts bigint lecture_id
CREATE OR REPLACE FUNCTION public.search_lecture_chunks(
    p_lecture_id bigint,  -- Changed from uuid to bigint
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
    lc.uuid AS chunk_id,  -- Return UUID for external APIs
    lc.content AS chunk_content,
    lc.chunk_index AS chunk_index,
    lc.chunk_type::text AS chunk_type,
    lc.chunk_metadata::text AS chunk_metadata,
    1 - (le.embedding <=> p_query_embedding) AS similarity_score
  FROM public.lecture_embedding le
  JOIN public.lecture_chunk lc ON le.chunk_id = lc.id  -- Join on integer IDs
  WHERE le.lecture_id = p_lecture_id  -- Compare bigint to bigint
  ORDER BY le.embedding <=> p_query_embedding
  LIMIT p_limit;
END;
$$;

-- Add comment
COMMENT ON FUNCTION public.search_lecture_chunks(bigint, public.vector, integer) 
IS 'Performs cosine similarity search to find the most relevant lecture chunks for a given query embedding. Updated to use bigint lecture_id after migration. Returns chunk_type to distinguish between LECTURE_CONTENT and SOURCE_MATERIAL.';
