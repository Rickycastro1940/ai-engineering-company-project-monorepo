# Brasaland Reporting API (`services/reporting/`)

HTTP shell for the weekly location cost & waste pipeline. **Not** `services/telemetry/` and **not** `GET /telemetry/report`.

| Role | Endpoint | Source |
| --- | --- | --- |
| Status | `GET /reporting/pipeline-runs/latest` | `get_latest_pipeline_run()` in `data/pipelines/pipeline.py` |
| Manual trigger | `POST /reporting/pipeline-runs` | Celery `run_weekly_pipeline` → Prefect `run_pipeline` (202 + `task_id`) |
| KPI query | `GET /reporting/weekly-location-performance` | `get_weekly_location_performance()` → `reporting.weekly_location_performance` |
| Task poll | `GET /tasks/{task_id}` | Celery result backend (companion to the trigger) |

Routes contain **no** ETL: no cost sums, event-type filters, location joins, or upserts.

## Run

```bash
# From monorepo root (Redis required for POST trigger)
uvicorn services.reporting.main:app --reload --port 8002
```

Examples:

```bash
curl -s http://127.0.0.1:8002/reporting/pipeline-runs/latest
curl -s 'http://127.0.0.1:8002/reporting/weekly-location-performance?week_start=2026-09-21'
curl -s -X POST http://127.0.0.1:8002/reporting/pipeline-runs \
  -H 'Content-Type: application/json' \
  -d '{"start_date":"2026-09-21","end_date":"2026-09-28"}'
```

Audience: Mariana Restrepo (Executive), Felipe Guerrero (Operations), Lucía Fernández (Procurement) — Part 3 dashboard consumes the KPI query.
