-- Migration: add_teacher_activity_log
-- Tracks key teacher actions on the live platform for admin observability.

CREATE TABLE IF NOT EXISTS teacher_activity_log (
    id          BIGSERIAL PRIMARY KEY,
    uuid        UUID        NOT NULL DEFAULT gen_random_uuid(),
    teacher_id  INTEGER,               -- FK to teacher.id (nullable: login events may not have it yet)
    user_id     INTEGER,               -- FK to users.id
    university_id INTEGER,
    activity_type VARCHAR(50) NOT NULL, -- LOGIN | GENERATE_LECTURE | GENERATE_LEARNING_MATERIALS | DELETE_LECTURE | PUBLISH_LECTURE
    lecture_id  INTEGER,               -- FK to lecture.id (null for login events)
    lecture_name TEXT,                 -- snapshot of lecture title at time of action
    metadata    JSONB        NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tal_teacher_id      ON teacher_activity_log (teacher_id);
CREATE INDEX IF NOT EXISTS idx_tal_university_id   ON teacher_activity_log (university_id);
CREATE INDEX IF NOT EXISTS idx_tal_activity_type   ON teacher_activity_log (activity_type);
CREATE INDEX IF NOT EXISTS idx_tal_created_at_desc ON teacher_activity_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tal_lecture_id      ON teacher_activity_log (lecture_id);
