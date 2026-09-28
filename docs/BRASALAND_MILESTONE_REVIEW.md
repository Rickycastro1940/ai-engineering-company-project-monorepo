# Brasaland milestone review

Review of Ricardo Chong’s 4Geeks Academy AI Engineering company project against milestones 0–10.

| | |
| --- | --- |
| Repo | `Rickycastro1940/ai-engineering-company-project-monorepo` |
| Company check | **Confirmed Brasaland** |
| Reviewed tree | `main` at `393e8b1` (2026-09-24) |
| Overall readiness | **about 45%** of a finished 0–10 company build |
| Scope | Read-only assessment. No product features were added in this review. |

Ratings mean:

- **Present** — a grader can point at a working deliverable that matches the milestone, and it is connected to Brasaland.
- **Partial** — real Brasaland code exists, but a required piece is missing, unwired, or not runnable from the declared dependencies.
- **Missing** — folder is still the template README, or the milestone behavior is not in the repo.

The percentage uses equal weight across the 11 milestones. Present = 1.0. Missing = 0.05 (template text only). Partial uses the credit in the table. `4.90 / 11 ≈ 45%`.

## Company check

This checkout is the Brasaland assignment, not the four-company template.

- `CONTEXT.md` opens with `# Welcome to Brasaland` and describes the grilled-food chain: founded 2008 in Medellín, **14** company-owned restaurants, Colombia and Florida, about 115 people, about USD 6 million, Brasa Points, Mariana Restrepo.
- `CONTEXT.es.md` is the Spanish briefing.
- `memory-bank/Projectbrief.md`, `memory-bank/Techcontext.md`, and `memory-bank/Progress.md` cite that briefing (COP and USD, Technology nouns, Monday 07:00 report).
- Location seed data is 8 Colombia (COP) and 6 Florida (USD) in `services/api/locations.py`.
- Public copy in `uis/website/src/content/brand.ts` uses the same facts.

`README.md` still says `CONTEXT.md` is a placeholder and that the repo “does not include runnable apps.” That paragraph is stale. The briefing and several apps are already in the tree.

## Milestone table

| # | Milestone | Rating | Credit | Evidence |
| --- | --- | --- | --- | --- |
| 0 | Prework (env, first prompts) | **Partial** | 0.60 | Env and Brasaland context are in place. Saved first prompts are not. |
| 1 | Web (site, forms, SEO) | **Partial** | 0.55 | Corporate home exists. Public forms and real SEO do not. |
| 2 | Programming (logic, scoring, calculations) | **Present** | 0.90 | Incident scoring and weekly cost/waste math are implemented and tested. |
| 3 | AI-driven UI | **Partial** | 0.45 | Three UIs exist. No generation record and no AI-driven screen on the public site. |
| 4 | Next.js portals / loyalty / ops UI | **Partial** | 0.40 | Staff portal is Vite, not Next.js. Loyalty and sales UI are not built. |
| 5 | Backend central API | **Partial** | 0.55 | Locations, inventory, and auth run on one app. Menus, sales, customers, and suppliers do not. |
| 6 | Telemetry / pipeline / dashboards | **Partial** | 0.45 | Pipeline and Celery code exist. They are not on the running API, and the live dashboard is legacy HTML. |
| 7 | RAG and memory | **Partial** | 0.35 | Knowledge docs and Qdrant code exist. The route is not mounted, and two RAG stacks disagree. |
| 8 | Agents | **Partial** | 0.50 | Root inventory agent is a real tool-calling loop. `agents/` has no company agent. |
| 9 | Workflows (n8n) | **Missing** | 0.05 | `workflows/` is the template README only. |
| 10 | Real-time | **Missing** | 0.05 | No live stream, websocket, or no-sales alert. |

Credit sum: **4.90 / 11 ≈ 45%**.

---

### 0 — Prework — Partial

What is here:

- Company context replaced: `CONTEXT.md`, `CONTEXT.es.md`.
- Python project: `pyproject.toml` (`requires-python >= 3.9`), `requirements.txt`, `uv.lock`, `.python-version`, `Dockerfile`.
- Local broker: `docker-compose.yml` (Redis, Flower, Celery worker).
- Agent operating notes: `AGENTS.md`, `.agents/rules/00-operating-loop.md`, `memory-bank/`.
- Env sample: `.env.example` (only `REDIS_URL`).

What is still open:

- No checked-in first-prompt log (no `docs/prompts/`, no prompt transcript).
- `.env.example` does not list `GROQ_API_KEY`, `JWT_SECRET_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `OPENAI_API_KEY`, or `QDRANT_HOST`, even though those are required by `agent.py`, `services/api/users.py`, `data/pipelines/pipeline.py`, and `data/process/rag.py`.
- Root `README.md` “Current status of the template” still claims there is no `AGENTS.md` and no runnable apps. Both claims are false (`AGENTS.md`, `uis/website`, `uis/backoffice`, `agent.py`).

### 1 — Web — Partial

What is here:

- Public site `uis/website/` (React 19, TypeScript, Vite, React Router).
- Single route `/` in `uis/website/src/App.tsx` renders hero, commitments, markets, and a Brasa Points teaser (`uis/website/src/pages/HomePage.tsx`).
- Facts come from `uis/website/src/content/brand.ts` and match `CONTEXT.md`.
- Basic SEO only: `<title>` and `<meta name="description">` in `uis/website/index.html`.
- Screenshot: `docs/screenshots/website-corporate-home.png`.
- Run notes: `uis/website/README.md` (`npm run dev`, default port 5173).

What is still open:

- No public form (contact, reservation, catering, or location finder). Header CTA is an anchor to `#markets` (`uis/website/src/components/SiteHeader.tsx`).
- No `robots.txt`, `sitemap.xml`, Open Graph tags, canonical URL, or structured data.
- One page, English only (`<html lang="en">`). Colombia is the home market.
- `LoyaltyTeaser` correctly says stamp cards are still the real programme. That is honest, and it is not a loyalty site.

Forms that do exist are staff or internal: `uis/backoffice` login/register/profile, and the incident upload form in `uis/web/index.html`. Those do not satisfy the public-website milestone.

### 2 — Programming — Present

This is the strongest milestone.

- Shared analyzer: `services/api/analyzer.py`, `services/api/validator.py`, `services/api/loader.py`.
- Scoring is real: valid vs invalid rows, category counts, satisfaction average on scores 1–5, CSV export (`IncidentAnalyzer.build_summary`).
- CLI: `scripts/analyze.py`. Sample rows: `scripts/incidents-COMPANY.csv` (Brasaland-style ids such as `BRS-000001`).
- Tests: `tests/test_scripts_io.py`.
- Web wrapper: `uis/web/index.html` posts to the API and renders the summary. Screenshot: `docs/screenshots/web-ui-analysis-loaded.png`.
- Second calculation path: weekly purchase cost, waste cost, waste ratio, stockout count, and price-alert count in `data/pipelines/pipeline.py` (`aggregate_location_kpis`). Tests: `tests/pipelines/test_pipeline.py`.

Keep the rating at Present, with one limit: Brasa Points math (10,000 COP or 10 USD = 1 point, tier discounts) is written only in `docs/company-knowledge-base/brasaland-loyalty-program.en.md`. It is not executable business logic.

`services/api/schemas.py` is a separate, unused order model (`ProductCreate`, `OrderCreate`) whose subclasses are `pass`. The live inventory API does not use it.

### 3 — AI-driven UI — Partial

What is here:

- `uis/web/index.html` — incident analysis screen (file input, engine select, summary).
- `uis/website/` — designed corporate page with tokens in `uis/website/src/styles/tokens.css`.
- `uis/backoffice/` — staff screens with loading, error, and retry (`uis/backoffice/src/components/AsyncState.tsx`).
- A knowledge-query component exists at `services/api/uis/pages/knowledge.js`, but it is not part of either Vite app.

What is still open:

- No prompt or generator log that shows these screens were produced as the AI-UI deliverable.
- The public site has no AI panel (no menu assistant, no “ask Brasaland”).
- `knowledge.js` uses TypeScript syntax (`useState<'idle' | ...>`) inside a `.js` file and lives under `services/api/uis/`, so neither website nor backoffice can import it. Its placeholder copy still says “return policy for enterprise tier clients,” which is not Brasaland.

### 4 — Next.js portals / loyalty / ops UI — Partial

`uis/backoffice/README.md` states the fact directly: **there is no Next.js app**. Both frontends are Vite SPAs (`uis/website/package.json`, `uis/backoffice/package.json`). No `next.config.*` anywhere.

What the staff app does have:

- Routes in `uis/backoffice/src/App.tsx`: `/login`, `/register`, `/accessible`, `/account/profile`, `/account/change-password`.
- JWT in `localStorage`, layout guard in `uis/backoffice/src/auth/ProtectedRoute.tsx`.
- `/accessible` loads `GET /locations/overview` and `GET /inventory` (`uis/backoffice/src/pages/AccessiblePage.tsx`).
- Screenshot: `docs/screenshots/backoffice-accessible.png`.

What the milestone still asks for:

- A Next.js portal (App Router or Pages). Vite will not satisfy a Next.js rubric line.
- A Brasa Points / loyalty experience. The public teaser is copy only.
- An operations UI for sales. The executive sales block is labeled placeholder and renders no numbers (`AccessiblePage.tsx`, “Executive sales (placeholder)”).

### 5 — Backend central API — Partial

The documented entry is real: `api/app.py` loads `services/api/app.py`. App title is `Brasaland Central API`.

Mounted on that app:

| Area | Where | Notes |
| --- | --- | --- |
| Locations | `services/api/locations.py` | `GET /locations`, `GET /locations/overview`. Bearer JWT. 14 sites, COP and USD. |
| Inventory | `services/api/inventory.py` | `GET/POST /inventory`, `PATCH /inventory/{id}`, `GET /inventory/alerts`. CSV file `products.csv`. **No JWT.** |
| Users / auth | `services/api/users.py` | Register, login, `/auth/me`, `/profiles/me`, user CRUD. SQLite. Tests in `tests/test_users_api.py`. |
| Incidents | `services/api/app.py` | `POST /api/incidents/analyze` and the typo alias `POST /api/incidents/anylayze`. |

Technology’s list in `CONTEXT.md` is locations, menus, sales, customers, suppliers. In this tree:

- locations: present
- menus: no router
- sales: no router
- customers: no router
- suppliers: no router
- inventory: present, as an operations extra

`memory-bank/Progress.md` already records the same gap.

Other wiring problems on this milestone:

- Reporting is a **second** FastAPI app, `services/reporting/main.py`. `uvicorn api.app:app` does not include `/reporting/*` or `/tasks/{task_id}`.
- `services/api/main.py` imports `api.routers.knowledge`, which does not exist. The knowledge router is `scripts/services/routers/knowledge.py`. Nothing mounts it on the central app.
- `services/api/app.py` mounts `uis/web` at `/`. API routes registered above the mount still work; the site root is the incident HTML page.
- `products.csv` is Tomatoes, Mozzarella, and Napkins. That is not a grill inventory.
- `services/api/database.pycat` and `services/api/models.pycat` are accidental text dumps, not modules.
- A root file named `-R | grep briefing` is a captured `git log` with ANSI codes. It should not be in the repo.

### 6 — Telemetry / data pipeline / dashboards — Partial

What is here:

- Design note for Mariana and Felipe: `data/pipelines/PIPELINE_DESIGN.md` (weekly location cost and waste, COP/USD via location currency).
- Prefect-style flow: `data/pipelines/pipeline.py` (`extract_telemetry_events`, `aggregate_location_kpis`, upsert to `weekly_location_performance`).
- Celery wrapper: `services/tasks.py` (`run_weekly_pipeline`), broker config in `services/celery_app.py`, dead letters in `services/dead_letter.py`.
- HTTP trigger, written on the **other** app: `POST /reporting/pipeline-runs` returns 202, `GET /tasks/{task_id}`, `GET /reporting/weekly-location-performance` in `services/reporting/main.py`.
- Tests that do not need Supabase: `tests/pipelines/test_pipeline.py`, `tests/test_celery_async.py`, `tests/test_async_api_endpoints.py` (the HTTP tests build a fake app).
- Legacy dashboards: `uis/backoffice/legacy/index.html` (weekly KPIs) and `uis/backoffice/legacy/telemetry.html` (engineering traffic/errors).
- Compose file runs Redis, Flower, and the worker. It does not run the API, Supabase, or Qdrant.

What keeps this Partial:

- `prefect`, `supabase`, and `pandas` are imported by the pipeline and are **not** in `requirements.txt` or `pyproject.toml`. `Dockerfile` runs `uv sync` from `pyproject.toml`, so the worker image does not install the ETL stack.
- The engineering telemetry module is filed at `skills/data-analysis/scripts/services/telemetry/main.py`. It imports `services.telemetry.analysis`, and there is no `services/telemetry/` package. Importing that file also raises if `SUPABASE_URL` is unset (client is created at import time).
- The Vite backoffice does not render weekly KPIs. Staff still see the sales placeholder.
- `data/pipelines/last_run.json` records `status: Success` with `records_processed: 0`.
- `data/raw/` and `data/eval/` are README-only. `data/process/` only adds `rag.py`.
- The design doc and the code disagree: the doc names events like `ingredient_purchased` and table `reporting.weekly_location_metrics`; the code queries `inbound_order_created` and upserts `weekly_location_performance`. The Mermaid block in `PIPELINE_DESIGN.md` is cut off mid-diagram by “Phase 3” prose.

### 7 — RAG and memory — Partial

What is here:

- Four English source docs in `docs/company-knowledge-base/`: loyalty, supplier ordering, waste protocol, menu allergens.
- Indexer: `data/process/rag.py` embeds with `text-embedding-3-small` and upserts collection `brasaland_kb`.
- Query function: `data/pipelines/rag.py` (`retrieve` / `query`, floor score 0.40, Brasaland system prompt).
- A second query function: `scripts/rag.py` (collection `company_knowledge_base`, floor 0.70, “commercial team” prompt).
- Router: `scripts/services/routers/knowledge.py` → `POST /knowledge/query`, calling `data.pipelines.rag.query`.
- Project memory for coding agents: `memory-bank/`. That is repo context, not guest or staff retrieval memory.
- The inventory agent appends turns to `conversation_log.csv` (gitignored at runtime). That is a log, not a memory store the model searches.

What keeps this Partial:

- `uvicorn api.app:app` never exposes `/knowledge/query`.
- `qdrant-client` and a guaranteed OpenAI client are not in `requirements.txt` / `pyproject.toml`. `openai` is only in `requirements.txt`.
- The two RAG modules do not share a collection name, so indexing with `data/process/rag.py` does not fill the collection `scripts/rag.py` searches.
- `services/api/uis/pages/tests/pipelines/test_rag.py` is outside `tests/`, calls `@patch` and `MagicMock` without importing them, and expects `scripts/rag.py` behavior (`_score`, `min_score=0.70`, `llm_client`) while importing `data.pipelines.rag`.
- `data/eval/` has no golden questions.
- The loyalty doc says a digital app already exists. `CONTEXT.md` says Brasa Points is physical stamp cards. Retrieval will answer with the doc, not the briefing.

### 8 — Agents — Partial

What is here:

- `agent.py` at the repo root: manual observe → think → act → update loop, Groq via the OpenAI-compatible client, no LangChain.
- Tools: `list_inventory`, `add_product`, `update_stock`, `get_low_stock_alerts`, mapped to the inventory API.
- Startup check that `http://127.0.0.1:8000` is up. Documented in `README.md` and `services/api/README.md` (evaluation checklist, 10 rubric rows).
- Skill for API coverage: `.agents/skills/verify-brasaland-api/SKILL.md`.
- Small pandas helpers: `skills/data-analysis/scripts/pandas_clean.py`.

What the milestone still asks for (support, onboarding, training agents, tools via MCP):

- `agents/` contains `_template/agent.py` (empty file) and READMEs only. No `support-agent/`, `onboarding-agent/`, or training agent.
- `agents/tools/` is a README.
- `mcps/` is a README. No MCP server.
- `skills/code-review/` and `skills/research/` are `.gitkeep` only. `skills/_template/SKILL.md` is empty.
- The agent prompt says “a restaurant company” and never names Brasaland, recipes, or the 14 locations.
- Because `/inventory` has no auth dependency, the agent can ignore the JWT work on locations. That split should be an explicit decision, not an accident.

### 9 — Workflows (n8n) — Missing

`workflows/README.md` and `workflows/README.es.md` are the template. There is no `.json` export, no n8n workflow, no Monday 07:00 schedule, and no diagram that operations could import.

Celery (`services/tasks.py`) is a queue, not an n8n workflow. It can be the worker an n8n flow calls. It does not replace the milestone artifact.

Executive need from `CONTEXT.md`: an automated weekly report every Monday at 07:00. Nothing in the repo sends that report.

### 10 — Real-time — Missing

No websocket route, no Server-Sent Events, no Supabase Realtime subscription in `uis/`, and no alert when a location has no sales during opening hours.

Nearby pieces that are **not** this milestone:

- Celery status polling (`GET /tasks/{task_id}`) is request/response after the fact.
- `pipeline.py` reads stored events in a weekly batch.
- Root `package.json` depends on `@supabase/supabase-js`, which pulls in `realtime-js`. No application code subscribes to a channel.

`CONTEXT.md` Operations still cannot see covers today, and Executive still cannot answer “how much did we sell this week in Florida?” from a live screen.

---

## Quality skim

### What is solid

- Brasaland identity is consistent across the briefing, location seed, website copy, and memory bank.
- Incident analysis is a complete small system: CLI, shared library, API, static UI, tests, screenshots.
- Staff auth is a complete small system: hash + JWT, protected locations, profile and password pages, tests, three-state loading UI.
- Error handling is unusually careful for this stage: `services/api/errors.py`, `services/safe_errors.py`, `tests/test_error_handling.py`, `docs/error-handling-audit.md`.
- The inventory agent matches a written rubric (`services/api/README.md` evaluation checklist) and stays on a plain Python loop.

### Stubs, empty areas, and misplaced files

| Path | Issue |
| --- | --- |
| `workflows/`, `mcps/`, `infra/`, `internal/`, `shared/` | Template README only. |
| `data/raw/`, `data/eval/` | Template README only. |
| `agents/_template/agent.py`, `skills/_template/SKILL.md` | Empty. |
| `skills/code-review/`, `skills/research/` | `.gitkeep` only. |
| `packages/shared/types/index.ts` | Placeholder `Id` / `BaseEntity`. Root `package.json` is not a workspace; it only lists Supabase packages. |
| `services/api/schemas.py` | Models that `pass`, unused by the live inventory routes. |
| `services/api/database.pycat`, `services/api/models.pycat` | Not Python modules. |
| `-R \| grep briefing` (repo root) | Accidental `git log` capture. |
| `services/api/uis/pages/` | UI, a RAG test, and a design note parked inside the API package. |
| `skills/data-analysis/scripts/services/telemetry/main.py` | API module under a skill path; import target missing. |
| `services/api/main.py` | Broken import `api.routers.knowledge`. |
| `uis/backoffice/src/pages/AccessiblePage.tsx` | Executive sales panel is a placeholder. |

### Can it run?

| Surface | Verdict |
| --- | --- |
| Incident CLI and analyzer tests | Should run after `pip install -r requirements.txt` (pandas is listed). Not re-executed for this review. No `.venv` is present in this checkout. |
| `uvicorn api.app:app` | Documented and structured so it can boot: locations, inventory, users, incident routes. Needs `JWT_SECRET_KEY` for stable tokens. |
| `uis/website`, `uis/backoffice` | Each has `package.json` scripts (`dev`, `build`). `node_modules` is not installed inside those apps. |
| `python agent.py` | Needs the API up and `GROQ_API_KEY`. |
| `docker compose up` worker | Image build uses `uv sync` from `pyproject.toml`, which does not list pandas, prefect, supabase, openai, or qdrant. The weekly task will fail at import inside the container. |
| Weekly pipeline against Supabase | No Supabase project, migration, or seed events in the repo. `last_run.json` shows a run that processed 0 rows. |
| RAG query | Not mounted, and Qdrant/OpenAI are not fully declared. |
| n8n / live dashboard | Nothing to start. |

### Docs

- Folder READMEs are bilingual and still useful as a map.
- The useful project docs are `memory-bank/`, `services/api/README.md`, `services/api/LOCATIONS.md`, `data/pipelines/PIPELINE_DESIGN.md`, `uis/website/README.md`, `uis/backoffice/README.md`, and `docs/error-handling-audit.md`.
- Root `README.md` contradicts the tree (placeholder context, “no apps”).
- `PIPELINE_DESIGN.md` contradicts `pipeline.py` on event names and the destination table.
- `docs/company-knowledge-base/brasaland-loyalty-program.en.md` contradicts `CONTEXT.md` on whether a digital loyalty app exists.

### Obvious wiring bugs

1. Three FastAPI entry points (`services/api/app.py`, `services/api/main.py`, `services/reporting/main.py`). Only the first is what `api/app.py` loads.
2. Knowledge router and reporting routes are invisible on the documented server.
3. Two RAG collection names (`brasaland_kb` vs `company_knowledge_base`).
4. RAG test file does not match the module it imports, and it is not under `tests/`.
5. Telemetry dashboard calls code that is not a package (`services.telemetry`).
6. `services/reporting/main.py` mounts `uis/backoffice` as static files. That directory is a Vite source tree, not a built site.
7. Public typo route `/api/incidents/anylayze` is still registered (an `/analyze` alias exists beside it).
8. Locations require JWT; inventory does not. The agent and the staff UI therefore follow different security rules.

---

## How to read the 45%

Early coursework is real and would survive a demo: incident scoring, corporate home page, JWT staff shell, location roster, CSV inventory, and a Groq inventory agent.

The second half of the programme is not submission-complete. Menus, sales, customers, and suppliers are absent. The pipeline and RAG code are not on the server a grader is told to start. Next.js, n8n, and real-time behavior are not in the tree. Loyalty is a paragraph. Executive sales is a placeholder.

Do not describe the central API as finished while those four nouns are missing. `memory-bank/Progress.md` already says this. The milestone table above agrees.

## Top 5 next actions

Ordered by how much they move a 4Geeks submission forward.

### 1. Finish the central API on the one app graders already start

Add routers for **menus, sales, customers, and suppliers** under `services/api/`, and `include_router` them from `services/api/app.py` (the module `api/app.py` loads).

Minimum shape that matches `CONTEXT.md`:

- Menu items with price in COP or USD and a location or market.
- Sales records per location (amount, currency, timestamp) so Florida vs Colombia can be totaled.
- Customers (the people behind Brasa Points).
- Suppliers (about 20, split across the two markets) with a price field Lucía can history later.

In the same change, mount the existing reporting routes and `POST /knowledge/query` on this app, or delete the extra entry points so there is one server. Re-run `.agents/skills/verify-brasaland-api` and update the coverage table in `memory-bank/Progress.md`.

This is first because milestones 4, 6, and 10 all need sales, and Technology’s milestone is explicitly these nouns.

### 2. Put loyalty and operations in a Next.js portal

Add a Next.js app under `uis/` (do not invent a new top-level folder). Move the staff session there, then add two screens the Vite app does not have:

- Brasa Points: balance, tier, and the earn/redeem rules from `docs/company-knowledge-base/brasaland-loyalty-program.en.md`, calculated in code.
- Operations: chain and per-location sales in **COP and USD**, replacing the placeholder in `AccessiblePage.tsx`.

Keep `uis/website` as the public marketing site. Keep `uis/web` as the incident tool. Say in that app’s README which `CONTEXT.md` department each route serves (Marketing vs Operations vs Executive).

Milestone 4 is named Next.js. A polished Vite backoffice will still be marked incomplete.

### 3. Make RAG one path and prove it with a golden set

Pick one stack and delete or re-export the other:

- Index only `docs/company-knowledge-base/*.md` into one collection.
- Serve it only through `POST /knowledge/query` on `api.app:app`.
- Add `qdrant-client` (and the embedding client you actually call) to `requirements.txt` and `pyproject.toml`.
- Add 8–10 question/answer pairs under `data/eval/` drawn from those four docs (allergens, waste, suppliers, points).
- Fix or replace `services/api/uis/pages/tests/pipelines/test_rag.py`, and move the UI into `uis/backoffice` so a staff user can ask a question.

Align the loyalty doc with `CONTEXT.md` before indexing it, or the assistant will claim a digital app that the briefing says does not exist.

### 4. Export one n8n workflow for Monday 07:00

Add a real export under `workflows/` (JSON plus a short README: trigger, credentials, failure path).

Flow to build, because the pieces already exist:

1. Schedule: Monday 07:00 America/Bogota.
2. HTTP: `POST /reporting/pipeline-runs` for the previous week.
3. Poll `GET /tasks/{task_id}` until success or failure.
4. HTTP: `GET /reporting/weekly-location-performance`.
5. Format totals in COP and USD and send them to Mariana (email or Slack).

Celery can remain the worker. The milestone artifact is the n8n export. Wire the pipeline dependencies (`supabase`, `pandas`, and whatever orchestration library you keep) into `pyproject.toml` first, or the worker container will not run step 2.

### 5. Ship one live operations alert

After sales exist (action 1), add a real-time channel on the same API: websocket or SSE is enough. Push a location event when sales are recorded, and raise an alert if a location that should be open has **no sales** in the current window (Operations, Felipe Guerrero, in `CONTEXT.md`).

Show that feed on the Next.js operations screen (action 2), not only in `uis/backoffice/legacy/`. One location going quiet during open hours is the demo. A full streaming platform is not required for this step.

---

## Suggested order of work

1. One FastAPI app with menus, sales, customers, suppliers, plus the reporting and knowledge routes.
2. Next.js loyalty + COP/USD sales screens on top of those routes.
3. Single RAG path, mounted, with a golden file in `data/eval/`.
4. n8n Monday report export in `workflows/`.
5. Live no-sales alert on the operations screen.

That sequence turns the current 45% into a coherent Brasaland Digital demo: the same 14 locations, two currencies, and one API, instead of more side scripts.
