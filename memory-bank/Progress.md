# Progress — Brasaland Digital

Verified **2026-09-16** on clone `Rickycastro1940/ai-engineering-company-project-monorepo`, branch `feature/auth-frontend`. Gaps below are scored against root [`CONTEXT.md`](../CONTEXT.md) department needs.

## Agent infrastructure (aligned to `CONTEXT.md`)

- Root `CONTEXT.md` / `CONTEXT.es.md` replaced with official Brasaland briefings (`00-general-contexts/CONTEXT-brasaland-briefing.*.md`). Placeholder four-company list removed.
- `memory-bank/` (`Projectbrief.md`, `Techcontext.md`, this file) cites `CONTEXT.md` departments, currencies, and Technology/Executive needs.
- `AGENTS.md` + `.agents/rules/00-operating-loop.md` (**always active**) enforce Brasaland-only facts from `CONTEXT.md`.
- Skill `.agents/skills/verify-brasaland-api/` checks the running API against Technology’s central-API list in `CONTEXT.md` (locations, menus, sales, customers, suppliers) plus the inventory slice used for Operations stock.

## Coverage vs `CONTEXT.md` (this checkout)

| `CONTEXT.md` need | Status in monorepo |
| --- | --- |
| Technology: central API (locations, menus, sales, customers, suppliers) | **Present (seeded)** — `locations`/`menus`/`sales`/`customers`/`suppliers`/`inventory=present` plus `knowledge=present` (`POST /knowledge/query`) and `realtime=present` (`GET /realtime/ops-alerts/stream`) on `uvicorn api.app:app` (`:8000`). Not a live POS or invoice feed |
| Technology: telemetry + pipeline to dashboards | **Partial** — design contract in `docs/telemetry/` (41 events: 18 mandatory + 23 identified opportunities; draft-07 schemas; property allowlists; envelope). Live no-sales SSE on `GET /realtime/ops-alerts/stream` plus Part 2 weekly location cost/waste ETL, Prefect stage subflows, KPI unit tests, CLI, and backoffice Monday weekly report. Catalog emitters are not wired. Engineering `GET /telemetry/report` untouched |
| Operations: sales per location COP/USD; no-sales alerts; smart ordering | **Partial** — seeded `GET /sales` tickets and `/sales/overview` (COP and USD, 14 locations) plus `/sales/alerts`; `POST /sales` stores a ticket and calls `record_sale` so the live no-sales alert on backoffice `/accessible` sees that location; Next.js `uis/portal` `/ops/sales` shows per-location sales in COP and USD. Smart ordering still open |
| Procurement: supplier price history, consolidated spend | **Partial** — seeded `GET /suppliers` (20 suppliers, Colombia and Florida, price history and alerts); Monday weekly purchase cost / price-alert frequency still separate; invoices are not live |
| Marketing: digital Brasa Points, CRM, personalisation | **Partial** — `GET /customers` CRM seed with `brasa_points_balance` on physical stamp cards; Next.js `uis/portal` `/points` looks up a guest and shows Brasa Points balance, history, and tier rewards (fixtures, or `GET /customers` when `BRASALAND_DATA_SOURCE=live`); `uis/website/` corporate home (`/`) live. `CONTEXT.md` still describes stamp cards as today’s in-restaurant programme |
| People: HR portal / KPIs by country | **Not done** |
| Training: recipe catalogue, push to 14 locations | **Partial** — `POST /knowledge/query` searches the four English standards (allergens, waste, ordering, Brasa Points) and returns cited chunks. Not a full recipe catalogue and not a push to all 14 kitchens |
| Executive: sales USD+COP dashboard, NL assistant, Monday 07:00 report | **Partial** — seeded `GET /sales/overview` and portal `/ops/sales` chain totals in COP and USD; Monday weekly ops & finance report in the backoffice; n8n export `workflows/brasaland-monday-leadership-report.n8n.json` schedules Monday 07:00 America/Bogota, logs into the central API, pulls `GET /reporting/weekly-location-performance`, and delivers COP/USD leadership copy (email, Slack, CSV) with a failure branch. Standards questions can go to `POST /knowledge/query`. A sales NL assistant and a chain sales dashboard remain open |

## What already runs (engineering)

| Area | Evidence |
| --- | --- |
| Inventory API + Groq agent | `services/api/inventory.py` (CSV-backed flat imports; no package-relative `.auth`), `agent.py` |
| Incident analysis UI | `uis/web` |
| Weekly cost/waste pipeline + Celery | `data/process/location_kpis.py`, `data/pipelines/pipeline.py`, `services/reporting/main.py`, `services/tasks.py`; Compose Redis/Flower/worker |
| Public corporate website | `uis/website/` — Vite/React, route `/`, brand tokens + components from `CONTEXT.md`; screenshot `docs/screenshots/website-corporate-home.png` |
| Internal backoffice | `uis/backoffice/` — JWT session; client layout guard (`ProtectedRoute` + `useRequireAuth`) on `/`, `/accessible`, `/account/profile`, `/account/change-password`, and `/reporting/weekly-performance`; `/accessible` locations+inventory and live no-sales; Monday weekly ops & finance report (COP/USD) |
| Telemetry design contract | `docs/telemetry/telemetry-plan.md`, `event-schemas.json`, `property-allowlists.md` — catalog and schemas only; emitters not wired |
| Locations API | `services/api/locations.py` — 14 locations, Colombia 8 / Florida 6, COP+USD; **Bearer JWT required** |

## Latest auth-frontend evidence (`feature/auth-frontend`)

Department served: **Technology** (JSON auth API restored onto the central FastAPI app) + **Operations/Executive** (staff backoffice is now session-gated).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
GET /locations/overview without token → 401
POST /auth/login → 200 + user + access_token
GET /locations/overview with Bearer → 200, 14 locations, COP+USD
GET /inventory with Bearer → 200
pytest tests/test_users_api.py → 17 passed
cd uis/backoffice && npm run build → green
GET /auth/me with Bearer → email + name/phone/address
PUT /profiles/me anonymous → 401; with Bearer → 200 contact fields
Browser /account/profile → GET /auth/me email + contact; save → PUT /profiles/me 200 “Profile updated.”
/account/change-password still renders after profile save
Client guard: no token → /login?next= for /, /accessible, /account/profile, /account/change-password
Login stores auth_token in localStorage; /accessible loads locations+inventory with Bearer
Logout removes auth_token and lands on /login
Protected 401 → clearSessionAndRedirectToLogin()
uis/website `/` (5173) loads corporate home with no login redirect
GET /auth/me with invalid Bearer → 401
E2E eval: register → token stored → /accessible; /account/profile email+name; PUT /profiles/me 200; logout /login no token; invalid JWT → GET /auth/me 401 → /login no token
Website `/` no auth_token, no login links
React 19.3.0 + react-dom in uis/backoffice and uis/website; vite-plugin-react; npm run build bundles createRoot/useState
Live #root has __reactContainer$ on :5174/login and :5173/

```

JWT login/register for the staff console is **present**. Technology’s menus/sales/customers/suppliers nouns remain **missing**.

## Latest verify-brasaland-api evidence (`feature/agent-memory-bank`)

Department served: **Technology** (central API coverage) + **Marketing** (corporate site) + **Operations/Executive** (backoffice location footprint).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
GET http://127.0.0.1:8001/docs → 200
locations=present
menus=missing
sales=missing
customers=missing
suppliers=missing
inventory=present
path_count=14
GET /locations/overview → 14 locations (company Brasaland)
GET /inventory → 200
```

Skill **passed** (criteria 1–4 + 6). Technology central API is **not complete** while menus/sales/customers/suppliers remain `missing`.

## Latest error-handling audit (`feature/error-handling-audit`)

Department served: **Technology** (central API must fail safely) + **Operations/Executive** (staff see errors, not a blank console).

```text
pytest tests/test_error_handling.py tests/test_users_api.py -q → 19 passed
cd uis/backoffice && npm run build → green
cd uis/website && npm run build → green
Checklist: docs/error-handling-audit.md
```

## Latest three-state fetch UI (`feature/error-handling-audit`)

Department served: **Operations/Executive** (staff console must not go blank while locations/inventory load) + **Technology** (session and API failures need a retry path).

```text
cd uis/backoffice && npm run build → tsc -b && vite build green
Browser :5174/login invalid credentials → alert + Sign in retry CTA; button showed Signing in…
Register Creating account… then /accessible with 14 locations (COP+USD roster)
/account/profile → email async-ui-0918@brasaland.test + Save profile form
uis/website has no fetch (static corporate home)
```

## Latest user-facing error copy (`feature/error-handling-audit`)

Department served: **Operations/Executive** (staff see plain-language failures with retry/home/support) + **Technology** (API errors are mapped, not dumped).

```text
cd uis/backoffice && npm run build → tsc -b && vite build green
```

## Latest FastAPI exception scope (`feature/error-handling-audit`)

Department served: **Technology** (central API handlers catch I/O at the call site; programming errors still hit the generic 500 handler).

```text
uv run python -m pytest tests/test_error_handling.py tests/test_users_api.py -q → 24 passed
```

## Latest structured HTTP errors (`feature/error-handling-audit`)

Department served: **Technology** (central API returns 400/404/422/500 as JSON, never Python tracebacks).

```text
uv run python -m pytest tests/test_error_handling.py tests/test_users_api.py -q → 24 passed
Envelope: status, code, message, detail (422 detail remains field loc/msg/type)
GET /inventory RuntimeError → 500 {"code":"internal_error","message":"Internal server error"} no traceback
```

## Latest secret-safe errors + external calls (`feature/error-handling-audit`)

Department served: **Technology** (client JSON must not leak connection strings, keys, or host paths; LLM/Qdrant/Supabase calls must fail closed).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
GET http://127.0.0.1:8000/docs → 200
locations=present
menus=missing
sales=missing
customers=missing
suppliers=missing
inventory=present
path_count=21
uv run python -m pytest tests/test_error_handling.py tests/test_users_api.py -q → 27 passed
error_body(500, postgres://… / sk- / /Users/) → generic Internal server error
ExternalServiceError("language model") on GET /inventory → 503 language model is unavailable
```

Skill **passed** (criteria 1–4 + 6). Technology central API remains **incomplete** while menus/sales/customers/suppliers are `missing`.

## Latest script file/CSV error handling (`feature/error-handling-audit`)

Department served: **Technology** (CLI tools must fail closed) + **Operations** (incident CSV analysis for kitchens/locations).

```text
uv run python -m pytest tests/test_scripts_io.py tests/test_error_handling.py -q → 16 passed
uv run python scripts/analyze.py scripts/does-not-exist.csv → STDERR + exit 1
```

## Latest log redaction (`feature/error-handling-audit`)

Department served: **Technology** (no stack traces or host paths in operator consoles) + **Marketing** (public site ErrorBoundary).

```text
uv run python -m pytest tests/test_error_handling.py tests/test_scripts_io.py -q → 16 passed
cd uis/backoffice && npm run build → green
cd uis/website && npm run build → green
ErrorBoundary console.error no longer includes error or componentStack
```

## Latest finally / client-safe / script I/O closeout (`feature/error-handling-audit`)

Department served: **Technology** (structured HTTP, no env names in 503s) + **Operations/Executive** (loading flags always clear; login session failure has retry).

```text
uv run python -m pytest tests/test_error_handling.py tests/test_scripts_io.py tests/test_users_api.py -q → 33 passed
cd uis/backoffice && npm run build → green
```

## Latest instrumentability evaluation (`cursor/telemetry-plan-ff8d`)

Department served: **Technology**. Audit of stream/batch urgency, PII handling, risks/exclusions, and whether another developer can instrument without clarification. **Verdict: PASS.**

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
delivery rows = 41; technical-preference justifications = none
sensitive/pseudonymous/sanitized property rows = 30
discarded candidates with reasoned why = 9
privacy + cost exclusions + delivery risk mitigations = present
checklist >= 12, IP-1..IP-8, instrumentation map, emit algorithm = present
```

Emitters are still not wired. Menus, sales, customers, and suppliers remain missing on the central API.

## Latest event quality evaluation (`cursor/telemetry-plan-ff8d`)

Department served: **Technology**. Audit of justification, envelope, allowlists, and schema–plan consistency. **Verdict: PASS.**

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
Draft7Validator.check_schema → pass
41/41 capture sentences (hypothesis + decision); no just-in-case events
envelope requires eventID, timestamp (ISO 8601 Z), sessionID, UserID, Event_type, SchemaVersion, requestID, properties (+ source, tags)
entity_action taxonomy: all Event_type values pass
41 examples validate with full envelope
41 property allowlists; 0 key mismatches vs schema; additionalProperties false
plan catalog == schema oneOf == 41
```

Emitters are still not wired. Menus, sales, customers, and suppliers remain missing on the central API.

## Latest CONTEXT coverage evaluation (`cursor/telemetry-plan-ff8d`)

Department served: **Technology** (audit of the telemetry contract against every `CONTEXT.md` department need). Verdict: **PASS**. All 34 mandatory metric ids in the plan match `weekly_report_dispatched.floor_metric_ids`. Business and technical opportunity coverage includes authentication, performance, errors, navigation, and inventory/marketing/HR exploration (`bo.*` off the floor).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
CONTEXT need phrases present = 22 / 22
mandatory metrics in plan = 34 = floor_metric_ids
evaluation Yes rows = 23 department-need mappings
opportunity metrics = 34; bo.* questions = 11; events = 41
auth/perf/errors/nav/business event gaps = none
null-pending floor ids retained (holiday, onboarding, catalogue search, training path)
ops.stockout.count remains opportunity (not floor)
```

Emitters are still not wired. Menus, sales, customers, and suppliers remain missing on the central API.

## Latest delivery strategy Phase 3 (`cursor/telemetry-plan-ff8d`)

Department served: **Technology** (with Operations/Procurement urgency for stream paths). Every catalog event is classified stream or batch from the urgency of the decision it feeds. Throttle/debounce covers silence episodes, protein-cover alerts, latency sampling, and navigation chatter. Risks and exclusions list discarded events plus privacy/cost data that will not be captured.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
mandatory events classified = 18
opportunity events classified = 23
stream examples: sale_completed, location_sales_silence_detected, stock_threshold_triggered, api_error_raised
batch examples: weekly_report_dispatched, employee_hired, stock_waste_registered, api_latency_recorded
throttle rows documented = 12
discarded + privacy/cost exclusions section present in telemetry-plan.md
```

Emitters are still not wired. Menus, sales, customers, and suppliers remain missing on the central API.

## Latest draft-07 schema export (`cursor/telemetry-plan-ff8d`)

Department served: **Technology**. `docs/telemetry/event-schemas.json` is exported as JSON Schema draft-07 (`$schema` `http://json-schema.org/draft-07/schema#`) with a root `oneOf` and `definitions` (not `$defs`), validatable with `Draft7Validator`.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
$schema = http://json-schema.org/draft-07/schema#
Draft7Validator.check_schema → pass
41 event examples validate
mandatoryMetricSet example validates
definitions present; $defs absent
sale_completed + email → reject
missing requestID → reject
```

Emitters are still not wired. Menus, sales, customers, and suppliers remain missing on the central API.

## Latest property allowlists (`cursor/telemetry-plan-ff8d`)

Department served: **Technology**. Every catalog event has an explicit `properties` allowlist (name, type, required/optional, description, Sensitive/PII handling). Schemas keep `additionalProperties: false` so keys outside the list are rejected before storage.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
property-allowlists.md / .json cover all 41 Event_type values
sale_completed + email → schema reject
sale_completed.lines + customer_email → schema reject
user_login_failed + password → schema reject
client_exception_caught + stack → schema reject
api_error_raised + token → schema reject
```

Emitters are still not wired. Menus, sales, customers, and suppliers remain missing on the central API.

## Latest event taxonomy and complete schemas (`cursor/telemetry-plan-ff8d`)

Department served: **Technology**. Every `Event_type` follows `entity_action` with a closed verb list. `definitions.mandatoryMetricSet` is the complete observation schema for all 34 `CONTEXT.md` mandatory metrics. Opportunity schemas cover business/inventory, authentication, performance, errors, and navigation (examples: `direct_stock_edit_rejected`, `session_expired`, `api_latency_recorded`).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
Draft202012Validator.check_schema → pass
41 event examples validate
mandatoryMetricSet example = 34 observations
entity_action examples present: inbound_order_created, stock_threshold_triggered, direct_stock_edit_rejected, session_expired, api_latency_recorded
old names absent: stock_modification_rejected, api_call_completed, page_view, api_error, ui_timing
session_expired split from session_rejected; expired reason removed from session_rejected
mandatory metrics remain 34
```

Emitters are still not wired. Menus, sales, customers, and suppliers remain missing on the central API.

## Latest event envelope (`cursor/telemetry-plan-ff8d`)

Department served: **Technology**. Every Brasaland telemetry document uses one envelope so a staff request, a location sale, and a Monday job can be correlated without putting a JWT or an email on the event.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
Draft202012Validator.check_schema → pass
40 event examples validate
envelope required keys: eventID, timestamp, sessionID, UserID, Event_type, SchemaVersion, requestID, source, tags, properties
missing requestID → schema reject
UserID as an email → schema reject
null UserID on user_login_succeeded → schema reject
timestamp with a numeric offset → schema reject
sessionID shaped like a JWT → schema reject
weekly report example sessionID and UserID are null
mandatory metric ids remain 34
```

Emitters are still not wired. Menus, sales, customers, and suppliers remain missing on the central API.

## Latest mandatory versus opportunity split (`cursor/telemetry-plan-ff8d`)

Department served: **Technology**, so the team can see which telemetry is the `CONTEXT.md` baseline and which is exploration of the application and the operating procedures.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
Draft202012Validator.check_schema → pass
40 event examples validate
mandatory metrics in the plan = 34 = weekly_report_dispatched.floor_metric_ids
identified opportunity metrics = 34, no id shared with the mandatory list
mandatory events = 18, identified opportunity events = 22, together the 40 schema events
report missing people.holiday.requests → schema reject
report containing ops.stockout.count → schema reject
mkt.loyalty.points_earned is not a mandatory id
```

Earn and redeem rates, waste bands, opening hours, and the stock threshold of 10 are labeled as plan bindings or opportunities. They are not written in `CONTEXT.md`. Emitters are still not wired. Menus, sales, customers, and suppliers remain missing on the central API.

## Latest capture decisions (`cursor/telemetry-plan-ff8d`)

Department served: **Technology**, with the decision owner named on each event (Operations, Procurement, Marketing, People, Training, or Executive). An event stays only when the sentence “We capture [event_type] because we need to know [hypothesis] which allows us to make the decision, [decision]” can be completed.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
Draft202012Validator.check_schema → pass
40 event examples validate
40 capture sentences, one per event_type, none missing, none extra
floor ids = 32, example matches the schema enum
backoffice page_view → schema reject
section suppliers → schema reject
flow inventory_inbound → schema reject
```

Dropped: `session_check_failed` (same decision as `api_call_completed` on `GET /auth/me`), backoffice `page_view` (staff visits are `section_viewed`), section ids `suppliers` / `people` / `training` / `reporting`, and flows `inventory_inbound` / `inventory_outbound`. Emitters are still not wired. Menus, sales, customers, and suppliers remain missing on the central API.

## Latest backoffice catalog (`cursor/telemetry-plan-ff8d`)

Department served: **Technology** (staff-console telemetry for Nicolás Park) and **Operations** (which sections a session reaches, and which flows are left unfinished). Authentication, API timing, uncaught front-end errors, required visits, and abandoned flows are specified. The 32 Phase 1 floor ids are unchanged. `bo.*` questions are not on the weekly report list.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
Draft202012Validator.check_schema → pass
41 event examples validate
floor ids in weekly_report_dispatched example = 32, matching the schema enum
bo.* ids in the plan = 11, none of them in the floor enum
expired session from the browser → schema reject
missing_token from services.api.auth → schema reject
inactive_user from services.api.users → pass
completed account_mutation with duplicate_email → schema reject
network api_call_completed with http_status 500 → schema reject
login form with reason mismatch → schema reject
email property on auth_form_rejected → schema reject
website client_exception with app backoffice → schema reject
componentStack on client_exception → schema reject
executive_sales ready true → schema reject
suppliers required false → schema reject
ui_timing kind form with name inventory → schema reject
weekly report missing people.turnover → schema reject
```

Emitters are still not wired. Menus, sales, customers, and suppliers remain missing on the central API.

## Latest inventory-flow instrumentation (`cursor/telemetry-plan-ff8d`)

Department served: **Technology** and **Operations**. The authenticated inventory path is mapped through inbound and outbound completion, including refused stock writes, 422 validation, and the minimum-stock crossing.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
Draft202012Validator.check_schema → pass
31 event examples validate
stock_modification_rejected below_zero, product_not_found, and negative_alert_threshold validate
below_zero without quantity_before → schema reject
```

## Latest telemetry floor catalog (`cursor/telemetry-plan-ff8d`)

Department served: **Technology**, so every `CONTEXT.md` day-one metric for Operations, Procurement, Marketing, People, Training, and Executive stays in the telemetry plan.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
Phase 1 floor ids in telemetry-plan.md = 32
weekly_report_dispatched example lists the same 32 ids
Draft202012Validator.check_schema → pass
29 event examples validate
Dropping people.turnover from floor_metric_ids → schema reject
```

Emitters are still not wired. Menus, sales, customers, and suppliers remain missing on the central API.

## Latest telemetry plan (`cursor/telemetry-plan-ff8d`)

Department served: **Technology** (real-time telemetry contract for Nicolás Park) so Restaurant Operations and Executive metrics in `CONTEXT.md` can be instrumented on the existing inventory API, login handlers, and weekly pipeline.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
python3 -c json load docs/telemetry/event-schemas.json
Draft202012Validator.check_schema → pass
17 examples validate (format checks on)
pipeline event types present: inbound_order_created, stock_waste_registered, stock_threshold_triggered, ingredient_price_variance_detected
locationId enum count = 14
rejected: US location + COP, chain event with location_id, email field, protein waste > 2kg without note, balance_before 10
```

Emitters are specified in `docs/telemetry/telemetry-plan.md` and are not implemented in this change. Technology’s menus/sales/customers/suppliers nouns remain **missing**.

Merge note (`origin/main` at `9d17da1`): menus, sales, customers, and suppliers are seeded on the central API, and `POST /sales` feeds the no-sales alert. Sentences in the telemetry sections above that say those nouns are missing describe this branch before that merge. Catalog emitters are still not wired.

## Latest business performance pipeline Part 2 (`cursor/business-performance-pipeline-part2-4f14`)

Department served: **Technology** (Nicolás — pipeline into ops/finance dashboards) + **Restaurant Operations** (Felipe — purchase/waste/stockouts) + **Procurement** (Lucía — purchase cost + price alerts) + **Executive** (Mariana — Monday location-week numbers).

Implemented against `CONTEXT-company.md` (KPIs to Measure / destination schema / endpoints) and approved `data/pipelines/PIPELINE_DESIGN.md`:

- Pure transform in `data/process/location_kpis.py` (dedupe on `telemetry_events.id`, five KPIs, roster `location_id`s).
- Prefect **3** flow `brasaland_weekly_performance_pipeline` with stage subflows
  `extract_brasaland_data_flow` → `transform_brasaland_kpis_flow` → `load_brasaland_reporting_flow`
  and tasks `extract_telemetry_events` / `extract_domain_data` / `aggregate_location_kpis` /
  `upsert_to_reporting_table` into `reporting.weekly_location_performance`.
- Extract lands in `data/raw/`; validation output in `data/eval/last_validation.json`.
- Destination `reporting.weekly_location_performance` + run log `reporting.pipeline_runs` (SQL in `data/pipelines/reporting_schema.sql`); mirror `data/pipelines/last_run.json`.
- HTTP shell in `services/reporting/` only — engineering telemetry left alone.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
uv run python -c "import prefect; print(prefect.__version__)" → 3.4.25
uv run python -m pytest tests/pipelines/ -q → 23 passed
Idempotent load: upsert on_conflict=location_id,week_start (CONTEXT PK); identical re-run payloads
Run metadata: started_at, finished_at, records_processed, status, error_message → pipeline_runs + last_run.json + pipeline_run_log.jsonl
```

## Latest Phase one — Prefect subflows (`cursor/pipeline-phase1-subflows-4f14`)

Department served: **Technology** (Nicolás — pipeline structure) + **Operations/Executive** (weekly KPI stages stay readable and isolatable).

Hardened `data/pipelines/pipeline.py` so Monday ETL is three stage `@flow` subflows with explicit I/O (no shared globals), plus optional eval as its own subflow:

| Subflow `name=` | Inputs → Outputs |
| --- | --- |
| `extract_brasaland_data_flow` | `(start_date, end_date)` → `(telemetry_df, locations_df)` |
| `transform_brasaland_kpis_flow` | `(telemetry_df, locations_df, week_start)` → `kpis_df` |
| `load_brasaland_reporting_flow` | `kpis_df` → rows upserted |
| `eval_brasaland_snapshot_flow` | `(kpis_df, week_start)` → validation dict (`return_state=True` from main) |

Main flow remains `brasaland_weekly_performance_pipeline`. Destination stays `reporting.weekly_location_performance`. `PIPELINE_DESIGN.md` Phase 4 name contract updated.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
.venv/bin/python -m pytest tests/pipelines/test_prefect_stages.py tests/pipelines/test_name_contract.py -q → 14 passed
.venv/bin/python -m pytest tests/pipelines/ -q → 30 passed
```

## Latest Phase two — transform unit tests (`cursor/pipeline-phase2-transform-tests-4f14`)

Department served: **Technology** (Nicolás — KPI transform correctness) + **Restaurant Operations** (Felipe — purchase/waste/stockouts) + **Procurement** (Lucía — purchase cost + price alerts).

Extended `tests/pipelines/test_pipeline.py` with isolated in-memory unit tests for CONTEXT-company.md "KPIs to Measure" (no DB / external APIs): `total_purchase_cost`, `total_waste_cost`, `waste_ratio` (hand-calculated 4dp + zero-purchase → 0), `stockout_events_count` / `price_alert_events_count`, Prefect task `.fn` parity, and defensive malformed payloads (non-dict, null cost/location, wrong cost type, missing columns).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
.venv/bin/python -m pytest tests/pipelines/test_pipeline.py -v → 14 passed
```

## Latest Phase three — CLI after subflow refactor (`cursor/pipeline-phase3-cli-4f14`)

Department served: **Technology** (Nicolás — Monday-runnable pipeline into ops/finance) + **Executive** (Mariana — Monday 07:00 America/Bogota reporting cycle).

After Phase one subflow hardening, restored Part 2 / Phase 4 script entry onto the same Prefect flow (did not invent a new CLI module):

- `if __name__ == "__main__"` → `main()` → `brasaland_weekly_performance_pipeline` / `run_pipeline`
- Flags: `--start-date`, `--end-date`, `--offline` (also auto-offline when `SUPABASE_*` unset)
- Offline rebinds `fetch_telemetry_events` / `fetch_domain_locations` / `persist_kpi_records` so extract → transform → load subflows still run with explicit I/O
- `PIPELINE_DESIGN.md` Script-based execution / Intended reporting schedule docs kept (same commands)

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
.venv/bin/python data/pipelines/pipeline.py --offline --start-date 2026-09-21 --end-date 2026-09-28
→ exit 0; status=Success records_processed=9
  subflows: extract_brasaland_data_flow → transform_brasaland_kpis_flow → load_brasaland_reporting_flow (Completed)
.venv/bin/python data/pipelines/pipeline.py --offline
→ exit 0; status=Success records_processed=9; window=[2026-09-14, 2026-09-21)
.venv/bin/python -m pytest tests/pipelines/ -q → 36 passed
```

## Planned next steps (order)

1. Keep every product change traceable to a `CONTEXT.md` department need (name the section in the PR/commit).
2. Central API nouns **locations, menus, sales, customers, and suppliers** are seeded on `uvicorn api.app:app`. A live POS, live invoices, and a digital Brasa Points wallet are still open.
3. Executive path: chain sales in **USD and COP** are seeded and shown on portal `/ops/sales`. Monday 07:00 delivery is the n8n workflow in `workflows/` (it reads the reporting API; it does not enqueue the pipeline). Keep Mariana’s NL assistant on the documented agent loop.
4. Later phases: keep staff dashboard consumers for `reporting.weekly_location_performance` current; extend sales USD+COP for Mariana.
5. Do not rewrite the monorepo or invent another company.

## Latest Phase four — business dashboard (`cursor/pipeline-phase4-dashboard-4f14`)

Department served: **Executive** (Mariana — Monday location-week numbers) + **Restaurant Operations** (Felipe — purchase/waste/stockouts) + **Procurement** (Lucía — purchase cost + price alerts) + **Technology** (Nicolás — reporting feed on central API).

Backoffice page `/reporting/weekly-performance` fetches Bearer-gated `GET /reporting/weekly-location-performance` and renders every CONTEXT-company.md KPI (Purchase cost, Waste cost, Waste ratio, Stockout frequency, Price alert frequency) with chain-week period (`week_start` + `[Monday, next Monday)` America/Bogota) and COP/USD rows. Vite proxies API paths only (`/reporting/weekly-location-performance`, `/reporting/pipeline-runs`) so the SPA route is not swallowed. Reporting routes mounted on `services/api/app.py` with JWT; offline KPI store readable when Supabase unset.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
GET http://127.0.0.1:8000/docs → 200
locations=present menus=missing sales=missing customers=missing suppliers=missing inventory=present reporting=present
path_count=25
GET /reporting/weekly-location-performance without token → 401
GET /reporting/weekly-location-performance with Bearer → 200, week_start=2026-09-21, COP+USD rows, five KPI columns
cd uis/backoffice && npm run build → tsc -b && vite build green
.venv/bin/python -m pytest tests/pipelines/ -q → 41 passed
```

Skill **passed** (criteria 1–4 + 6). Technology central API remains **incomplete** while menus/sales/customers/suppliers are `missing`.

## Latest Phase four stakeholder UX (`cursor/pipeline-phase4-stakeholder-ux-4f14`)

Department served: **Executive** (Mariana) + **Restaurant Operations** (Felipe) + **Procurement** (Lucía) — Monday report must be legible without API/table jargon.

Hardened `uis/backoffice` Monday weekly report copy for leadership:

- Title/nav: “Monday weekly ops & finance report” / “Monday weekly report” (not “Weekly KPIs” / KPI query)
- Lead and empty states drop endpoint paths, table names, Bearer, backticks, CLI commands, and engineering telemetry notes
- Column labels stay CONTEXT-company.md exact: Purchase cost, Waste cost, Waste ratio, Stockout frequency, Price alert frequency
- Period shown as chain week starting Monday YYYY-MM-DD (America/Bogota); location column shows friendly names only (no raw `location_id` as primary label)
- Still fetches `GET /reporting/weekly-location-performance` under the hood

Prefect / test vocabulary: `PIPELINE_DESIGN.md` Phase 4 `name=` contract already matches `data/pipelines/pipeline.py` and `tests/pipelines/test_name_contract.py` (`brasaland_weekly_performance_pipeline`, `extract_brasaland_data_flow`, `transform_brasaland_kpis_flow`, `load_brasaland_reporting_flow`, `eval_brasaland_snapshot_flow`, domain tasks). No renames required; no generic `extract_data` / `business_metrics` left.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
.venv/bin/python -m pytest tests/pipelines/ -q → 41 passed
cd uis/backoffice && npm run build → tsc -b && vite build green
Manual UI (CDP): login → Monday weekly report; audit forbidden jargon hits=[]; required KPI labels present; friendly location names; COP+USD; period America/Bogota
Artifacts: stakeholder_ux_03_monday_report.png, stakeholder_ux_04_kpi_table.png, stakeholder_ux_monday_report_walkthrough.mp4
```

## Latest milestone 9 — n8n Monday leadership report (`cursor/n8n-monday-leadership-report-3cb7`)

Department served: **Executive** (Mariana Restrepo — automated weekly report Monday 07:00) with **Restaurant Operations** (Felipe Guerrero) and **Procurement** (Lucía Fernández) figures on the same report (purchase, waste, stockouts, price alerts, COP and USD kept separate).

Importable workflow `workflows/brasaland-monday-leadership-report.n8n.json` (inactive until credentials exist):

- Schedule cron `0 7 * * 1` with workflow timezone `America/Bogota` (not America/New_York: Bogotá has no daylight saving, and the chain week in `previous_chain_week_bounds` is America/Bogota). Manual trigger for a grader test.
- `POST /auth/login` using `BRASALAND_STAFF_EMAIL` / `BRASALAND_STAFF_PASSWORD`, then `GET /reporting/weekly-location-performance?week_start=` with Bearer JWT.
- Leadership text plus CSV under `/home/node/brasaland-reports` (host `workflows/out/`). Email (SMTP credential placeholder, CSV attached) and Slack (API credential placeholder) run when their env vars are set.
- Error output from login, missing token, KPI query, format, CSV write, email, and Slack writes `brasaland-weekly-failure.txt` and notifies when delivery env vars are set.
- Local n8n: `workflows/docker-compose.n8n.yml` (`n8nio/n8n:1.123.81`). Root `docker-compose.yml` was not changed.
- No live secrets in the export. Docker was not available in this run, so n8n itself was not started; the export was checked with the structure script and Node execution of the embedded week and report functions.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
python3 workflows/validate_weekly_report_workflow.py
→ OK brasaland-monday-leadership-report.n8n.json
  nodes=23
  schedule=0 7 * * 1 timezone=America/Bogota active=false
  sample COP purchase=1000.00 USD purchase=50.00
  chain-week instants checked=7
python3 -m pytest tests/test_n8n_weekly_workflow.py -q → 1 passed
```

## Latest Next.js portal (`cursor/nextjs-brasaland-portal-9a60`)

Department served: **Marketing** (Camila Ospina — digital Brasa Points) + **Restaurant Operations** (Felipe Guerrero — sales per location in COP and USD) + **Executive** (Mariana Restrepo — chain totals in both currencies). The portal calls Technology’s customers and sales nouns when `BRASALAND_DATA_SOURCE=live`. Before this merge those routers were **missing** on the branch, so the default is a typed fixture client. This does not complete a live POS or a digital wallet.

- App: `uis/portal` (Next.js App Router, TypeScript). Routes `/`, `/points`, `/points/[customerId]`, `/ops/sales`.
- Client: `GET /customers`, `GET /customers/{id}`, `GET /sales` (`location_id` + `currency`). Fallback when the live call fails. Staff JWT via `BRASALAND_API_TOKEN` (not committed).
- Points math from `docs/company-knowledge-base/brasaland-loyalty-program.en.md` (10,000 COP or 10 USD = 1 point; Bronze/Silver/Gold; redeem from 15 in steps of 5).
- Brand tokens match `uis/website` (charcoal, ember, Outfit, Source Sans 3).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
Live mode matches draft central API shapes on `cursor/central-api-nouns-5989` (PR #89): `brasa_points_balance` + `loyalty_tier` + `order_history` without spend; `GET /sales` tickets (`amount`, `currency`, `location_id`, `occurred_at`) rolled up per location. `GET /sales/overview` location rows still accepted.
cd uis/portal && npm test → 16 passed (loyalty, COP/USD conversion, ticket rollup, stamp-card balance, env switch, fixture fallback)
cd uis/portal && npm run build → Next.js 15.5.26 compiled; routes / , /points , /points/[customerId] , /ops/sales
npm start → :3000
Browser: unknown email → not-found alert; ana.morales@guest.brasaland.example → balance 23, Silver, history, rewards
/ops/sales → chain COP $476,340,000 and chain USD $119,085.00; Florida filter → 6 Florida rows, Colombia hidden
Narrow viewport still shows the sales heading; console clear
```

Technology central API remains **incomplete** while menus/sales/customers/suppliers are `missing` on `services/api/app.py`. That sentence describes the portal run before the merge. After `origin/main` (`7b0a125`) those nouns, `POST /knowledge/query`, and `GET /realtime/ops-alerts/stream` are mounted with the portal.

## Latest central API nouns (`cursor/central-api-nouns-5989`)

Department served: **Technology** (Nicolás Park — locations, menus, sales, customers, suppliers on one server) + **Operations** (Felipe — per-location COP/USD tickets and a no-sales alert list) + **Procurement** (Lucía — ~20 suppliers and price history) + **Marketing** (Camila — CRM with a Brasa Points stamp-card balance) + **Executive** (Mariana — chain totals in COP and USD) + **Training** (Jake — same menu in all 14 kitchens).

Built on `main` (`a7c9bf9`), not draft PR #64. Routers: `services/api/menus.py`, `sales.py`, `customers.py`, `suppliers.py`. `app.py` only mounts them; reporting stays mounted. Seeded snapshot, not a live POS. Brasa Points stay physical stamp cards (`digital_loyalty=false`).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
GET http://127.0.0.1:8000/docs → 200
locations=present
menus=present
sales=present
customers=present
suppliers=present
inventory=present
path_count=39
reporting paths still present
python3 -m pytest tests/test_central_api_domains.py -q → 7 passed
python3 -m pytest tests/test_users_api.py tests/test_error_handling.py -q → 27 passed
GET /menus/catalogue → 6 items, currencies COP+USD, location_count 14
GET /sales/overview without token → 401
GET /sales/overview with Bearer → 14 locations, 42 tickets, chain_total_cop=476340000, chain_total_usd=119085, florida_total_usd=53460
GET /customers/cus-001 → Brasa Points, brasa_points_balance=32, loyalty_tier=silver, digital_loyalty=false
GET /suppliers/overview → total_suppliers=20, colombia_count=10, florida_count=10, price_alerts=8
```

Skill **passed** (criteria 1–4 and 6). Criterion 5: locations, menus, sales, customers, and suppliers are **present**. That does not make POS integration, telemetry, or a digital loyalty wallet complete.

## Latest knowledge RAG (`cursor/knowledge-rag-query-34a7`)

Department served: **Training** (Jake Morrison — searchable standards) + **Technology** (Nicolás Park — one route on the central API) + **Executive** (Mariana can ask a standards question; this is not the chain-sales assistant).

Kept `data/process/rag.py` + `data/pipelines/rag.py` (collection `brasaland_kb`, allergen and COP/USD rules). Retired `scripts/rag.py` (it searched `company_knowledge_base`) by making it delegate here. `services/api/main.py` no longer imports a missing router; it starts the same central app. `POST /knowledge/query` is `services/knowledge/routes.py`, included from `services/api/app.py`.

Default path needs no API key: local hashed embeddings and an extractive answer with cited chunks. `BRASALAND_RAG_BACKEND=qdrant` and `BRASALAND_RAG_LLM=openai` enable the vector store and chat model. Loyalty copy now matches `CONTEXT.md` (physical stamp cards; digital app not available yet).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
GET http://127.0.0.1:8000/docs → 200
locations=present
menus=missing
sales=missing
customers=missing
suppliers=missing
inventory=present
knowledge=present
path_count=26
/knowledge/query in OpenAPI → True
POST /knowledge/query House Sauce → 200, soy + sulfites, source brasaland-menu-allergens.en.md
POST unrelated question → not enough information, sources=[]
python data/eval/eval_knowledge_qa.py → n=28 retrieval_hit_rate=1.000 answer_pass_rate=1.000
python -m pytest tests/test_knowledge_query.py -q → 14 passed
```

Skill **passed** (criteria 1–4 + 6). At the time of that run, Technology’s menus/sales/customers/suppliers were still `missing`. Those nouns are mounted together with `/knowledge/query` after the merge from `origin/main` (`#89`).

## Latest merge of #89 into knowledge query (`cursor/knowledge-rag-query-34a7`)

Department served: **Technology** (Nicolás Park — menus, sales, customers, suppliers, and `POST /knowledge/query` on one server) + **Training** (Jake Morrison — searchable standards stay mounted).

Merged `origin/main` (`5751231`, PR #89) into this branch. `services/api/app.py` includes `menus`, `sales`, `customers`, `suppliers`, and `services.knowledge.routes`. Both Progress entries above are kept.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
GET http://127.0.0.1:8000/docs → 200
locations=present
menus=present
sales=present
customers=present
suppliers=present
inventory=present
knowledge=present
path_count=40
/menus /sales /customers /suppliers GET present
/knowledge/query POST present
python -m pytest tests/test_knowledge_query.py tests/test_central_api_domains.py -q → 21 passed
python -m pytest -q → 110 passed
```

Skill **passed** (criteria 1–4 and 6). Criterion 5: locations, menus, sales, customers, and suppliers are **present**, and `/knowledge/query` is present. That does not make POS integration, telemetry, or a digital loyalty wallet complete.

## Latest live no-sales alert (`cursor/realtime-no-sales-alert-198b`)

Department served: **Restaurant Operations** (Felipe Guerrero — alert when a location has no sales during opening hours) + **Technology** (Nicolás Park — real-time telemetry on the central API).

SSE on `GET /realtime/ops-alerts/stream` (Bearer JWT, `fetch` + `ReadableStream`). Detection lives in `services/api/no_sales.py`; the router is `services/api/no_sales_router.py`. Sales enter through `sales_events.record_sale` so a future `/sales` router can hook in without this channel owning that noun. OpenAPI paths do not contain `sales`, so the coverage script still reports `sales=missing`.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
GET http://127.0.0.1:8000/docs → 200
locations=present
menus=missing
sales=missing
customers=missing
suppliers=missing
inventory=present
path_count=28
/realtime/ops-alerts /realtime/ops-alerts/stream /realtime/ops-alerts/simulate present
GET /realtime/ops-alerts/stream without token → 401
python scripts/simulate_no_sales.py quiet --location co-med-centro → alert COP, quiet_minutes=31
python scripts/simulate_no_sales.py resume --location co-med-centro --amount 48000 --currency COP → status=cleared
NO_SALES_MONITOR=0 .venv/bin/python -m pytest tests/test_no_sales_alerts.py tests/test_users_api.py -q → 34 passed
node --experimental-strip-types --test uis/backoffice/tests/noSalesAlerts.test.ts → 8 passed
cd uis/backoffice && npm run build → tsc -b && vite build green
Browser http://127.0.0.1:5174/accessible (grader.ops@brasaland.test): Live → Simulate no sales → banner + list Medellín Centro COP, no reload → Record a sale (48000 COP) → row gone, “No open location is quiet right now.” Same flow at 390px width.
```

Skill **passed** (criteria 1–4 + 6). At the time of that run, Technology’s menus/sales/customers/suppliers were still `missing`. Those nouns, `POST /knowledge/query`, and the realtime router are mounted together after the merge from `origin/main` (`0813179`).

Draft PRs **#53** (SSE tickets) and **#54** (WebSocket knowledge chat) can be closed. This branch reuses the SSE shape (named events, JWT via fetch, Last-Event-ID, reconnect backoff) on current `main` for the no-sales alert. Those drafts target other features and have diverged from `main`.

## Latest merge of main into the no-sales alert (`cursor/realtime-no-sales-alert-198b`)

Department served: **Restaurant Operations** (Felipe Guerrero — live no-sales alert stays mounted) + **Technology** (Nicolás Park — locations, menus, sales, customers, suppliers, inventory, users, reporting, knowledge, and realtime on one server).

Merged `origin/main` (`0813179`, PR #93) into this branch. `services/api/app.py` includes the #89 routers, `services.knowledge.routes`, and `register_ops_alerts`. `locations.py` keeps `location_roster`, `all_locations`, and `get_location`. Progress keeps the central-API, knowledge, and no-sales entries.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
/locations /menus /sales /customers /suppliers /inventory /users present
/reporting/weekly-location-performance present
/knowledge/query present
/realtime/ops-alerts/stream present
path_count=43
NO_SALES_MONITOR=0 python -m pytest -q → 127 passed
cd uis/backoffice && npm run build → tsc -b && vite build green
node --experimental-strip-types --test uis/backoffice/tests/noSalesAlerts.test.ts → 8 passed
```

## Latest merge of main into the Next.js portal (`cursor/nextjs-brasaland-portal`)

Department served: **Marketing** (Camila Ospina — `/points` stays) + **Restaurant Operations** (Felipe Guerrero — `/ops/sales` stays beside the live no-sales alert) + **Technology** (Nicolás Park — seeded nouns, knowledge query, and realtime stream stay mounted).

Merged `origin/main` (`7b0a125`) into this branch. The only content conflict was `memory-bank/Progress.md`. Root package files, `.gitignore`, and CI did not overlap. `uis/README.md` keeps website, backoffice (including the no-sales alert), portal, and `web/`.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
NO_SALES_MONITOR=0 python -m pytest -q → 127 passed
cd uis/portal && npm ci && npm test → 16 passed
cd uis/portal && npm run build → Next.js 15.5.26; routes / , /points , /points/[customerId] , /ops/sales
```

## Latest merge of main into the Monday leadership workflow (`cursor/n8n-monday-leadership-report`)

Department served: **Executive** (Mariana Restrepo — Monday 07:00 America/Bogota report stays) + **Technology** (Nicolás Park — the workflow still reads the central reporting API that is mounted with the other routers).

Merged `origin/main` (`940987f`) into this branch. The only content conflict was `memory-bank/Progress.md`. Docs indexes for the central API, knowledge query, and no-sales alert stay, and `workflows/README.md` keeps the Monday report. The n8n export was not rewritten.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
python3 -c json.load(workflows/brasaland-monday-leadership-report.n8n.json) → name=Brasaland Monday leadership report nodes=23
python3 workflows/validate_weekly_report_workflow.py → OK schedule=0 7 * * 1 timezone=America/Bogota active=false
python3 -m pytest tests/test_n8n_weekly_workflow.py -q → 1 passed
NO_SALES_MONITOR=0 python -m pytest -q → 128 passed
```

## Latest sales feed into the no-sales alert (`cursor/sales-feed-no-sales-alert-d91e`)

Department served: **Restaurant Operations** (Felipe Guerrero — a real ticket clears a quiet location) + **Technology** (Nicolás Park — `POST /sales` on the central API calls `record_sale`).

`GET /sales` was read-only. `POST /sales` appends the ticket to the same in-memory list and calls `record_sale` in `services/api/sales_events.py`. Unknown locations are 404. A currency that is not the location's COP or USD is 400.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
NO_SALES_MONITOR=0 python -m pytest -q → 131 passed
node --experimental-strip-types --test uis/backoffice/tests/noSalesAlerts.test.ts → 8 passed
POST /sales co-med-centro 48000 COP during an open alert → 201, active alerts cleared, ticket on GET /sales
POST /sales before evaluate → no alert raised
POST unknown location → 404; Colombia location with USD → 400; EUR → 422; amount 0 → 400
```

## Latest merge of main into the telemetry plan (`cursor/telemetry-plan-ff8d`)

Department served: **Technology** (Nicolás Park — telemetry contract plus the central API). Merged `origin/main` (`9d17da1`) and kept every telemetry evaluation section and every later main section (pipeline, portal, RAG, n8n, live no-sales, `POST /sales`).

The catalog is unchanged: 41 events (18 mandatory + 23 identified opportunities). `Draft7Validator.check_schema` passes, and the schema `oneOf` is the same 41 `Event_type` values as the plan catalog. Emitters are still not wired. Menus, sales, customers, and suppliers are seeded on `uvicorn api.app:app` (they are not missing).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
NO_SALES_MONITOR=0 python -m pytest -q → 131 passed, 5 warnings in 92.39s
Draft7Validator.check_schema(docs/telemetry/event-schemas.json) → pass
plan catalog == schema oneOf == 41 (18 mandatory + 23 opportunity)
```

## How to update this file

After a verified change, append evidence (command + result) and update the coverage table. Do not log plans that were not run.
