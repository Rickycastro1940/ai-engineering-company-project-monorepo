# Engineering telemetry technical report

Department: **Technology** (Nicolás Park).

`GET /telemetry/report` answers three engineering questions from Supabase
`telemetry_events` — not business KPIs (sales, conversion, revenue). Those stay
in the Data Pipelines milestone (`services/reporting/`).

| Metric | Formula |
| --- | --- |
| `events_per_day` | Count of rows per UTC date |
| `error_rate_by_type` | Count of `api_error` and `user_login_failed` by `event_type` |
| `auth_failure_rate` | `user_login_failed / (failed + succeeded)` per UTC day (4 dp) |

## Order of implementation

1. Analysis — `analysis.py` (`get_events_per_day`, `get_error_rate_by_type`, `get_auth_failure_rate`)
2. Report endpoint — `main.py` (`GET /telemetry/report`)
3. Cache — in-memory map, 60s TTL per `(start_date, end_date)`

Event catalogue: [`docs/telemetry/telemetry-plan.md`](../../docs/telemetry/telemetry-plan.md).  
UI: [`uis/backoffice/legacy/telemetry.html`](../../uis/backoffice/legacy/telemetry.html).

## Run

```bash
export SUPABASE_URL=...
export SUPABASE_KEY=...
uvicorn api.app:app --reload --port 8000
curl -s "http://127.0.0.1:8000/telemetry/report" | python3 -m json.tool
```

Default window: last 7 days UTC when query params are omitted.
