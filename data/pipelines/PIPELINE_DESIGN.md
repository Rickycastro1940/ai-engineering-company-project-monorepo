# Business Performance Data Pipeline Design
**Company:** Brasaland
**Target Audience:** Mariana (CEO) and Felipe (Operations Director)

## Phase 1 — Current State Analysis

### 1. Current State
Currently, our system captures technical telemetry events (such as `page_view`, `user_login_succeeded`, `user_login_failed`, and `api_error`) and stores them in the `telemetry_events` table in our Supabase database. 

We have an existing engineering dashboard powered by the `GET /telemetry/report` endpoint and the `services/telemetry/analysis.py` pipeline. This pipeline answers technical and operational questions for the engineering team:
* Total daily traffic volume to monitor system load.
* Technical error distribution to pinpoint instability.
* Authentication failure rates for operational security.

### 2. The Gap
**Unanswered Business Question:** How efficiently is each Brasaland location managing its inventory costs and waste?

While our current technical report tells us if the platform is crashing, it provides zero visibility into business margins. Mariana (CEO) and Felipe (Operations Director) need a **"Weekly Location Cost & Waste Report"** to compare the 14 locations based on purchase costs, waste costs, waste ratios, stockout frequencies, and price alert frequencies. 

A dedicated business pipeline is required because these metrics require joining operational events with domain data (locations, ingredient costs) and aggregating them on a weekly business cadence, which should not pollute the fast, real-time technical engineering endpoint.

## Phase 2 — Pipeline Design

### 1. Purpose
The purpose of this pipeline is to produce the **"Weekly Location Cost & Waste Report"** for the CEO and Operations Director by computing Purchase Cost, Waste Cost, Waste Ratio, Stockout Frequency, and Price Alert Frequency from raw operational telemetry events (e.g., `ingredient_purchased`, `waste_logged`, `stockout_alert`).

### 2. Extraction Format
Data will be extracted from the `telemetry_events` table. The events arrive continuously in real-time as JSON payloads. The extraction phase will query these events in weekly batches (filtering by the relevant event types and the specific date window) and join them with static domain tables (`locations`, `ingredients`) to attach costs and location names.

### 3. Data Flow Diagram
```mermaid
graph TD
    A[(telemetry_events table)] -->|Extract Weekly Events| C(Transformation Layer)
    B[(domain tables: locations)] -->|Extract Dimensions| C
    C -->|Parse JSON & Aggregate KPIs| D(Load Layer)
    D -->|Upsert Aggregates| E[(reporting.weekly_location_metrics)]
    ## Phase 3 — Resilience and Idempotency

### 1. Idempotency Strategy
If the pipeline fails midway through the load phase (e.g., a database connection drop) and is re-run, we guarantee data integrity by using an **Upsert (INSERT ... ON CONFLICT)** strategy based on the composite primary key `(location_id, reporting_week_start)`. 

Because our transformation stage recalculates the entire week's aggregations from the raw `telemetry_events` table every time it runs, a second run will simply overwrite any partially loaded data from the failed run with the exact same, correct weekly totals. It will never add to existing totals (no double-counting) or create duplicate rows.

### 2. Execution Log (`job_runs`) — verified in Supabase
Live table `public.job_runs` (project `tlfllnfwynaykxglsqhc`) enforces:

`pending` → `processing` → `completed`  
`pending` → `failed`  
`processing` → `failed`

via check constraint `job_runs_status_check`.

Fields (live schema):
1. **`id` (integer identity):** Uniquely identifies the execution attempt.
2. **`job_name` (varchar):** Pipeline / job identifier.
3. **`target_date` (date):** Business date this job is responsible for.
4. **`status`:** `pending` | `processing` | `completed` | `failed`.
5. **`started_at` / `finished_at` / `created_at`:** Lifecycle timestamps.
6. **`error_message` (text):** Failure reason when status is `failed`.

App code: `job_runs.py`. SQL mirror: `job_runs.sql`.

### 3. Distributed lock = `processing` (no separate lock)
Only one row may be `processing` for a given `(job_name, target_date)`. That row **is** the distributed lock — there is no Redis/advisory-lock/mutex table.

- Enforced in app via `claim_processing()` / `ProcessingLockHeld`
- Enforced in Postgres via unique partial index `job_runs_one_processing_per_target`
- Demo: `python3 scripts/demo_processing_lock.py` (launches two instances at once)
- Manual: run `scripts/run_pipeline_job.py` in two terminals with the same `--target-date`

### 4. Idempotency per `target_date`
If a `completed` job already exists for `(job_name, target_date)`, `execute_with_job_tracking()` returns that job and **skips** `execute_fn` — no second pipeline run and no duplicated dated CSV/artifacts.

Failed runs are still retriable (only `completed` short-circuits).

### 5. No stuck `processing` after failure
`execute_with_job_tracking()` uses `try` / `except` / `finally`. The `finally` block calls `_fail_if_still_processing()` so any claimed job still in `processing` is transitioned to `failed` — including `KeyboardInterrupt` / other `BaseException` paths that `except Exception` would miss.

### 6. Lifecycle logging
Every relevant job event is logged via `log_job_event()` with **timestamp**, **job_name**, and **status** (plus event / target_date / job_id):

- `idempotent_skip` — completed job already exists  
- `processing` — lock acquired  
- `lock_held` — another instance holds processing  
- `completed` — success  
- `failed` — failure path / `finally` cleanup  

Logger name: `data.pipelines.job_runs`.

### 7. `job_runs` vs `pipeline_runs` (no duplicated responsibilities)
| Layer | Role |
| --- | --- |
| **`job_runs`** | Sole system of record: status, lock, idempotency, history (table + `job_runs.py`) |
| **`/reporting/pipeline-runs*`** | Thin HTTP alias for the Brasaland weekly pipeline only — reads/writes **through** `job_runs` filtered by `job_name` |
| **`last_run.json`** | **Removed** as a source of truth (do not use for latest-run APIs) |

There is no separate `pipeline_runs` table. Pipeline trigger/list/latest endpoints set `"source": "job_runs"` in responses so ownership stays explicit.

## Phase 4 — Mapping to Prefect

### 1. Prefect Concepts Mapping
*   **Flow:** The main orchestrator is a Prefect Flow named `brasaland_weekly_performance_pipeline` (plus scheduled wrapper `brasaland_weekly_scheduled_pipeline`). It dictates the order of execution and handles overall success/failure.
*   **Tasks:** The granular, retryable steps inside the flow:
    1.  `extract_telemetry_events` (Pulls raw data for the week)
    2.  `extract_domain_data` (Pulls the 14 Brasaland locations and ingredient costs)
    3.  `aggregate_location_kpis` (Pandas transformation for cost and waste)
    4.  `upsert_to_reporting_table` (Loads the data safely into Supabase)
*   **States:** 
    *   *Scheduled:* Waiting for the Monday cron (see below).
    *   *Running:* Currently calculating metrics (`job_runs.status = processing`).
    *   *Completed:* Successfully upserted to `weekly_location_performance` (`job_runs.status = completed`).
    *   *Failed:* E.g., Database timeout (`job_runs.status = failed`), which triggers our idempotency recovery strategy.

### 2. Configured schedule (cron)

**Cron expression:** `0 9 * * 1`  
**Timezone:** `UTC`  
**Meaning:** Every Monday at 09:00 UTC (“Monday morning”).

| Layer | Where configured |
| --- | --- |
| Source of truth | `data/pipelines/schedule.py` → `CRON_EXPRESSION = "0 9 * * 1"` |
| GitHub Actions trigger | `.github/workflows/brasaland-weekly-pipeline.yml` → `on.schedule.cron: "0 9 * * 1"` |
| Prefect serve | `scripts/serve_pipeline_schedule.py` → `.serve(cron=CRON_EXPRESSION)` |
| CLI entrypoint | `scripts/run_scheduled_pipeline.py` (resolves previous ISO week, then runs ETL) |

Scheduled runs aggregate the **previous closed ISO week** (Monday–Sunday): `previous_week_window()` sets `start_date` / `target_date` to that week’s Monday and `end_date` to the following Monday (exclusive).

Manual overrides remain available via `POST /reporting/pipeline-runs` and Actions `workflow_dispatch`.

### 3. Prefect Blocks
To keep secrets out of our code, we will use a **Prefect Secret Block** or **Credentials Block** to securely store the Supabase connection string and API keys. This ensures the pipeline can connect to the database securely without hardcoding credentials in `data/pipelines/`.

---

## Phase 5 — Application Integration

### 1. New Reporting Endpoints
These endpoints will live in a completely separate module (`services/reporting/main.py`) to isolate them from the engineering telemetry:

*   **`GET /reporting/brasaland-weekly`**
    *   *Purpose:* The endpoint the front-end dashboard calls to display the metrics for Mariana and Felipe. It strictly queries the `reporting.weekly_location_metrics` table.
*   **`POST /reporting/brasaland-weekly/trigger`**
    *   *Purpose:* A manual override endpoint to force the pipeline to re-run for a specific week if delayed events arrive or an audit is requested.

### 2. Pipeline Invocation
The `POST /reporting/brasaland-weekly/trigger` endpoint will *not* contain any ETL logic. Instead, it will directly import and call the `brasaland_weekly_cost_waste_flow()` located in `data/pipelines/`, passing the requested `window_start` and `window_end` dates as parameters.