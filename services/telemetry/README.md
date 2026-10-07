# Engineering telemetry technical report

Department: **Technology** (Nicolás Park).

`GET /telemetry/report` answers three engineering questions from Supabase
`telemetry_events` — not business KPIs (sales, conversion, revenue). Those stay
in the Data Pipelines milestone (`services/reporting/`).

| Metric (pandas function) | Dimension | Formula / captured inputs |
| --- | --- | --- |
| `get_events_per_day` | Volume | `COUNT(id)` per UTC date (all events) |
| `get_error_count_by_type` | Errors | Count of `api_error`, `client_exception_caught`, `user_login_failed`, … |
| `get_api_latency_per_day` | Latency | `count` / `mean` / `sum` of `api_latency_recorded.value` (ms) |
| `get_auth_failure_rate` | Availability | `user_login_failed / (failed + succeeded)` per UTC day (4 dp) |

Functions are independent, side-effect free, and use only pandas
(`.groupby()`, `.agg()`, `count`, `sum`, `mean`) — no row loops.

The report handler resolves `start_date` / `end_date` once, then passes
that same window into every metric function. Metrics never invent their
own default time window.

## Order of implementation

1. Analysis — `analysis.py` (phase one pandas metrics above)
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
