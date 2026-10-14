-- Job control for Brasaland background work (nightly telemetry export).
-- Lives in public next to telemetry_events so PostgREST `.table("job_runs")`
-- matches services/job_runner.py. Not mounted on the FastAPI process.
--
-- Naming follows the telemetry tables already in this project:
--   public.telemetry_events        id, timestamp, event_type, tags, service, level
--   public.telemetry_events_legacy id, created_at, timestamp, event_type, tags
--   public.locations               id, country, currency
-- Snake_case columns. Status is a closed set. Time bounds are timestamptz.
-- The nightly script filters telemetry_events on "timestamp" (not created_at).
--
-- Idempotency: at most one processing row per (job_name, target_date).
-- Service role bypasses RLS. No anon/authenticated policy: job status is not public.

create table if not exists public.job_runs (
    id serial primary key,
    job_name varchar(64) not null,
    target_date date not null,
    status varchar(16) not null
        check (status in ('pending', 'processing', 'completed', 'failed')),
    started_at timestamptz,
    finished_at timestamptz,
    error_message text,
    created_at timestamptz not null default now()
);

create index if not exists idx_job_runs_name_status
    on public.job_runs (job_name, status);

create index if not exists idx_job_runs_name_date
    on public.job_runs (job_name, target_date);

create unique index if not exists job_runs_one_processing_per_target
    on public.job_runs (job_name, target_date)
    where status = 'processing';

alter table public.job_runs enable row level security;
