-- Migration: Add flashcards table for lecture study aids
-- Flashcards are auto-generated when lectures are published

-- Create flashcard table
CREATE TABLE IF NOT EXISTS public.flashcard (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  lecture_id uuid NOT NULL,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  order_index INTEGER NOT NULL DEFAULT 0,
  difficulty VARCHAR(20) DEFAULT 'MEDIUM',
  topic VARCHAR(255),
  created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  
  CONSTRAINT flashcard_pkey PRIMARY KEY (id),
  CONSTRAINT flashcard_lecture_id_fkey FOREIGN KEY (lecture_id) 
    REFERENCES public.lecture(id) ON DELETE CASCADE
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_flashcard_lecture_id 
  ON public.flashcard(lecture_id);

CREATE INDEX IF NOT EXISTS idx_flashcard_lecture_order 
  ON public.flashcard(lecture_id, order_index);

-- Add comment
COMMENT ON TABLE public.flashcard IS 'Flashcards for quick review and study - auto-generated per lecture';
COMMENT ON COLUMN public.flashcard.question IS 'The question or prompt side of the flashcard';
COMMENT ON COLUMN public.flashcard.answer IS 'The answer or explanation side of the flashcard';
COMMENT ON COLUMN public.flashcard.difficulty IS 'Difficulty level: EASY, MEDIUM, HARD';
COMMENT ON COLUMN public.flashcard.topic IS 'Topic or category for grouping flashcards';

