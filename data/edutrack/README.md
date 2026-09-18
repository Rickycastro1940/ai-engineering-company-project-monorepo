# EduTrack enrollments audit (Day 36)

Academy SQL audit of the denormalized `enrollments` table. `students` and `courses` are loaded for context only and are not modified.

## Files

- `edutrack.sql` — schema + seed (paste into the Supabase SQL Editor)
- `queries.sql` — all audit queries, in the order they must run
- `analysis_report.md` — findings from those queries

## Import (Supabase)

1. Create a project and open SQL Editor.
2. Run the full contents of `edutrack.sql`.
3. Verify: `SELECT * FROM enrollments LIMIT 5;`
4. Run `queries.sql` in order (SELECT before every UPDATE/DELETE).

## Local verification (this checkout)

PostgreSQL-compatible DuckDB replay of `edutrack.sql` + `queries.sql` (no live Supabase project from this environment):

```bash
python3 data/edutrack/run_audit.py
```
