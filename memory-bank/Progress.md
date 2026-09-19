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
| Technology: central API (locations, menus, sales, customers, suppliers) | **Partial** — `locations=present`; `auth`/`users=present`; `menus`/`sales`/`customers`/`suppliers=missing`; `inventory=present` (SQLModel `Ingredient`/`IngredientEntry`/`IngredientExit` under `/inventory/products` and `/inventory/orders`; CSV Groq agent moved to `/agent/inventory`; TinyDB auth) |
| Technology: telemetry + pipeline to dashboards | **Partial** — `data/pipelines/` weekly location cost/waste; Celery async path |
| Operations: sales per location COP/USD; no-sales alerts; smart ordering | **Not done** as product UI; pipeline design targets cost/waste for Mariana + Felipe |
| Procurement: supplier price history, consolidated spend | **Not done** (supplier docs may exist on other branches; not claimed here) |
| Marketing: digital Brasa Points, CRM, personalisation | **Partial** — `uis/website/` corporate home (`/`) live; Brasa Points still stamp cards per `CONTEXT.md` |
| People: HR portal / KPIs by country | **Not done** |
| Training: recipe catalogue, push to 14 locations | **Not done** — knowledge docs under `docs/company-knowledge-base/` are source material only |
| Executive: sales USD+COP dashboard, NL assistant, Monday 07:00 report | **Partial hooks** — inventory Groq agent; weekly pipeline + Flower; backoffice placeholder for USD+COP sales |

## What already runs (engineering)

| Area | Evidence |
| --- | --- |
| Inventory API + Groq agent | ORM computed stock: `services/routers/inventory.py`; CSV agent: `services/api/inventory.py` + `agent.py` under `/agent/inventory` |
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

## Latest testing toolchain (`feature/error-handling-audit`)

Department served: **Technology** (auth API on the central FastAPI app needs pytest for bullet-proof coverage of login/register/JWT).

```text
origin = Rickycastro1940/ai-engineering-company-project-monorepo (existing fork)
uv add --dev pytest pytest-cov httpx
pytest 8.4.2 / pytest-cov 7.1.0 / httpx 0.28.1
uv run python -m pytest tests/test_users_api.py -q → 17 passed
```

Jest was not installed: the previous-milestone auth surface is Python/FastAPI (`services/api/auth.py`, `/auth/token`, `/auth/login`, `/auth/register`, `/auth/me`), not a TypeScript API.

## Latest live API check (`feature/error-handling-audit`)

Department served: **Technology** (central FastAPI `api.app:app` on `:8000`).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
uv run uvicorn api.app:app --reload --host 127.0.0.1 --port 8000 → Application startup complete
GET /docs → 200
locations=present menus=missing sales=missing customers=missing suppliers=missing inventory=present auth=present
path_count=21
GET /auth/me no token → 401
POST /auth/register → 201 + access_token
GET /auth/me Bearer → 200
GET /locations/overview Bearer → 200, 14 locations, Colombia 8 / Florida 6, COP+USD
```

Skill **passed** (criteria 1–4 + 6). Technology central API remains **incomplete** while menus/sales/customers/suppliers are `missing`.

## Latest AI-assisted auth edge cases (`feature/error-handling-audit`)

Department served: **Technology** (JWT register/login/token/me plus RBAC gaps the endpoint review found).

```text
TESTING.md — tests assert session/role/password decisions, not HTTP envelopes
AI-found bug: GET /inventory/products requires staff session (Depends(get_current_user))
CSV Groq agent no longer shares /inventory (moved to /agent/inventory)
```

## Latest business-logic + Jest suite (`feature/error-handling-audit`)

Department served: **Technology** (staff JWT decisions on the central API) + **Operations/Executive** (backoffice only stores a well-formed session token).

Intent over coverage: cases exist for who may sign in, who is admin, and whether kitchen stock is anonymous. 70% on auth/users is the floor; unused CRUD lines stay uncovered on purpose. Jest in `uis/backoffice` is optional extra.

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
TESTING.md — AI-assisted missed cases + inventory bug (test_anonymous_cannot_read_kitchen_stock)
```

## Latest ORM inventory + CSV agent move (`feature/error-handling-audit`)

Department served: **Operations** (computed kitchen stock) + **Technology** (dual TinyDB + SQLModel, `/inventory` router).

```text
testing.md at repo root — run commands, existing suites, happy/edge/failure per /auth /users /profiles /locations
uv run pytest test/test_inventory_orm.py tests/test_error_handling.py tests/test_users_api.py
CSV agent prefix /agent/inventory; ORM products/orders under /inventory
.env is gitignored (never commit DATABASE_URL credentials)
```

## Planned next steps (order)

1. Keep every product change traceable to a `CONTEXT.md` department need (name the section in the PR/commit).
2. Extend the central API toward missing Technology nouns: **locations → menus → sales → customers → suppliers**, reusing `services/api` routers.
3. Executive path: surface chain sales in **USD and COP**, wire Monday-style weekly report to the existing async pipeline, keep Mariana’s NL assistant on the documented agent loop.
4. Do not rewrite the monorepo or invent another company.

## How to update this file

After a verified change, append evidence (command + result) and update the coverage table. Do not log plans that were not run.
