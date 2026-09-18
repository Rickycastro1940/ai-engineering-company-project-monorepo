-- ============================================================
-- EduTrack Data Audit — queries.sql
-- Target: enrollments only. Do not UPDATE/DELETE students or courses.
-- Run in this order: 1–5 read the seed (17 rows), 6–8 correct it,
-- 9–12 report on the cleaned table (16 rows).
-- Before every UPDATE or DELETE, run the matching SELECT first.
-- ============================================================

-- Verify import
SELECT * FROM enrollments LIMIT 5;


-- ------------------------------------------------------------
-- Q1. Enrollments in 'Intro to Python'
-- ------------------------------------------------------------
SELECT student_name, student_email, completion_percentage
FROM enrollments
WHERE course_title = 'Intro to Python'
ORDER BY completion_percentage DESC;


-- ------------------------------------------------------------
-- Q2. Completion below 10% (includes never-started at 0%)
-- ------------------------------------------------------------
SELECT id, student_name, student_email, course_title, completion_percentage
FROM enrollments
WHERE completion_percentage < 10
ORDER BY completion_percentage ASC, student_name;


-- ------------------------------------------------------------
-- Q3. Missing instructor (IS NULL — not = NULL)
-- ------------------------------------------------------------
SELECT id, student_name, course_title, enrollment_date, instructor
FROM enrollments
WHERE instructor IS NULL;


-- ------------------------------------------------------------
-- Q4. Highest completion among students who have not passed
-- ------------------------------------------------------------
SELECT id, student_name, course_title, completion_percentage, passed
FROM enrollments
WHERE passed = FALSE
ORDER BY completion_percentage DESC
LIMIT 5;


-- ------------------------------------------------------------
-- Q5. Enrollments dated 2025-01-01 or later (calendar 2025+ in the seed)
--     Newest first. Seed newest date is 2025-03-05.
-- ------------------------------------------------------------
SELECT id, student_name, course_title, enrollment_date, completion_percentage
FROM enrollments
WHERE enrollment_date >= DATE '2025-01-01'
ORDER BY enrollment_date DESC;

-- Stale-export check: last 365 days from CURRENT_DATE.
-- On 2026-09-18 this returns 0 rows because the seed stops at 2025-03-05.
SELECT id, student_name, course_title, enrollment_date
FROM enrollments
WHERE enrollment_date >= CURRENT_DATE - INTERVAL '1 year'
ORDER BY enrollment_date DESC;


-- ------------------------------------------------------------
-- Q6. Insert the enrollment confirmed by email but never stored
--     (values from the comment block at the end of edutrack.sql)
-- ------------------------------------------------------------
INSERT INTO enrollments (
    id,
    student_id,
    student_name,
    student_email,
    course_id,
    course_title,
    category,
    enrollment_date,
    completion_percentage,
    passed,
    monthly_fee_paid,
    instructor
) VALUES (
    18,
    3,
    'Lucia Fernandes',
    'lucia.fernandes@student.edutrack.com',
    5,
    'Advanced Python',
    'Programming',
    DATE '2025-04-01',
    0,
    FALSE,
    69.99,
    'Carlos Vega'
);

SELECT *
FROM enrollments
WHERE id = 18;


-- ------------------------------------------------------------
-- Q7. Assign placeholder instructor for NULL rows
-- ------------------------------------------------------------
SELECT id, student_name, course_title, instructor
FROM enrollments
WHERE instructor IS NULL;

UPDATE enrollments
SET instructor = 'Pending assignment'
WHERE instructor IS NULL;

SELECT id, student_name, course_title, instructor
FROM enrollments
WHERE instructor = 'Pending assignment';


-- ------------------------------------------------------------
-- Q8. Remove imported @test.com accounts
-- ------------------------------------------------------------
SELECT id, student_name, student_email, course_title
FROM enrollments
WHERE student_email LIKE '%@test.com';

DELETE FROM enrollments
WHERE student_email LIKE '%@test.com';

SELECT COUNT(*) AS enrollments_after_cleanup
FROM enrollments;


-- ------------------------------------------------------------
-- Q9. Enrollment count by category
-- ------------------------------------------------------------
SELECT category, COUNT(*) AS enrollments
FROM enrollments
GROUP BY category
ORDER BY enrollments DESC, category;


-- ------------------------------------------------------------
-- Q10. Average completion by course, lowest first
-- ------------------------------------------------------------
SELECT
    course_title,
    ROUND(AVG(completion_percentage), 2) AS avg_completion,
    COUNT(*) AS enrollments
FROM enrollments
GROUP BY course_title
ORDER BY avg_completion ASC, course_title;


-- ------------------------------------------------------------
-- Q11. Courses with more than 3 enrollments
-- ------------------------------------------------------------
SELECT course_title, COUNT(*) AS enrollments
FROM enrollments
GROUP BY course_title
HAVING COUNT(*) > 3
ORDER BY enrollments DESC, course_title;


-- ------------------------------------------------------------
-- Q12. Total monthly fees collected by category
-- ------------------------------------------------------------
SELECT
    category,
    ROUND(SUM(monthly_fee_paid), 2) AS total_revenue,
    COUNT(*) AS enrollments
FROM enrollments
GROUP BY category
ORDER BY total_revenue DESC, category;
