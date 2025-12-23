-- Migration: Add result_view_request table for graded quiz result approval mechanism
-- This allows students to request viewing their graded quiz results, which teachers can approve/reject

-- Create the result_view_request table
CREATE TABLE IF NOT EXISTS result_view_request (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id UUID NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES student(id) ON DELETE CASCADE,
    teacher_id UUID NOT NULL REFERENCES teacher(id) ON DELETE CASCADE,
    
    -- Request details
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    request_message TEXT,  -- Optional message from student
    response_message TEXT,  -- Optional message from teacher
    
    -- Timestamps
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    responded_at TIMESTAMP WITH TIME ZONE,
    
    -- Ensure one request per student per assessment
    UNIQUE(assessment_id, student_id)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_result_view_request_assessment ON result_view_request(assessment_id);
CREATE INDEX IF NOT EXISTS idx_result_view_request_student ON result_view_request(student_id);
CREATE INDEX IF NOT EXISTS idx_result_view_request_teacher ON result_view_request(teacher_id);
CREATE INDEX IF NOT EXISTS idx_result_view_request_status ON result_view_request(status);
CREATE INDEX IF NOT EXISTS idx_result_view_request_teacher_pending ON result_view_request(teacher_id, status) WHERE status = 'PENDING';

-- Enable Row Level Security
ALTER TABLE result_view_request ENABLE ROW LEVEL SECURITY;

-- RLS Policies

-- Students can view their own requests
CREATE POLICY "Students can view own result view requests" ON result_view_request
    FOR SELECT
    USING (
        student_id IN (
            SELECT id FROM student WHERE user_id = auth.uid()
        )
    );

-- Students can create requests for quizzes they have submitted
CREATE POLICY "Students can create result view requests" ON result_view_request
    FOR INSERT
    WITH CHECK (
        student_id IN (
            SELECT id FROM student WHERE user_id = auth.uid()
        )
        AND EXISTS (
            SELECT 1 FROM assessment_submission
            WHERE assessment_submission.assessment_id = result_view_request.assessment_id
            AND assessment_submission.student_id = result_view_request.student_id
            AND assessment_submission.is_submitted = true
        )
    );

-- Teachers can view requests for their assessments
CREATE POLICY "Teachers can view result view requests for their assessments" ON result_view_request
    FOR SELECT
    USING (
        teacher_id IN (
            SELECT id FROM teacher WHERE user_id = auth.uid()
        )
    );

-- Teachers can update (approve/reject) requests for their assessments
CREATE POLICY "Teachers can update result view requests" ON result_view_request
    FOR UPDATE
    USING (
        teacher_id IN (
            SELECT id FROM teacher WHERE user_id = auth.uid()
        )
    )
    WITH CHECK (
        teacher_id IN (
            SELECT id FROM teacher WHERE user_id = auth.uid()
        )
    );

-- Grant permissions to authenticated users
GRANT SELECT, INSERT ON result_view_request TO authenticated;
GRANT UPDATE (status, response_message, responded_at) ON result_view_request TO authenticated;

-- Add comment for documentation
COMMENT ON TABLE result_view_request IS 'Stores student requests to view graded quiz results. Teachers approve/reject these requests.';
COMMENT ON COLUMN result_view_request.status IS 'Request status: PENDING (awaiting teacher response), APPROVED (student can view results), REJECTED (student cannot view results)';

