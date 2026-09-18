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

## Planned next steps (order)

1. Keep every product change traceable to a `CONTEXT.md` department need (name the section in the PR/commit).
2. Extend the central API toward missing Technology nouns: **locations → menus → sales → customers → suppliers**, reusing `services/api` routers.
3. Executive path: surface chain sales in **USD and COP**, wire Monday-style weekly report to the existing async pipeline, keep Mariana’s NL assistant on the documented agent loop.
4. Do not rewrite the monorepo or invent another company.

## How to update this file

After a verified change, append evidence (command + result) and update the coverage table. Do not log plans that were not run.
