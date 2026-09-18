# EduTrack Data Audit — Analysis Report

Audit of the denormalized `enrollments` table (Day 36 seed in `edutrack.sql`). `students` (10 rows) and `courses` (7 rows) were loaded for context and were not modified.

Queries live in [`queries.sql`](queries.sql) and must run in order: 1–5 read the 17-row seed, 6–8 correct it, 9–12 report on the cleaned 16-row table.

This environment could not create a live Supabase project (no platform login). The same PostgreSQL-shaped SQL was replayed locally with DuckDB (`python3 data/edutrack/run_audit.py`). Import check: `SELECT * FROM enrollments LIMIT 5` returned five real enrollments (Emily Watson, Klaus Weber, Lucia Fernandes).

**Headline:** the extract arrived with **17 enrollments**. Two were `@test.com` accounts that should never be billed or reported. Two UI/UX rows had a NULL instructor. One confirmed Advanced Python enrollment for Lucia Fernandes was missing. After insert + instructor placeholder + test-account delete, the table holds **16 enrollments** and **$819.84** in recorded monthly fees. UI/UX Fundamentals is still at 0% completion for both remaining students.

---

## Q1 — Enrollments in Intro to Python

Result: **5** rows (seed, before cleanup).

| Student | Email | Completion |
| --- | --- | ---: |
| Klaus Weber | klaus.weber@student.edutrack.com | 92% |
| Marco Rossi | marco.rossi@student.edutrack.com | 88% |
| Emily Watson | emily.watson@student.edutrack.com | 85% |
| Priya Sharma | priya.sharma@student.edutrack.com | 55% |
| James Miller | james.miller@test.com | 30% |

Three students have already passed this course at 85%+. Priya is mid-progress and has not passed. James is a test account (removed in Q8); counting him in a live roster would inflate Intro to Python from 4 real enrollments to 5.

---

## Q2 — Completion below 10%

Result: **4** rows.

| ID | Student | Course | Completion |
| ---: | --- | --- | ---: |
| 11 | Pierre Dubois | UI/UX Fundamentals | 0% |
| 10 | Yuki Nakamura | UI/UX Fundamentals | 0% |
| 6 | Lucia Fernandes | Digital Marketing 101 | 3% |
| 5 | Lucia Fernandes | Web Design Basics | 5% |

Two patterns: **never started** (both UI/UX rows at 0%, same course that had no instructor) versus **stalled after a few percent** (Lucia on two different courses). Those are different interventions — assign an instructor / kickoff vs. a re-engagement email.

---

## Q3 — NULL instructor

Result: **2** rows. `IS NULL` is required; `instructor = NULL` would match nothing.

| ID | Student | Course | Enrolled |
| ---: | --- | --- | --- |
| 10 | Yuki Nakamura | UI/UX Fundamentals | 2024-10-11 |
| 11 | Pierre Dubois | UI/UX Fundamentals | 2024-11-05 |

Both sit on UI/UX Fundamentals. The `courses` catalog also lists that title with a NULL `instructor_name` (not changed here). The enrollment NULLs are consistent with an upstream course-level gap, not two independent typos.

---

## Q4 — Top 5 completion among students who have not passed

Result: **5** rows.

| ID | Student | Course | Completion |
| ---: | --- | --- | ---: |
| 2 | Emily Watson | Web Design Basics | 60% |
| 15 | Priya Sharma | Intro to Python | 55% |
| 9 | Yuki Nakamura | Data Analysis with SQL | 45% |
| 17 | Emily Watson | Advanced Python | 40% |
| 13 | James Miller | Intro to Python | 30% |

These are the closest-to-pass records in the seed. After Q8, James drops out of this list; the next real row would be Alex Chen at 10% (also a test account) or Pierre at 20% on Data Analysis with SQL.

---

## Q5 — Enrollments from 2025 onward

Calendar filter `enrollment_date >= DATE '2025-01-01'`: **3** rows.

| ID | Student | Course | Date | Completion |
| ---: | --- | --- | --- | ---: |
| 17 | Emily Watson | Advanced Python | 2025-03-05 | 40% |
| 16 | Pierre Dubois | Data Analysis with SQL | 2025-02-20 | 20% |
| 15 | Priya Sharma | Intro to Python | 2025-01-10 | 55% |

Rolling window `enrollment_date >= CURRENT_DATE - INTERVAL '1 year'` on **2026-09-18**: **0** rows. The newest seed date is **2025-03-05**, more than a year before this audit. Treat the extract as stale for any “last 12 months” Q3/Q4 board number until a fresh dump is confirmed.

Q6 later inserts Lucia Fernandes / Advanced Python on **2025-04-01**, which is also older than one year from this audit date.

---

## Q6 — Missing enrollment inserted

`SELECT` after `INSERT` for `id = 18`: **1** row.

| Field | Value |
| --- | --- |
| student | Lucia Fernandes (`student_id` 3) |
| course | Advanced Python (`course_id` 5, Programming) |
| enrollment_date | 2025-04-01 |
| completion | 0% |
| passed | false |
| monthly_fee_paid | 69.99 |
| instructor | Carlos Vega |

Table size: 17 → **18** before the test-account delete. Values taken from the comment block at the end of `edutrack.sql` (email-confirmed, never stored).

---

## Q7 — Missing instructors updated

Matching `SELECT` first: ids **10** and **11** (same two rows as Q3).

`UPDATE ... WHERE instructor IS NULL` affected **2** rows. Follow-up `SELECT` where `instructor = 'Pending assignment'`:

- Yuki Nakamura — UI/UX Fundamentals
- Pierre Dubois — UI/UX Fundamentals

This is a data-quality placeholder, not a real instructor assignment. Completions remain 0%. Someone still has to staff the course.

---

## Q8 — Test accounts deleted

Matching `SELECT` first (`student_email LIKE '%@test.com'`): **2** rows.

| ID | Student | Email | Course |
| ---: | --- | --- | --- |
| 13 | James Miller | james.miller@test.com | Intro to Python |
| 14 | Alex Chen | alex.chen@test.com | Web Design Basics |

`DELETE` used the **same WHERE clause**. After cleanup: **16** enrollments. `students` still contains the two test people (10 rows) because that table was out of scope.

---

## Q9 — Enrollments by category (cleaned table)

| Category | Enrollments |
| --- | ---: |
| Programming | 7 |
| Design | 4 |
| Data | 3 |
| Marketing | 2 |

Programming is the load-bearing category. Marketing is a thin sample (two rows, both Digital Marketing 101). Email Campaigns exists on `courses` with **zero** enrollments.

---

## Q10 — Average completion by course (cleaned table)

| Course | Avg completion | Enrollments |
| --- | ---: | ---: |
| UI/UX Fundamentals | 0.00 | 2 |
| Web Design Basics | 32.50 | 2 |
| Digital Marketing 101 | 36.50 | 2 |
| Advanced Python | 45.00 | 3 |
| Data Analysis with SQL | 47.67 | 3 |
| Intro to Python | 80.00 | 4 |

Intro to Python is healthy once James is removed (80% average, 4 real students). UI/UX is a complete stall. Advanced Python’s average is pulled down by Emily at 40% and the new Lucia row at 0%.

---

## Q11 — Courses with more than 3 enrollments

Result: **1** course.

- Intro to Python — **4** enrollments

No other course clears the `HAVING COUNT(*) > 3` bar on the cleaned table. Design and Data volume is too small to treat averages as stable KPIs.

---

## Q12 — Revenue by category (sum of `monthly_fee_paid`)

| Category | Total | Enrollments |
| --- | ---: | ---: |
| Programming | 409.93 | 7 |
| Data | 179.97 | 3 |
| Design | 169.96 | 4 |
| Marketing | 59.98 | 2 |

**Grand total: $819.84.** Programming is about half of recorded fees. These figures are monthly-fee snapshots on the enrollment row, not recognized revenue over time.

---

## Integrity notes (enrollments only)

- `students` / `courses` were not updated or deleted.
- Post-audit counts: enrollments **16**, students **10**, courses **7**, NULL instructors **0**, `@test.com` enrollments **0**.
- Denormalized names, titles, and fees can drift from `students`/`courses` on a later related-tables audit; this pass did not JOIN.

## Recommended follow-ups

1. Staff UI/UX Fundamentals (replace `Pending assignment`) and check why both students are still at 0%.
2. Exclude `@test.com` at import time so they never hit reporting.
3. Refresh the extract; a “last year” filter against today is empty.
4. Reach Lucia Fernandes (two stalled courses plus a new Advanced Python row at 0%).
5. Next schema pass: JOINs and foreign keys so enrollment instructor/title cannot disagree with `courses`.
