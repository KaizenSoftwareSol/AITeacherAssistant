-- Migration: Rename metadata column to chunk_metadata
-- Date: 2025-10-27
-- Description: Fixes the reserved field name issue by renaming metadata to chunk_metadata

-- ============================================================
-- Check if the old column exists and rename it
-- ============================================================

DO $$
BEGIN
    -- Check if the table exists
    IF EXISTS (
        SELECT FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename = 'lecture_chunk'
    ) THEN
        -- Check if old column 'metadata' exists
        IF EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'lecture_chunk' 
            AND column_name = 'metadata'
        ) THEN
            -- Rename the column
            ALTER TABLE public.lecture_chunk 
            RENAME COLUMN metadata TO chunk_metadata;
            
            RAISE NOTICE 'Renamed column metadata to chunk_metadata in lecture_chunk table';
        ELSE
            RAISE NOTICE 'Column metadata does not exist or already renamed';
        END IF;
    ELSE
        RAISE NOTICE 'Table lecture_chunk does not exist yet - will be created by migration 001';
    END IF;
END $$;

-- ============================================================
-- Update the search function if it exists
-- ============================================================

-- Drop and recreate the function with correct column name
DROP FUNCTION IF EXISTS public.search_lecture_chunks(uuid, vector, integer);

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
-- Completion message
-- ============================================================

DO $$
BEGIN
  RAISE NOTICE '================================================================';
  RAISE NOTICE 'Successfully renamed metadata to chunk_metadata!';
  RAISE NOTICE 'The RAG chatbot should now work correctly.';
  RAISE NOTICE '================================================================';
END $$;

