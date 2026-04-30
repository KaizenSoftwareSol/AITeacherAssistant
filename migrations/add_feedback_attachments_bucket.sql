-- migrations/add_feedback_attachments_bucket.sql
-- Creates feedback screenshots bucket if it does not already exist.

INSERT INTO storage.buckets (id, name, public)
VALUES ('feedback-attachments', 'feedback-attachments', true)
ON CONFLICT (id) DO NOTHING;
