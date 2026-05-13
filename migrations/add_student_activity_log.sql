-- migrations/add_student_activity_log.sql
-- Adds student_id column to teacher_activity_log so the same table
-- tracks both teacher and student events.  New STUDENT_* activity types
-- are distinguished purely by the activity_type VARCHAR value; no enum
-- change is needed.

ALTER TABLE teacher_activity_log
    ADD COLUMN IF NOT EXISTS student_id INTEGER;

CREATE INDEX IF NOT EXISTS idx_tal_student_id
    ON teacher_activity_log (student_id);

-- Helpful composite index for admin queries filtered by university + user_type
-- (teacher vs student is inferred from activity_type prefix)
CREATE INDEX IF NOT EXISTS idx_tal_univ_type
    ON teacher_activity_log (university_id, activity_type, created_at DESC);
