-- migrations/add_notifications.sql
-- Migration to create the notifications table for the AITA platform
-- Run this migration in your Supabase SQL editor

-- ==================== Create Notifications Table ====================

CREATE TABLE IF NOT EXISTS notification (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    type INTEGER NOT NULL,              -- NotificationType enum value
    severity INTEGER DEFAULT 1,         -- NotificationSeverity enum (1=Info, 2=Success, 3=Warning, 4=Danger)
    is_read BOOLEAN DEFAULT FALSE,
    is_archived BOOLEAN DEFAULT FALSE,
    feature_type INTEGER DEFAULT 101,   -- For frontend categorization
    
    -- Related entity info for deep linking
    related_entity_type VARCHAR(50),    -- 'course', 'lecture', 'quiz', 'assessment', etc.
    related_entity_id UUID,             -- ID of related entity
    action_url VARCHAR(500),            -- Deep link URL
    
    -- Multi-tenant support
    company_key VARCHAR(100),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    read_at TIMESTAMP WITH TIME ZONE
);

-- ==================== Create Indexes for Performance ====================

-- Index for fetching user's notifications (most common query)
CREATE INDEX IF NOT EXISTS idx_notification_user_unread 
    ON notification(user_id, is_read, is_archived, created_at DESC);

-- Index for filtering by type
CREATE INDEX IF NOT EXISTS idx_notification_user_type 
    ON notification(user_id, type);

-- Index for created_at sorting
CREATE INDEX IF NOT EXISTS idx_notification_created 
    ON notification(created_at DESC);

-- Index for unread count queries
CREATE INDEX IF NOT EXISTS idx_notification_unread_count 
    ON notification(user_id, is_read) 
    WHERE is_read = FALSE AND is_archived = FALSE;

-- ==================== Enable Row Level Security (RLS) ====================

ALTER TABLE notification ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own notifications
CREATE POLICY "Users can view own notifications" 
    ON notification FOR SELECT 
    USING (user_id = auth.uid());

-- Policy: Users can update their own notifications (mark as read, archive)
CREATE POLICY "Users can update own notifications" 
    ON notification FOR UPDATE 
    USING (user_id = auth.uid());

-- Policy: Users can delete their own notifications
CREATE POLICY "Users can delete own notifications" 
    ON notification FOR DELETE 
    USING (user_id = auth.uid());

-- Policy: System can insert notifications for any user
-- (This uses service role key, not affected by RLS)
CREATE POLICY "Service can insert notifications" 
    ON notification FOR INSERT 
    WITH CHECK (true);

-- ==================== Comments ====================

COMMENT ON TABLE notification IS 'Notification system for the AITA platform';
COMMENT ON COLUMN notification.type IS 'NotificationType enum: 1=StudentEnrolled, 2=Pending, 3=QuizSubmitted, 4=ResultRequest, 5=LecturePublished, 6=QuizPublished, 7=ResultApproved, 8=ResultRejected, 9=NewAssessment, 10=CourseUpdate, 11=DeadlineReminder, 12=ResultsReady, 13=LowScore, 14=EnrollmentConfirmed';
COMMENT ON COLUMN notification.severity IS 'NotificationSeverity enum: 1=Info, 2=Success, 3=Warning, 4=Danger';

-- ==================== Notification Types Reference ====================
/*
Notification Types:
1  = STUDENT_ENROLLED      - Teacher notified when student enrolls
2  = PENDING               - Generic pending notification
3  = QUIZ_SUBMITTED        - Teacher notified when student submits quiz
4  = RESULT_REQUEST        - Teacher notified when student requests results
5  = LECTURE_PUBLISHED     - Students notified when lecture is published
6  = QUIZ_PUBLISHED        - Students notified when quiz is published
7  = RESULT_APPROVED       - Student notified when result request approved
8  = RESULT_REJECTED       - Student notified when result request rejected
9  = NEW_ASSESSMENT_AVAILABLE - Student notified of new assessment
10 = COURSE_UPDATE         - Students notified of course updates
11 = QUIZ_DEADLINE_REMINDER - Student reminded of upcoming deadline
12 = QUIZ_RESULTS_READY    - Student notified results are ready
13 = LOW_QUIZ_SCORE        - Teacher notified of low-scoring student
14 = ENROLLMENT_CONFIRMED  - Student notified enrollment successful

Severity Levels:
1 = INFO     - General information (blue)
2 = SUCCESS  - Positive actions completed (green)
3 = WARNING  - Requires attention (yellow/orange)
4 = DANGER   - Urgent/critical alerts (red)
*/

