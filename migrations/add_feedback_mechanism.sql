-- migrations/add_feedback_mechanism.sql
-- Feedback mechanism for Student/Teacher users with SYSTEM response workflow.

CREATE TABLE IF NOT EXISTS feedback (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_role VARCHAR(20) NOT NULL CHECK (user_role IN ('STUDENT', 'TEACHER')),
    feature_area VARCHAR(50) NOT NULL CHECK (
        feature_area IN (
            'LECTURE_GENERATION',
            'RESULT_TRACKING',
            'LECTURE_CREATION',
            'ASSESSMENTS',
            'COURSES',
            'NOTIFICATIONS',
            'OTHER'
        )
    ),
    difficulty_level VARCHAR(20) NOT NULL CHECK (
        difficulty_level IN ('LOW', 'MEDIUM', 'HIGH', 'BLOCKER')
    ),
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN' CHECK (
        status IN ('OPEN', 'IN_REVIEW', 'RESPONDED', 'CLOSED')
    ),
    system_response TEXT,
    responded_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    responded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT feedback_attachments_max_three CHECK (jsonb_array_length(attachments) <= 3)
);

CREATE INDEX IF NOT EXISTS idx_feedback_user_created_at
    ON feedback(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_feedback_status_created_at
    ON feedback(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_feedback_feature_area
    ON feedback(feature_area);

CREATE OR REPLACE FUNCTION set_feedback_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_feedback_updated_at ON feedback;
CREATE TRIGGER trg_feedback_updated_at
    BEFORE UPDATE ON feedback
    FOR EACH ROW
    EXECUTE FUNCTION set_feedback_updated_at();
