# `scripts` folder

This folder contains **helper scripts** for the monorepo: development automation, maintenance utilities, repetitive tasks (setup, lint, migrations, data generation, etc.), and internal tooling.

- **Main purpose**: group support tools that do not belong to a specific app, agent, or pipeline but make the team’s work easier.
- **Recommendation**: document each script (what it does, parameters, requirements, usage examples) and keep them reproducible (and safe) across environments.

## `nightly_export.py`

Copies one America/Bogota calendar day of operational rows from `public.telemetry_events` (`timestamp`, not `created_at`) into `data/raw/telemetry_YYYY-MM-DD.csv`, then runs `data/pipelines/pipeline.py`. Status is `public.job_runs` via `services/job_runner.py`.

```bash
# Yesterday in America/Bogota (what cron runs)
python scripts/nightly_export.py

# One calendar day, backfill
python scripts/nightly_export.py 2026-10-12
```

Needs `SUPABASE_URL` and `SUPABASE_KEY` (service role; RLS is on and there is no anon policy). A second run for the same date exits 0 when that date is already `completed`, or when a `processing` lock is held.

Cron expression: `0 2 * * *` with `CRON_TZ=America/Bogota`. Install: `bash infra/cron/install-nightly-export-cron.sh`. The FastAPI process does not schedule this script.

> _Spanish version: [README.es.md](./README.es.md)._
