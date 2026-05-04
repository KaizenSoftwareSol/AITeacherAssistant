-- migrations/seed_feedback_sample_rollback.sql
-- Removes ONLY the demo rows inserted by seed_feedback_sample.sql

DELETE FROM feedback
WHERE title IN (
    'Lecture generation gets stuck at 80%',
    'Result analytics page is slow',
    'Minor typo in lecture editor button'
)
AND (
    description LIKE 'When I try generating a lecture from the student flow%'
    OR description LIKE 'The analytics tab for assessments takes around 4-6 seconds%'
    OR description LIKE 'The "Create Lecture" button had a typo in one section%'
);
