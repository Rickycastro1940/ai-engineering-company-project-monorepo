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
| Technology: central API (locations, menus, sales, customers, suppliers) | **Partial** — `locations=present`; `auth`/`users=present`; `menus`/`sales`/`customers`/`suppliers=missing`; `inventory=present` on `:8000` |
| Technology: telemetry + pipeline to dashboards | **Partial** — 34 mandatory metrics, stream/batch delivery by decision urgency (Phase 3), property allowlists, draft-07 schemas, envelope. Weekly cost/waste pipeline and Celery path exist. Live emitters are not wired |
| Operations: sales per location COP/USD; no-sales alerts; smart ordering | **Not done** as product UI; pipeline design targets cost/waste for Mariana + Felipe |
| Procurement: supplier price history, consolidated spend | **Not done** (supplier docs may exist on other branches; not claimed here) |
| Marketing: digital Brasa Points, CRM, personalisation | **Partial** — `uis/website/` corporate home (`/`) live; Brasa Points still stamp cards per `CONTEXT.md` |
| People: HR portal / KPIs by country | **Not done** |
| Training: recipe catalogue, push to 14 locations | **Not done** — knowledge docs under `docs/company-knowledge-base/` are source material only |
| Executive: sales USD+COP dashboard, NL assistant, Monday 07:00 report | **Partial hooks** — inventory Groq agent; weekly pipeline + Flower; backoffice placeholder for USD+COP sales |

## What already runs (engineering)

| Area | Evidence |
| --- | --- |
| Inventory API + Groq agent | `services/api/inventory.py` (CSV-backed flat imports; no package-relative `.auth`), `agent.py` |
| Incident analysis UI | `uis/web` |
| Weekly cost/waste pipeline + Celery | `data/pipelines/`, `services/tasks.py`, Compose Redis/Flower/worker on this branch |
| Public corporate website | `uis/website/` — Vite/React, route `/`, brand tokens + components from `CONTEXT.md`; screenshot `docs/screenshots/website-corporate-home.png` |
| Internal backoffice | `uis/backoffice/` — JWT session; client layout guard (`ProtectedRoute` + `useRequireAuth`) on `/`, `/accessible`, `/account/profile`, `/account/change-password`; `/accessible` loads JWT-gated locations (14 / 8 Colombia / 6 Florida, COP+USD) plus inventory |
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

## Planned next steps (order)

1. Keep every product change traceable to a `CONTEXT.md` department need (name the section in the PR/commit).
2. Extend the central API toward missing Technology nouns: **locations → menus → sales → customers → suppliers**, reusing `services/api` routers.
3. Executive path: surface chain sales in **USD and COP**, wire Monday-style weekly report to the existing async pipeline, keep Mariana’s NL assistant on the documented agent loop.
4. Do not rewrite the monorepo or invent another company.

## How to update this file

After a verified change, append evidence (command + result) and update the coverage table. Do not log plans that were not run.
