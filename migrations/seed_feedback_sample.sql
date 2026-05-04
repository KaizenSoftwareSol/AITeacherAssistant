-- migrations/seed_feedback_sample.sql
-- Sample seed data for feedback feature.
-- Run AFTER: migrations/add_feedback_mechanism.sql

WITH selected_users AS (
    SELECT
        (SELECT id FROM users WHERE role = 'STUDENT' ORDER BY created_at ASC LIMIT 1) AS student_id,
        (SELECT id FROM users WHERE role = 'TEACHER' ORDER BY created_at ASC LIMIT 1) AS teacher_id,
        (SELECT id FROM users WHERE role = 'SYSTEM' ORDER BY created_at ASC LIMIT 1) AS system_id
),
seed_rows AS (
    -- Student sample: open feedback
    SELECT
        gen_random_uuid() AS uuid,
        su.student_id AS user_id,
        'STUDENT'::varchar AS user_role,
        'LECTURE_GENERATION'::varchar AS feature_area,
        'HIGH'::varchar AS difficulty_level,
        'Lecture generation gets stuck at 80%'::varchar AS title,
        'When I try generating a lecture from the student flow, the spinner keeps running and never completes.'::text AS description,
        '[]'::jsonb AS attachments,
        'OPEN'::varchar AS status,
        NULL::text AS system_response,
        NULL::bigint AS responded_by_user_id,
        NULL::timestamptz AS responded_at,
        NOW() - INTERVAL '2 days' AS created_at,
        NOW() - INTERVAL '2 days' AS updated_at
    FROM selected_users su
    WHERE su.student_id IS NOT NULL

    UNION ALL

    -- Teacher sample: responded feedback
    SELECT
        gen_random_uuid() AS uuid,
        su.teacher_id AS user_id,
        'TEACHER'::varchar AS user_role,
        'RESULT_TRACKING'::varchar AS feature_area,
        'MEDIUM'::varchar AS difficulty_level,
        'Result analytics page is slow'::varchar AS title,
        'The analytics tab for assessments takes around 4-6 seconds during peak hours.'::text AS description,
        '[]'::jsonb AS attachments,
        CASE WHEN su.system_id IS NOT NULL THEN 'RESPONDED' ELSE 'IN_REVIEW' END::varchar AS status,
        CASE
            WHEN su.system_id IS NOT NULL THEN 'Thanks for reporting this. We have optimized the query and deployed a fix; please recheck.'
            ELSE NULL
        END::text AS system_response,
        su.system_id AS responded_by_user_id,
        CASE WHEN su.system_id IS NOT NULL THEN NOW() - INTERVAL '20 hours' ELSE NULL END::timestamptz AS responded_at,
        NOW() - INTERVAL '1 day' AS created_at,
        NOW() - INTERVAL '20 hours' AS updated_at
    FROM selected_users su
    WHERE su.teacher_id IS NOT NULL

    UNION ALL

    -- Teacher sample: closed feedback
    SELECT
        gen_random_uuid() AS uuid,
        su.teacher_id AS user_id,
        'TEACHER'::varchar AS user_role,
        'LECTURE_CREATION'::varchar AS feature_area,
        'LOW'::varchar AS difficulty_level,
        'Minor typo in lecture editor button'::varchar AS title,
        'The "Create Lecture" button had a typo in one section. Issue is now resolved.'::text AS description,
        '[]'::jsonb AS attachments,
        CASE WHEN su.system_id IS NOT NULL THEN 'CLOSED' ELSE 'IN_REVIEW' END::varchar AS status,
        CASE
            WHEN su.system_id IS NOT NULL THEN 'Confirmed and fixed in latest release. Closing this ticket.'
            ELSE NULL
        END::text AS system_response,
        su.system_id AS responded_by_user_id,
        CASE WHEN su.system_id IS NOT NULL THEN NOW() - INTERVAL '8 hours' ELSE NULL END::timestamptz AS responded_at,
        NOW() - INTERVAL '12 hours' AS created_at,
        NOW() - INTERVAL '8 hours' AS updated_at
    FROM selected_users su
    WHERE su.teacher_id IS NOT NULL
)
INSERT INTO feedback (
    uuid,
    user_id,
    user_role,
    feature_area,
    difficulty_level,
    title,
    description,
    attachments,
    status,
    system_response,
    responded_by_user_id,
    responded_at,
    created_at,
    updated_at
)
SELECT *
FROM seed_rows;
