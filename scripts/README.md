# `scripts` folder

This folder contains **helper scripts** for the monorepo: development automation, maintenance utilities, repetitive tasks (setup, lint, migrations, data generation, etc.), and internal tooling.

- **Main purpose**: group support tools that do not belong to a specific app, agent, or pipeline but make the team’s work easier.
- **Recommendation**: document each script (what it does, parameters, requirements, usage examples) and keep them reproducible (and safe) across environments.

## `seed_incidents.py`

Loads `scripts/incidents-brasaland.csv` into the incident manager (`data/company_api.db` unless `--database` is set). Invalid analyzer rows are printed and skipped. A second run does not insert duplicates.

```bash
python scripts/seed_incidents.py
python scripts/seed_incidents.py scripts/incidents-brasaland.csv --database /tmp/incidents.db
```

## `nightly_export.py`

Copies one UTC calendar day of operational rows from `public.telemetry_events` (`timestamp`) into `data/raw/telemetry_YYYY-MM-DD.csv` only when that file is not already there. The CSV is a backup snapshot. The Milestone 6 pipeline (`data/pipelines/pipeline.py`) reads the database, not the file. The script then records final status, `target_date`, timestamps, and any error on `public.job_runs`.

`target_date` is the first CLI argument, otherwise `TARGET_DATE`, otherwise yesterday in UTC.

```bash
# Yesterday in UTC (what cron runs)
python scripts/nightly_export.py

# One calendar day from the environment
TARGET_DATE=2026-10-12 python scripts/nightly_export.py

# One calendar day, backfill
python scripts/nightly_export.py 2026-10-12
```

Needs `SUPABASE_URL` and `SUPABASE_KEY` (service role; RLS is on and there is no anon policy). A second run for the same date exits 0 when that date is already `completed`, or when a `processing` lock is held.

Cron expression: `0 2 * * *` with `CRON_TZ=America/Bogota`. Install: `bash infra/cron/install-nightly-export-cron.sh`. The FastAPI process does not schedule this script.

> _Spanish version: [README.es.md](./README.es.md)._
