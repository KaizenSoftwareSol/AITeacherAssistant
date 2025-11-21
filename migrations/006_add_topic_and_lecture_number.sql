-- Add topic and lecture_number to lecture table
-- This enables grouping lectures by topic and numbering them sequentially within each topic

ALTER TABLE public.lecture
ADD COLUMN topic VARCHAR(255);

ALTER TABLE public.lecture
ADD COLUMN lecture_number INTEGER;

-- Add index for faster queries by topic
CREATE INDEX idx_lecture_topic ON public.lecture(topic);

-- Add composite index for topic + course + semester to support lecture numbering
CREATE INDEX idx_lecture_topic_course_semester 
ON public.lecture(topic, course_id, semester_id);

COMMENT ON COLUMN public.lecture.topic IS 'Topic name for grouping lectures (e.g., CLUSTERING, PREDICTION, REGRESSION)';
COMMENT ON COLUMN public.lecture.lecture_number IS 'Sequential number of this lecture within its topic (starts from 1 for each topic)';

