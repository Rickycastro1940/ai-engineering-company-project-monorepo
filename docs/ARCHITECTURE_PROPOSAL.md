# Brasaland backend architecture proposal

**Audience:** Nicolás Park, CTO, Medellín. This document is the architecture decision for Brasaland Digital. It is a reasoning document. It does not add routes or change a running process.

**Company facts that constrain the design** come from `CONTEXT.md`:

- Grilled-food chain founded in Medellín in 2008. About 115 people. About USD 6 million a year.
- **14 company-owned** restaurants. Eight in Colombia, six in Florida. Headquarters in Medellín. A Miami office coordinates Florida. These are not franchises, so headquarters can impose one system of record.
- Two point-of-sale installations, two currencies (**COP** and **USD**), two labour markets, and two languages (Spanish and English).
- The brand promise is that a dish tastes and looks the same in Medellín and Miami.
- Technology today is a static site, an outdated app, country-specific POS terminals, and spreadsheets. There is no internal API and no consolidated telemetry.
- The technology team is small and based in Medellín. The architecture has to be operable by that team.

Department needs the structure must be able to absorb, without a new service per need:

| Owner | Need the structure has to carry |
| --- | --- |
| Felipe Guerrero, Restaurant Operations | Sales per location in COP and USD, stock-aware ordering, an alert when an open location records no sales |
| Lucía Fernández, Procurement | About 20 suppliers, price history, consolidated purchasing across both markets |
| Camila Ospina, Marketing | A customer record and Brasa Points. Today the programme is a physical stamp card |
| Ashley Turner, People (Miami) | Holiday, absence, onboarding, and HR KPIs split by country |
| Jake Morrison, Training (Miami) | One recipe standard, searchable, later pushed to all 14 kitchens |
| Nicolás Park, Technology | One central API for locations, menus, sales, customers, and suppliers; telemetry; a pipeline into operations, marketing, and finance |
| Mariana Restrepo, Executive | Chain sales in USD and COP, a natural-language question, a report every Monday at 07:00 America/Bogota |

---

## 1. Decision

**Pattern: a layered modular monolith.** One HTTP service is the system of record. Inside it, layers separate kinds of work, and modules separate business nouns. Batch and delivery run as separate processes that call the same rules. They are not separate products.

The five nouns Nicolás was asked for — locations, menus, sales, customers, suppliers — share one consistency boundary. A sale is Felipe’s ticket, a line in Mariana’s chain total, and a future earn event for Camila’s stamp card. Splitting that fact across services would make the chain total and the kitchen alert disagree. Keeping it in one process makes the disagreement a bug in one codebase, which a small team can fix.

---

## 2. Architectural pattern

### What “layered modular monolith” means here

| Idea | Meaning for Brasaland |
| --- | --- |
| Monolith | One deployable API process. One roster of 14 locations. One rule that a Colombia ticket is COP and a Florida ticket is USD. |
| Modular | Each noun is a module with one department owner. A change to supplier price history does not require editing the menu module. |
| Layered | HTTP, domain rules, long-running jobs, and storage have different latency and failure behaviour, so they stay in different layers. |

| Layer | Responsibility | What belongs here | What must stay out |
| --- | --- | --- | --- |
| Interface | Translate HTTP into a domain call and an HTTP status | Routers, auth dependencies, OpenAPI models, error envelopes | Weekly KPI arithmetic, POS protocol details |
| Domain | Invariants the company will hold even if the database changes | Closed set of location ids, currency must match the location, Brasa Points remain a stamp-card balance until a ledger exists, chain week bounds | SQL, React, cron syntax |
| Jobs | Work that is too slow or too scheduled for a request | Weekly cost/waste rollup, nightly telemetry copy, Monday 07:00 delivery | Ad-hoc queries typed by a manager |
| Data | Durable state | Postgres for events and reporting, a staff user store, the stock file, Redis as the queue broker | Business decisions such as “is this kitchen quiet?” |

A module is a vertical slice through those layers for one noun. The sales module owns the ticket schema in the interface layer and the currency invariant in the domain layer. The weekly job reads sales and purchase events. It does not redefine what a ticket is.

### Why this pattern matches this company

Four properties of Brasaland make the pattern, rather than a generic preference for monoliths.

**The nouns are coupled by the questions leadership actually asks.** “How much did Florida sell this week?” joins sales to the location roster and to a timezone. “Which kitchen was quiet during service?” joins the same sales to opening hours. “What did we pay for meat?” joins suppliers to purchase events at those locations. A modular monolith lets those joins stay in-process. A distributed join across five department APIs would be the first thing a two-person team gets wrong.

**The company is company-owned and centrally led.** Mariana can require every location to post tickets to one API. Franchise architectures often put a database in each store because the franchisor does not control the operator. That constraint is absent here. The remaining distribution is physical (14 kitchens, two POS vendors), and it is handled by adapters that write into the monolith, not by fourteen databases.

**The team cannot staff a platform.** Nicolás’s group is small and sits in one city, while Ashley and Jake sit in Miami. Every extra deployable service is an extra thing that must be logged, migrated, and kept on the same location id. Workers (a queue consumer, a Sunday-night cron, an n8n delivery) are justified because their failure mode is different from a request. A Procurement API beside an Operations API is not, because their failure mode is the same and their data is the same roster.

**The dangerous work is slow, and the user-facing work is not.** Mariana’s Monday report aggregates a week of purchase, waste, stockout, and price-alert events. That job can run for longer than a staff login should wait. The layer split exists so the report is computed ahead of the click. The modular split exists so the report reads a sales fact it does not own.

### Patterns considered and rejected

| Pattern | Where it is a good fit | Why it fails this company |
| --- | --- | --- |
| Classic MVC | One server renders HTML for one product | The staff console, the public site, and the guest points page are already separate clients. An MVC `views/` layer would put Camila’s page template in the same process as the currency rule and would still not serve the other two clients. The “model” and the rules belong in the API. The “view” belongs in `uis/`. There is no shared controller. |
| Layered architecture without modules | A single small application with one database | Layers alone do not stop a sale, a supplier price, and an HR absence landing in one module. Brasaland’s failure today is that everything already lives in shared spreadsheets. Layers without domain modules recreate that spreadsheet inside `app.py`. |
| Serverless, one function per route | Spiky, stateless HTTP with no long-lived connections | Felipe’s no-sales alert is a stream that stays open for a service period (11:00–22:00 in the location’s timezone). The nightly job needs a lock so two runs do not write the same location-week twice. Copying the 14-location roster and the COP/USD check into every function’s environment is how those invariants drift. |
| Microservices, one service per department | Independent teams that deploy on different schedules and can tolerate eventual consistency | The departments are not independent. Lucía’s price, Felipe’s stockout, and Mariana’s Monday number are one chain week. Eventual consistency between them is the Tuesday PDF problem the project exists to end. |
| A second repository for the API | A backend team that does not share reviews with the UI team | Field names (`location_id`, `currency`, `brasa_points_balance`) change together with the screens that show them. A second repo delays that review by a release. Separate **processes** still give independent restarts. See section 6. |

Workers stay outside the request process. That is a process boundary, not a service boundary. The Celery worker, the Prefect flow, the OS cron, and n8n are clients or runners of the same domain. They do not publish a second public contract.

---

## 3. Folder and module structure

### Separation criteria

A file boundary is justified only when it matches one of these cuts. A boundary that matches none of them is a folder for its own sake.

| Criterion | Question that forces the cut | Consequence when the cut is ignored |
| --- | --- | --- |
| Domain owner | Which `CONTEXT.md` lead is accountable for the rule? | A menu allergen edit and a staff password edit share a diff, and a reviewer cannot tell whose invariant broke. |
| Consistency | Which facts must commit together? | Sales and locations share a database and a process. Reporting rows are derived and can lag. Mixing them in one table makes a late event rewrite a ticket. |
| Runtime | Does this finish inside one HTTP request? | Weekly aggregation inside the request that draws the dashboard makes Monday logins wait on the heaviest query of the week. |
| Trust | Who is allowed to call it, and from which network? | A public menu and a staff customer list on one router either hide the menu behind a login or expose the CRM. |
| Change rate | Do these files change for the same reason? | The recipe text changes when Jake updates a standard. The ticket schema changes when a POS adapter is added. Those are different releases. |

### Backend layout this proposal commits to

The monorepo already separates products by top-level folder (`services/`, `data/`, `uis/`, `workflows/`). The backend project lives under `services/` and `data/`. Creating a new top-level application would split the company in two inside the same git history.

```text
api/app.py                      # process entry: uvicorn api.app:app loads the app below
services/
  api/
    app.py                      # composition root only: construct FastAPI, CORS, errors, include_router
    core/                       # target home for settings, JWT, error envelope (shared by every module)
    locations.py                # one module per noun until that noun gains a real database
    menus.py
    sales.py
    customers.py
    suppliers.py
    inventory.py
    users.py
    auth.py
    no_sales.py                 # domain rule: quiet location during opening hours
    no_sales_router.py          # interface for that rule; path stays /realtime, not /sales
  reporting/                    # interface over a derived table; no KPI math in the route
  knowledge/                    # interface for standards search
  celery_app.py                 # queue process
  tasks.py
  job_runner.py                 # status rows for jobs that are not HTTP
data/
  process/                      # pure functions. Tests call them without a server
  pipelines/                    # orchestration and the reporting DDL
  raw/                          # optional landing copies, not the source of truth
  eval/                         # hand-calculated expectations for the 14 location ids
```

**Why one file per noun for now.** A common FastAPI layout splits each area into `router.py`, `schemas.py`, `models.py`, and `crud.py` on day one. That split pays off when there is a real persistence boundary. The five nouns are still a seeded contract. Splitting each into four files before there is SQL creates a repository that only returns a list, and the invariant (currency matches the location) becomes harder to find. The proposal keeps schema and route together in the noun module until the move to Postgres. At that moment the noun becomes a package:

```text
services/api/sales/
  router.py        # HTTP only
  schemas.py       # the JSON contract clients already call
  service.py       # currency check, location check, call to the no-sales rule
  repository.py    # the only file allowed to write the sales table
```

The HTTP contract stays put. The new file exists because a new boundary exists, not because a template had the file.

**Why `data/process/` is not inside `services/api/`.** The weekly numbers must be testable with a table of events and no network. If the transform imports FastAPI, every test boots a web app and the formula for waste ratio hides behind a request. The pipeline may import the pure function. The pure function may not import the pipeline or the router. That dependency direction is the layer rule made visible in imports.

**Why reporting is a package and sales is a module.** Sales is a noun in the system of record. The weekly table is a derived read model (one row per location per chain week, costs left in the location currency). Giving it a `/sales` prefix would tell clients that a ticket and a week rollup have the same freshness and the same writer. They do not.

### What each existing area is accountable for

| Path | Accountable rule |
| --- | --- |
| `services/api/locations.py` | The closed roster. Every other module borrows ids from here. Eight Colombia/COP sites, six Florida/USD sites. |
| `services/api/menus.py` | One catalogue for every kitchen. Prices published in both COP and USD. Public read, because the brand card is not a staff secret. |
| `services/api/sales.py` | A ticket is an amount in the location’s own currency. Chain totals may display both currencies. The display conversion is labeled illustrative (4,000 COP per USD) and is not a treasury rate. |
| `services/api/customers.py` | Identity, order history, and a stamp-card balance. `digital_loyalty` stays false until a ledger exists. Tiers: Bronze 0–19, Silver 20–49, Gold 50+. One point per 10,000 COP or 10 USD. |
| `services/api/suppliers.py` | About 20 suppliers, two markets, price history, a price-alert flag. Invoices are a later write on this module. |
| `services/api/inventory.py` | On-hand stock for kitchens. Live rows are `products.csv`. |
| `services/reporting/` | Read and trigger `reporting.weekly_location_performance`. The route returns 202 when it starts a run, because the run is a job. |
| `services/knowledge/` | Answers limited to the company standards (allergens, waste, ordering, Brasa Points), with citations. |
| `services/api/no_sales.py` | During 11:00–22:00 local, a location with sale history and a long enough quiet stretch is an operations alert. No history means no alert, so the chain does not page all 14 sites before a POS exists. |
| `uis/website` | Public corporate site. |
| `uis/backoffice` | Staff session, locations, stock, Monday report, live alert. |
| `uis/portal` | Guest points lookup and operations sales. |
| `uis/web` | Incident HTML only. It is not the marketing site. |

People’s HR portal is a future module on this app (`/people`), scoped by country, because Colombia and Florida labour rules differ and Ashley’s KPIs are explicitly by country. It does not justify a second API.

---

## 4. FastAPI endpoints and routers

### How routes are grouped

Routers follow the domain cut in section 3, expressed the way FastAPI expects: one `APIRouter` per module, a path prefix, an OpenAPI tag, and dependencies that apply to every route on that router.

| Grouping rule | Reason |
| --- | --- |
| Prefix is the noun (`/sales`, `/suppliers`), not the department (`/operations`, `/procurement`) | A sale is read by Felipe, Mariana, and later Camila. A department prefix would assign an owner the data does not have and would force a second route when the next department needs the same fact. |
| One router, one tag | `/docs` is the map Nicolás hands a new developer. If the tag is “default”, the five nouns Technology asked for are invisible. |
| Auth is declared on the router | The security policy is a property of the noun. Menus are public. Sales, customers, suppliers, locations, reporting, and the live alert require a staff Bearer token. Putting `Depends` on each function invites one new route to forget it. |
| `app.py` only composes | The composition root calls `include_router`. Route bodies live in the noun module. A reviewer can open the sales module and see every ticket route. |
| A derived model gets its own prefix | `/reporting/weekly-location-performance` is a week grain. `/realtime/ops-alerts` is a stream. Neither is a sale, so neither sits under `/sales`. |
| Writes of a noun stay on that noun’s router | `POST /sales` records the ticket and then notifies the quiet-location rule. The realtime module does not accept a raw ticket body. One writer of the ticket schema remains. |

### Routes by domain

These are the routes the grouping produces. The table is the contract. It is not an implementation task in this document.

| Domain | Auth | Routes | Why this group |
| --- | --- | --- | --- |
| Menus | Public | `GET /menus`, `GET /menus/catalogue`, `GET /menus/{item_id}` | Same card in every kitchen and on the public site. Training’s later publish (`POST /menus/{item_id}/publications`) joins this router because it changes the same catalogue. |
| Locations | Bearer | `GET /locations`, `GET /locations/overview` | The roster every other domain cites. |
| Sales | Bearer | `GET /sales`, `GET /sales/overview`, `GET /sales/alerts`, `GET /sales/locations/{location_id}`, `GET /sales/{sale_id}`, `POST /sales` | Tickets and the chain totals in COP and USD. `POST` rejects a currency that is not the location’s own. |
| Customers | Bearer | `GET /customers`, `GET /customers/overview`, `GET /customers/{customer_id}` | CRM and stamp-card balance. A later `POST /customers/{id}/loyalty/earn` joins this router only when `digital_loyalty` can be true. |
| Suppliers | Bearer | `GET /suppliers`, `GET /suppliers/overview`, `GET /suppliers/{supplier_id}` | Price history and alerts. A later invoice write uses `/suppliers/{id}/invoices` on this same router. |
| Inventory | Bearer | `GET /inventory`, `POST /inventory`, `PATCH /inventory/{product_id}`, `GET /inventory/alerts` | Kitchen stock. The inventory assistant calls only this group. |
| Reporting | Bearer | `GET /reporting/weekly-location-performance`, `POST /reporting/pipeline-runs`, `GET /reporting/pipeline-runs/latest`, `GET /tasks/{task_id}` | Derived week rows. `POST` returns 202 and a `task_id` because the work is a job. |
| Knowledge | Mounted on the central app | `POST /knowledge/query` | Standards search for Jake. It is not the executive sales assistant. |
| Realtime | Bearer | `GET /realtime/ops-alerts`, `GET /realtime/ops-alerts/stream`, `POST /realtime/ops-alerts/simulate` | Server-sent events for a quiet location. The simulate route exists so the rule can be shown without a live POS. |
| Identity | Public login, Bearer thereafter | `POST /auth/register`, `POST /auth/login`, `POST /auth/token`, `GET /auth/me`, `PUT /profiles/me` | Staff sessions. n8n uses the same login. |
| People (later) | Bearer, country-scoped | `GET /people/kpis?country=` | Ashley’s KPIs. Same app, new module, because the roster and the staff directory are already here. |
| Procurement suggestion (later) | Bearer | `POST /procurement/suggested-orders` | Uses sales history and stock. Its own prefix, because a suggestion is not a supplier master record and not a ticket. |

Unknown ids return 404. A missing token returns 401. Validation errors return 422. Unexpected failures return a JSON envelope (`status`, `code`, `message`, `detail`) with no traceback and no connection string. That envelope is part of the interface layer so every module fails the same way.

---

## 5. How a standard FastAPI project shapes this decision

Source: FastAPI’s own guide, [Bigger Applications — Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/). That page is the structure this proposal is checked against. It shows a single package, not one file of routes:

```text
app/
  main.py                 # creates FastAPI() and include_router(...) only
  dependencies.py         # shared Depends callables (common auth, common query params)
  routers/
    items.py              # APIRouter(); paths for one area
    users.py              # another APIRouter(); its own paths
  internal/
    admin.py              # a router included with a prefix and extra dependencies
```

The same page states the conventions this proposal treats as required:

- Path operations for one area live in a module that builds an `APIRouter`.
- `main.py` imports those routers and mounts them with `include_router`.
- A router may carry a `prefix`, `tags`, and `dependencies` so every route in that area shares them.
- The same router can be included more than once under different prefixes.
- Shared request dependencies live in `dependencies.py`, not copied into each route.

Those conventions are present in the layout in section 3, under the names this monorepo already uses:

| Convention from the FastAPI guide | Where it sits in this proposal |
| --- | --- |
| `app/main.py` only builds the app and includes routers | `services/api/app.py`. `api/app.py` only loads that module so `uvicorn api.app:app` stays the process entry. |
| `app/routers/<area>.py` as an `APIRouter` | `services/api/locations.py`, `menus.py`, `sales.py`, `customers.py`, `suppliers.py`, `inventory.py`, `users.py`, plus `services/reporting/` and `services/knowledge/`. One module per domain. Routes are not declared in the factory. |
| `prefix`, `tags`, and router-level `dependencies` | Each noun router sets its prefix and OpenAPI tag. Staff nouns set `Depends(get_current_user)` on the router. Menus omit that dependency because the card is public. |
| `dependencies.py` for shared dependencies | `services/api/auth.py` is that module: token decode and the current-user dependency. `services/api/core/` is the place settings join it, so a missing `JWT_SECRET_KEY` fails at startup instead of minting a new secret on every boot. |
| `internal/` included with an extra prefix and extra dependencies | `services/reporting/` is the internal read model. It is mounted under `/reporting` with the same staff dependency, separate from the public menu router. |

The guide’s directory is named `app/` because the tutorial is a single project. This repository is a monorepo whose backend root is already `services/`. Copying an `app/routers` tree beside `services/api` would create a second composition root. The conventions move. The tutorial folder name does not.

Pydantic models sit in the same module as their router. The guide generates OpenAPI from those models, and that is the contract the website and the staff console call. A later split into `schemas.py` and a persistence file happens when a noun gains a table, as drawn under `services/api/sales/` in section 3. Doing that split while the store is still a list would add files the guide does not require.

---

## 6. Frontend and backend as separate systems

### What “separate” has to mean

Three arrangements are commonly used when a browser app and an API both exist.

| Arrangement | What teams gain | What Brasaland would lose |
| --- | --- | --- |
| One process serves HTML and JSON | No CORS, no token hand-off | The public site, the staff console, and the guest portal could not ship on different cadences. A marketing change would redeploy the API that holds staff passwords. |
| A repository per application | Independent permissions and pipelines | `location_id`, `currency`, and `brasa_points_balance` would change in the API repo and be noticed in the UI repo a release later. The company already loses facts between spreadsheets. A second repo recreates that gap in git. |
| One repository, separate processes (this proposal) | A contract change is reviewed with the screens it affects. Each app still starts, stops, and deploys on its own. | Shared CI and a discipline that `uis/` does not import Python. That discipline is cheaper than a cross-repo release. |

The third row is the fit. Headquarters is one technology team, not a platform org with a separate frontend department. The clients are still separate programs:

| Program | Stack | Dev origin | Relationship to the API |
| --- | --- | --- | --- |
| Central API | FastAPI | `http://127.0.0.1:8000` | System of record. JSON and one server-sent event stream. |
| `uis/website` | Vite, React | `http://localhost:5173` | Public pages. The only browser caller that should use a public route (`GET /menus`). |
| `uis/backoffice` | Vite, React | `http://localhost:5174` | Staff tools. The dev server proxies API prefixes to port 8000 so the browser talks to its own origin during development. |
| `uis/portal` | Next.js | `http://localhost:3000` | Guest points and operations sales. Live mode calls the API from the Next.js server, not from the guest’s browser. |
| n8n, `agent.py` | Workflow runner, CLI | Outside the browser | HTTP clients. They use the same routes as the staff UI. |

### API communication

- Reads and writes are JSON over HTTP. The OpenAPI document is the shared contract. Clients do not share Python types with the server, because they are not the same language runtime.
- Staff calls send `Authorization: Bearer`. The token comes from `POST /auth/login`.
- The quiet-location banner is server-to-client only, so it is a long-lived HTTP response (server-sent events), not a second socket protocol. The browser `EventSource` API cannot set an `Authorization` header, so the staff console uses `fetch` and reads the stream. That is a constraint of the browser, and it is why the realtime route still accepts the same Bearer token as the rest of the staff API.
- The portal, when pointed at the live API, fetches customers and sales upstream. If the upstream call fails, it shows fixtures and says so. It does not re-grade loyalty tiers. The tier rule lives with the customer noun. A second implementation in the portal would let a guest see Silver while the CRM still has Bronze.

### Environment variables

Separate processes mean separate configuration. The rule is: a secret is read by the process that must use it, and a bundler must not be able to inline it into JavaScript.

| Variable | Read by | Why it is not shared with the browser |
| --- | --- | --- |
| `JWT_SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `GROQ_API_KEY`, Supabase keys | API, worker, cron | Signing keys and database URLs in a JavaScript bundle are public. |
| `VITE_API_PROXY` | Backoffice dev server only | Names the proxy target (`http://127.0.0.1:8000`). It is not a credential. Vite exposes only `VITE_`-prefixed values to client code, so this name must stay a dev-server setting. |
| `BRASALAND_API_BASE_URL`, `BRASALAND_API_TOKEN`, `BRASALAND_DATA_SOURCE` | Portal server | The token is a staff JWT used to read CRM rows for a guest lookup. Next.js inlines `NEXT_PUBLIC_` values into the browser bundle. The token therefore uses the server name, not the public alias. |
| `BRASALAND_STAFF_EMAIL`, `BRASALAND_STAFF_PASSWORD` | n8n at run time | The exported workflow stores the variable names. It does not store the password. |

Root `.env` is gitignored. The API does not read Vite or Next configuration. Each process failing to start when its own required variable is missing is preferable to a process that starts and serves an empty chain.

### CORS

Cross-origin resource sharing is enforced by browsers, not by server-to-server callers. It matters for the website and the backoffice if they call port 8000 from another origin. It does not matter for the portal’s server-side fetch, for n8n, or for `agent.py`.

The API allow-list names the website origins (`http://localhost:5173`, `http://127.0.0.1:5173`) and the backoffice origins (port 5174), with credentials enabled so a browser can send the staff cookie or authorization header the apps use. A wildcard origin combined with credentials would let any site a manager has open read staff JSON. A new `uis/` app that calls the API from the browser is added to the allow-list by origin. It does not get a wildcard.

The backoffice dev proxy makes the browser’s requests same-origin in local development, which hides CORS until production. The allow-list still has to exist, because production will not be a Vite proxy.

---

## 7. Risks and points of attention

These are failures that follow from leaving the structure, not from ordinary bugs inside it.

**1. A second API per department copies the roster and the currency rule.** If People, Procurement, or Marketing start their own FastAPI app, each app will grow its own list of kitchens. A Florida ticket can be stored as COP in one of them, or the same kitchen can be `us-mia-downtown` in sales and `miami-downtown` in purchasing. Mariana’s chain total and Felipe’s quiet-location alert then answer different questions with the same words. The structure prevents that by keeping one roster module and one sales writer, and by adding a router when a department needs a new capability.

**2. Domain rules implemented in a frontend diverge immediately.** If the portal computes Brasa Points tiers, or the backoffice decides that a location is quiet, the website, the inventory agent, and the Monday workflow each need their own copy to stay consistent. They will not stay consistent. A guest will see a different balance from the CRM, and a ticket posted by a POS adapter will not clear the banner. Clients render the JSON the API returns. The tier boundaries and the quiet-window rule stay in the domain layer.

**3. New routes written in the composition root erase the domain cut.** If every endpoint is added to `services/api/app.py`, a public menu route will sit beside staff administration and will eventually inherit the wrong dependency. OpenAPI will show one tag. The way back is to put the route on the noun’s router and include that router from the factory.

Two further consequences are worth stating because they are easy to “simplify” later:

| If the team does this | What breaks in the business |
| --- | --- |
| Runs the weekly aggregation inside the request that draws the Monday screen | Staff login and the leadership report share a fate. A heavy week takes down the console Felipe uses during service. |
| Treats the illustrative COP/USD display factor as the accounting conversion | Florida’s USD and Colombia’s COP get mixed into one number. Lucía cannot negotiate from it, and Mariana cannot compare a Miami week to a Medellín week. The reporting row keeps the location currency. Display conversion stays labeled as illustrative. |

---

## 8. Consequences the team should expect

- A new department capability is a new module and a new router on the existing app. The review question is “which noun owns this rule?”, not “which service do we deploy?”.
- A new client is a process under `uis/` that speaks HTTP. It does not import `services/`.
- A new slow job is a worker, a cron entry, or a workflow. The HTTP call that starts it returns as soon as the job is accepted.
- Moving the five nouns from memory to Postgres changes the repository file, not the path or the auth rule.
- Brasa Points stay a stamp-card field until a ledger module exists. The architecture does not imply that the digital wallet is done.
- The executive natural-language assistant, when it is built, is a client with tools that call `GET /sales/overview`. It is not a second place where chain totals are calculated, and it is not the standards search.

The test of this document is whether a later change can be placed with these rules without inventing a new system. The test is not whether a server starts.
