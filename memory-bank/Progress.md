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
| Technology: central API (locations, menus, sales, customers, suppliers) | **Present** — `locations`/`menus`/`sales`/`customers`/`suppliers`/`inventory` on `:8000` (sales/customers/suppliers JWT; menus public; POS still not live) |
| Technology: telemetry + pipeline to dashboards | **Partial** — `data/pipelines/` weekly location cost/waste; Celery async path |
| Operations: sales per location COP/USD; no-sales alerts; smart ordering | **Partial** — `GET /sales/overview` and `/sales/alerts` (JWT, 14 sites, COP+USD snapshot); no smart ordering; no ops dashboard UI |
| Procurement: supplier price history, consolidated spend | **Partial** — `GET /suppliers` 20 vendors Colombia+Florida with `price_history` and `price_alert`; no negotiation UI |
| Marketing: digital Brasa Points, CRM, personalisation | **Partial** — `GET /customers` CRM + order history; Brasa Points still physical stamp cards; public site `/` live |
| People: HR portal / KPIs by country | **Not done** |
| Training: recipe catalogue, push to 14 locations | **Partial** — `GET /menus/catalogue` same recipes + COP/USD prices for 14 kitchens; no push/onboarding platform |
| Executive: sales USD+COP dashboard, NL assistant, Monday 07:00 report | **Partial** — `GET /sales/overview` chain COP+USD; inventory Groq agent; weekly pipeline + Flower; no Monday email yet |

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

## Latest uis Node Alpine image (`cursor/uis-node-alpine-dockerfile-2c91`)

Department served: **Technology** (repeatable container runtime) + **Marketing** (Camila’s public site) + **Operations/Executive** (staff backoffice).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
docker build -t brasaland-uis ./uis → FROM node:22-alpine, image library/node
RUN npm ci --prefix /uis/website (32 packages) then RUN npm ci --prefix /uis/backoffice (32 packages) — separate layers
container: NODE=v22.23.2 PRETTY_NAME="Alpine Linux v3.24"
/uis/website/node_modules and /uis/backoffice/node_modules both present (react ok)
docker run -w /uis/website … npm run build → tsc -b && vite build green
docker run -w /uis/backoffice … npm run build → tsc -b && vite build green
GET http://127.0.0.1:5173/ → 200 <title>Brasaland — Grilled food, Colombia & Florida</title>
GET http://127.0.0.1:5174/login → 200 <title>Brasaland Backoffice</title>
```

Does **not** complete Technology’s central API (menus/sales/customers/suppliers still missing).

## Latest central API nouns (`cursor/central-api-nouns-2c91`)

Department served: **Technology** (Nicolás Park — locations, menus, sales, customers, suppliers) + **Operations/Executive** (sales COP/USD) + **Marketing** (CRM, physical Brasa Points) + **Procurement** (~20 suppliers, price alerts) + **Training** (same chain menu).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
GET http://127.0.0.1:8000/docs → 200
locations=present
menus=present
sales=present
customers=present
suppliers=present
inventory=present
path_count=34
PYTHONPATH=/workspace python3 -m pytest tests/test_central_api_domains.py tests/test_users_api.py -q → 22 passed
GET /menus/catalogue → 6 items, COP+USD, 14 kitchens
GET /sales/overview without token → 401; with JWT → 14 locations, chain COP+USD
GET /customers/overview → digital_loyalty=false, Brasa Points physical
GET /suppliers/overview → 20 suppliers, 10 Colombia / 10 Florida, price alerts
```

Skill **passed**. Seeded snapshots; POS is still not integrated (`CONTEXT.md`).

## Latest uis start.sh Next.js pair (`cursor/uis-start-sh-2c91`)

Department served: **Technology** (container runtime) + **Marketing** (website :3000) + **Operations/Executive** (backoffice :3001).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
docker inspect Cmd → ["./start.sh"] ExposedPorts 3000/tcp 3001/tcp
npm ci --prefix /uis/website then npm ci --prefix /uis/backoffice (separate)
next build website + backoffice green inside node:22-alpine
container: next start --port 3000 and next start --port 3001 Ready
GET http://127.0.0.1:3000/ → 200 Brasaland — Grilled food, Colombia & Florida
GET http://127.0.0.1:3001/login → 200 Brasaland Backoffice
uis/.dockerignore includes node_modules, .next, .env*, *.log
```

## Latest services Python uv image (`cursor/services-python-uv-dockerfile-2c91`)

Department served: **Technology** (Nicolás Park — containerized central FastAPI).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
docker build -f services/Dockerfile -t brasaland-api . → FROM python:3.11-slim
install uv; RUN uv pip install -r requirements.txt (61 packages)
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
logs: Started reloader process using WatchFiles
GET /docs 200
locations=present menus=present sales=present customers=present suppliers=present inventory=present
path_count=34
uv --version in image → uv 0.12.17
```

## Latest services/.dockerignore (`cursor/services-dockerignore-2c91`)

Department served: **Technology** (backend image must not ship bytecode, secrets, tests, or logs).

```text
head -n 5 CONTEXT.md → # Welcome to Brasaland
services/.dockerignore includes __pycache__, *.pyc, .env*, test/, *.log
```

## Planned next steps (order)

1. Keep every product change traceable to a `CONTEXT.md` department need (name the section in the PR/commit).
2. Wire menus/sales/customers/suppliers into the staff console and keep telemetry/Monday report work on the existing pipeline.
3. Executive path: surface chain sales in **USD and COP**, wire Monday-style weekly report to the existing async pipeline, keep Mariana’s NL assistant on the documented agent loop.
4. Do not rewrite the monorepo or invent another company.

## How to update this file

After a verified change, append evidence (command + result) and update the coverage table. Do not log plans that were not run.
