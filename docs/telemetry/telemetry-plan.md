# Brasaland telemetry plan

Normative field names and types live in [`event-schemas.json`](./event-schemas.json) (JSON Schema draft 2020-12). This document is normative for **when** to emit, **how** to compute metrics, and **how** a row is stored. If a field name here and in the schema ever diverge, follow the schema and update this file in the same change.

Department served: **Technology** (Nicolás Park) — real-time telemetry from each location into the operations, marketing, and finance path. The metrics below are the ones `CONTEXT.md` assigns to Restaurant Operations (Felipe Guerrero), Procurement (Lucía Fernández), Marketing (Camila Ospina), People (Ashley Turner), and Executive Direction (Mariana Restrepo).

There is no telemetry writer in the running API today. `CONTEXT.md` states the chain has no telemetry. This plan is the contract for adding it to the code that already exists.

## Authority

| Fact | Source |
| --- | --- |
| 14 company-owned restaurants, Colombia and Florida; ~115 employees; ~USD 6 million revenue; HQ Medellín | `CONTEXT.md` |
| Sales dashboards in **COP and USD**; no-sales alert during opening hours; ingredient ordering from history and stock | `CONTEXT.md` Restaurant Operations |
| ~20 suppliers; price history and consolidated purchasing across both markets | `CONTEXT.md` Procurement |
| Brasa Points (physical stamp cards today; 60% of customers do not use them) | `CONTEXT.md` Marketing |
| Turnover, absenteeism, vacancy fill time, by country | `CONTEXT.md` People |
| Central API nouns: locations, menus, sales, customers, suppliers; telemetry; pipelines | `CONTEXT.md` Technology |
| Chain sales in USD and COP; weekly report Monday 07:00 | `CONTEXT.md` Executive Direction |
| Canonical `location_id`, country, and currency | `services/api/locations.py` |
| Live product record | `products.csv` via `services/api/inventory.py` (`product_id`, `name`, `quantity`, `unit`) |
| Order shapes already declared | `services/api/models.py` (`Product`, `InboundOrder`, `OutboundOrder`); `services/api/schemas.py` (`OrderType` `INBOUND` / `OUTBOUND`) |
| Weekly KPI consumer | `data/pipelines/pipeline.py` → table `weekly_location_performance` |
| Waste, supplier cadence, loyalty arithmetic | `docs/company-knowledge-base/` |

`CONTEXT.md` wins if a knowledge-base file disagrees with it. The knowledge base supplies the operating thresholds the briefing does not spell out (waste bands, protein cover, Brasa Points rates, order cadence).

## Constraints every emitter obeys

- Money is stored in the location currency. Colombia locations are **COP**. Florida locations are **USD**. A chain total is two native sums plus an optional USD rollup. The rollup is labeled converted.
- `location_id` on a location-scoped event is one of the 14 ids in `services/api/locations.py`. The pipeline joins `event_payload.location_id` to `locations.id`. The strings in `tests/pipelines/test_pipeline.py` (`miami-downtown`, `medellin-centro`, `bogota-norte`) are fixture labels. After a failed join, `pipeline.py` fills a missing currency with `USD`, which would report a Colombian location as US dollars. Emit the roster ids below.
- The live inventory file is one chain-wide CSV. It has no `location_id`. Chain-scoped stock events use `location_scope: "chain"`. They are not the four event types the weekly pipeline aggregates.
- A successful HTTP handler returns its business response even when the telemetry write fails. Telemetry is appended after the business write commits.
- Payloads contain no email, phone, postal address, customer name, password, JWT, connection string, or traceback. Staff identity is `actor_id` = decimal `users.id`. Customer identity is an opaque `loyalty_account_id` when a digital account exists.
- Timestamps are UTC, written as `YYYY-MM-DDTHH:MM:SSZ` (no milliseconds, no offset other than `Z`).

### Location roster

| `location_id` | Name | Country | Currency | Timezone |
| --- | --- | --- | --- | --- |
| `co-med-centro` | Medellín Centro | Colombia | COP | `America/Bogota` |
| `co-med-elpoblado` | Medellín El Poblado | Colombia | COP | `America/Bogota` |
| `co-bog-chapinero` | Bogotá Chapinero | Colombia | COP | `America/Bogota` |
| `co-bog-norte` | Bogotá Norte | Colombia | COP | `America/Bogota` |
| `co-cali-norte` | Cali Norte | Colombia | COP | `America/Bogota` |
| `co-barranquilla` | Barranquilla | Colombia | COP | `America/Bogota` |
| `co-cartagena` | Cartagena | Colombia | COP | `America/Bogota` |
| `co-pereira` | Pereira | Colombia | COP | `America/Bogota` |
| `us-mia-brickell` | Miami Brickell | United States | USD | `America/New_York` |
| `us-mia-downtown` | Miami Downtown | United States | USD | `America/New_York` |
| `us-orlando` | Orlando | United States | USD | `America/New_York` |
| `us-tampa` | Tampa | United States | USD | `America/New_York` |
| `us-ftlauderdale` | Fort Lauderdale | United States | USD | `America/New_York` |
| `us-jacksonville` | Jacksonville | United States | USD | `America/New_York` |

Eight Colombia ids, six Florida ids. `country` is `Colombia` or `United States` (the `Location.country` enum). Florida is `region` on the location API; telemetry uses `country` plus the `us-` id prefix.

### v1 operating defaults

`CONTEXT.md` requires a no-sales alert during opening hours and does not publish the hours. Until a location record carries hours, the silence monitor uses this v1 contract (field `opening_hours_source` = `telemetry-plan.v1`):

- Local open window: **11:00 inclusive to 22:00 exclusive**, every day, in the location timezone above.
- Silence threshold: **45 minutes** with zero `sale_completed` inside that window.
- Chain week for Mariana’s Monday report: Monday 00:00 through the next Monday 00:00 in `America/Bogota` (Colombia is UTC−5 year-round). A job that fires Monday 07:00 America/Bogota reports the **previous** chain week.
- Low-stock edge on the current CSV uses threshold **10**, the default argument of `get_alerts` in `services/api/inventory.py`.
- USD conversion rate for COP amounts is the process environment variable `BRASALAND_FX_USD_PER_COP` (USD for one COP). USD events use rate `1`. When the variable is unset, COP events set `fx_status` to `missing` and omit `amount_usd`. An emergency COP order with `fx_status: missing` sets `approval_required` to `true`.

## Entities the events describe

### Product (live)

`GET/POST /inventory` and `PATCH /inventory/{product_id}` persist `products.csv`:

| CSV column | Event field | Rule |
| --- | --- | --- |
| `product_id` | `product_id` | Integer ≥ 1, assigned by `create_product` |
| `name` | `product_name` | Strip whitespace, same value written to the CSV |
| `quantity` | `quantity`, `quantity_before`, `quantity_after` | Integers ≥ 0. `apply_delta` rejects a result below 0 with HTTP 400 and emits nothing |
| `unit` | `unit` | Free string, length ≥ 1 (`kg`, `liters`, `boxes` are current samples) |

`services/api/schemas.py` also declares `sku`, `price`, and string `product_id` on a future product model. The live writer does not have those columns. Emit the CSV shape. When a router starts writing `services/api/models.py` `Product`, keep `product_id` as that row’s integer primary key (do not switch the telemetry id to a SKU).

### Order (declared, no live router)

`InboundOrder` / `OutboundOrder` in `services/api/models.py`: `id`, `product_id`, `quantity`, `created_at`, `user_uuid`. The users table key is an integer, so telemetry stores `actor_id` = `str(users.id)` and does not copy the `user_uuid` column name.

`OrderType` in `services/api/schemas.py` is `INBOUND` or `OUTBOUND`, with line items `{product_id, quantity}`. One telemetry event is emitted **per line** after the order row commits, because the weekly pipeline sums a single `cost` per event and groups by one `location_id`. `order_id` ties the lines together. `product_id` on the event is the integer inventory id; if the pydantic body sends a numeric string, parse it with `int` before emit.

Inbound lines are supplier receipts. Outbound lines are kitchen consumption or transfers. A transfer sets `destination_location_id` to a roster id other than `location_id`. Guest checks are `sale_completed`. Outbound orders record stock leaving the kitchen.

### Location, sale, supplier, loyalty

Locations are the roster above (`GET /locations`). Sales, menus, customers, and suppliers are still missing on the central API (`memory-bank/Progress.md`). Their events are specified so the router that adds them can emit on the first write. Menu lines on a sale use `menu_item_name` (a guest-facing dish such as “Grilled Sirloin”). They are not inventory `product_id`s. Ingredient depletion stays on outbound orders and waste events.

`supplier_id` matches `^sup_[a-z0-9_]{2,64}$`. Mint one stable id per supplier (the briefing’s count is about 20, split across the two markets) and reuse it on every receipt.

## Mandatory metrics

Grain, formula, and the events that feed the number. “Chain week” and “location day” are defined in the clock section below.

| Id | Question it answers | Formula | Grain | Freshness | Events |
| --- | --- | --- | --- | --- | --- |
| `exec.chain.sales` | How much did we sell this week, in Florida and across the chain? | Sum of `amount` grouped by `currency`. Florida = `country` United States. Converted rollup = sum of `amount_usd` where `fx_status` is `recorded` | Chain week | Hourly once `sale_completed` exists | `sale_completed` |
| `ops.sales.gross_native` | Sales today at one location, in that location’s currency | Sum of `amount` | Location × `business_date` | Minutes | `sale_completed` |
| `ops.sales.covers` | Covers served | Sum of `covers` | Location × `business_date` | Minutes | `sale_completed` |
| `ops.sales.tickets` | Distinct tickets | Count of `sale_completed` | Location × `business_date` | Minutes | `sale_completed` |
| `ops.sales.average_ticket` | Highest average ticket this month | `sum(amount) / count(sale_completed)` in the location currency. Publish the currency beside the number | Location × calendar month in the location timezone | Nightly | `sale_completed` |
| `ops.sales.silence` | A location is open and has no sales | See silence monitor | One open episode per location | Every 5 minutes | `location_sales_silence_detected` |
| `proc.purchase.cost` | What did this location buy this week? | Sum of payload `cost` on `inbound_order_created` | Location × chain week | Weekly pipeline, Monday 07:00 | `inbound_order_created` |
| `ops.waste.cost` | Waste cost | Sum of payload `cost` on `stock_waste_registered` | Location × chain week | Weekly pipeline | `stock_waste_registered` |
| `ops.waste.ratio` | Waste versus purchases (pipeline field `waste_ratio`) | `waste_cost / purchase_cost` when purchase cost > 0, else `0`. Round to 4 decimal places, matching `aggregate_location_kpis` | Location × chain week | Weekly pipeline | the two events above |
| `ops.waste.monthly_rate` | Keep waste under 4% of monthly ingredient cost; 6% for two months starts an improvement plan | Sum waste `cost` / sum purchase `cost` for the calendar month in the **location** timezone. Compare the ratio to `0.04` (target) and `0.06` (improvement plan if both of the last two months exceed it). Average the weekly ratios is the wrong aggregation | Location × calendar month | Monthly | inbound + waste |
| `ops.stockout.count` | Stockout frequency | Count of `stock_threshold_triggered` | Location × chain week | Weekly pipeline | `stock_threshold_triggered` |
| `proc.price.alerts` | Price moved before the invoice is a surprise | Count of `ingredient_price_variance_detected` | Location × chain week | Weekly pipeline | `ingredient_price_variance_detected` |
| `ops.protein.cover_days` | At least 3 days of main protein on hand | `on_hand / (trailing_28_location_days_usage / 28)`. Usage is the sum of `quantity` on `outbound_order_created` with `reason` `kitchen_consumption` and `protein_class` `main_protein` or `premium_protein`, plus `stock_waste_registered` for the same classes. Emit when cover < 3 and usage > 0 | Location × product | Hourly | outbound, waste, then `stock_threshold_triggered` with `reason` `protein_cover_below_3_days` |
| `ops.shrinkage.rate` | Unexplained shrinkage above 3% of weekly inventory | `shrink_qty / (opening_qty + inbound_qty)` for `waste_category` `unexplained_shrinkage`. `opening_qty` is the latest `quantity_after` on `stock_count_adjusted` for that product and location before the chain week starts. If that snapshot is absent, skip the alert (record `insufficient_snapshot` in the monitor log) and keep the waste events | Location × product × chain week | Weekly | waste + stock counts + inbound |
| `ops.waste.premium_escalation` | Premium protein waste over 5 kg in a week goes to Felipe Guerrero | Sum of `quantity` where `protein_class` is `premium_protein`, `unit` is `kg`, one location, one chain week. Escalate when the sum is **greater than 5** | Location × chain week | Weekly | `stock_waste_registered` |
| `ops.waste.shrinkage_streak` | Three consecutive weeks of unexplained shrinkage at the same location | A week counts when it has at least one `unexplained_shrinkage` waste event for that location | Location | Weekly | `stock_waste_registered` |
| `mkt.loyalty.attach_rate` | Who is actually in Brasa Points (stamp cards produce no rows) | `sale_completed` with `loyalty_attached` true / all `sale_completed` | Chain week, split by country | Daily | `sale_completed` |
| `mkt.loyalty.points_earned` | Points from spend | `floor(amount / 10000)` when currency is COP. `floor(amount / 10)` when currency is USD. The producer writes the integer on the sale | Per ticket | With the sale | `sale_completed` |
| `mkt.loyalty.redeem_value` | 5 points = 20,000 COP or 20 USD | `points / 5 * 20000` COP or `points / 5 * 20` USD. Redeem in multiples of 5 | Per redemption | With the redemption | `loyalty_points_redeemed` |
| `tech.traffic.events_per_day` | Platform volume for the engineering report | Count of rows by UTC date | UTC day | The engineering reader’s window | every stored event |
| `tech.errors.by_type` | Instability | Count of `api_error` grouped by `code` | Reader window | Same | `api_error` |
| `tech.auth.failure_rate` | Sign-in failures | `user_login_failed / (user_login_failed + user_login_succeeded)` per UTC date. The reader in `skills/data-analysis/scripts/pandas_clean.py` already expects these two `event_type` values | UTC day | Same | login events |
| `people.turnover` | Leavers versus headcount, by country | `(leavers in period / average headcount in period) * 100` | Country × month | When the HR portal exists | No event in this pack |
| `people.absenteeism` | Absence, by country | `(days absent / scheduled working days) * 100` | Country × month | When the HR portal exists | No event in this pack |
| `people.time_to_fill` | Vacancy fill time, by country | Days from vacancy open to offer accepted | Country × vacancy | When the HR portal exists | No event in this pack |

People metrics are fixed here so the HR portal does not invent a second definition. This schema pack does not include HR events: there is no HR writer in the repo to attach them to.

### Clocks

| Clock | Definition | Used by |
| --- | --- | --- |
| `occurred_at` | UTC instant of the business fact | Storage columns `created_at` and `timestamp` |
| `business_date` | Calendar date in the location timezone | Per-location day metrics (“covers today in Medellín Centro”) |
| Chain week | `[Monday 00:00, next Monday 00:00)` America/Bogota | `proc.*` weekly pipeline, Mariana’s Monday report, “this week in Florida” |
| Calendar month | Month boundaries in the **location** timezone | Average ticket, monthly waste rate |

Example chain week reported at Monday 2026-09-28 07:00 America/Bogota: `week_start` `2026-09-21`, UTC window `[2026-09-21T05:00:00Z, 2026-09-28T05:00:00Z)`. Pass those instants to `POST /reporting/pipeline-runs` as `start_date` and `end_date`. The extractor filters `created_at` with `gte` start and `lt` end.

Supplier cadence (for monitors that compare a receipt to the expected rhythm; the receipt itself is still `inbound_order_created`):

| `category` | Expectation from `docs/company-knowledge-base/brasaland-supplier-ordering.en.md` |
| --- | --- |
| `proteins` | Weekly order, 48-hour delivery |
| `vegetables_fruit` | Monday and Thursday, 24-hour delivery |
| `beverages_packaging` | Every two weeks, 5 business-day delivery |
| `imported_sauces` | Monthly, 10 to 15 business days, Colombia imports |
| `cleaning` | Named in `CONTEXT.md`; the procedure does not set a cadence |
| `other` | Anything else |

Emergency inbound (`order_kind` `emergency`): `surcharge_rate` is `0.08` and `cost` is the charged amount (`list_cost * 1.08`, rounded to 2 decimal places). Scheduled inbound uses `surcharge_rate` `0` and `cost` = `list_cost`. `approval_required` is true when `order_kind` is `emergency` and (`amount_usd` > 500 or `fx_status` is `missing`). At exactly 500 USD, `approval_required` is false. The approver role is Procurement Manager.

Waste notes: when `protein_class` is `main_protein` or `premium_protein`, `unit` is `kg`, and `quantity` > 2, `note` is required (the shift log for more than 2 kg of meat protein). `premium_protein` means tenderloin or ribs, as in the waste protocol. Training waste in an employee’s first 14 days may set `training_waste` true; the note rule still applies.

Price alert: after an inbound line is priced, load the previous `unit_price` for the same `product_id`, `supplier_id`, and `currency`. Emit `ingredient_price_variance_detected` when a previous price exists and `abs(unit_price - previous_unit_price) / previous_unit_price >= 0.01`. The first price for that key is stored and does not emit an alert. `variance_pct` = `(unit_price - previous_unit_price) / previous_unit_price`.

## Event catalog

| `event_type` | `location_scope` | Producer | Pipeline reads it? |
| --- | --- | --- | --- |
| `product_created` | `chain` today; `location` once the row has a location | `services.api.inventory` `create_product` | No |
| `stock_count_adjusted` | `chain` or `location` | `services.api.inventory` `apply_delta` | No |
| `stock_threshold_crossed` | `chain` | `apply_delta` when quantity crosses from ≥ 10 to < 10 | No |
| `stock_threshold_cleared` | `chain` | `apply_delta` when quantity crosses from < 10 to ≥ 10 | No |
| `inbound_order_created` | `location` | Future order writer, one event per inbound line | Yes — sums `cost` into `total_purchase_cost` |
| `outbound_order_created` | `location` | Future order writer, one event per outbound line | No |
| `stock_waste_registered` | `location` | Waste log at shift close | Yes — sums `cost` into `total_waste_cost` |
| `stock_threshold_triggered` | `location` | Location-scoped stock edge, or the protein-cover monitor | Yes — counted |
| `ingredient_price_variance_detected` | `location` | Same transaction as the inbound line that changed price | Yes — counted |
| `sale_completed` | `location` | Future sales writer, one event per closed ticket | No (executive/ops readers) |
| `location_sales_silence_detected` | `location` | `services.telemetry.silence_monitor` | No |
| `loyalty_points_redeemed` | `location` | Future loyalty writer | No |
| `loyalty_card_transferred` | `location` | One-time physical card → app transfer | No |
| `user_login_succeeded` | `none` | `services/api/users.py` login handlers | No |
| `user_login_failed` | `none` | Those handlers’ 401 branches | No |
| `api_error` | `none` | `services/api/errors.py` 500 and 503 handlers | No |
| `page_view` | `none` | `uis/website` and `uis/backoffice` | No |

`data/pipelines/pipeline.py` `extract_telemetry_events` filters exactly these four types: `inbound_order_created`, `stock_waste_registered`, `stock_threshold_triggered`, `ingredient_price_variance_detected`. `scripts/nightly_export.py` copies only the first three. When that export is next edited, add `ingredient_price_variance_detected` so the CSV matches the extractor. The extractor reads Supabase itself; the CSV is not the aggregation input.

## Storage row

Writers insert one row into Supabase table `telemetry_events`. Both existing readers must see the row:

| Column | Value | Reader |
| --- | --- | --- |
| `id` | Event `id` (UUID) | Engineering select in `skills/data-analysis/scripts/services/telemetry/main.py` |
| `event_type` | Event `event_type` | Both |
| `timestamp` | `occurred_at` | Engineering select |
| `created_at` | The same `occurred_at` | Pipeline `gte` / `lt` filter |
| `event_payload` | JSON `payload` | Pipeline `location_id` and `cost` |
| `tags` | JSON `tags` | Engineering select |

`tags` is a copy, built only by this function, so the engineering reader and the payload cannot drift:

```python
def build_tags(source: str, payload: dict) -> dict:
    tags = {"source": source, "location_scope": payload["location_scope"]}
    for key in ("location_id", "country", "currency"):
        if payload.get(key) is not None:
            tags[key] = payload[key]
    return tags
```

`payload.cost`, when present, is a JSON number in the location currency. The pipeline does `float(payload.get("cost", 0) or 0)`. Purchase and waste events always send `cost`. Price-alert and stockout events omit `cost`; the pipeline treats that as zero and only counts the rows.

### Emit algorithm

```text
emit(event):
  1. Validate the producer document against event-schemas.json (draft 2020-12, format checks on).
  2. If validation fails: log a warning on logger "brasaland.telemetry" with event_type and a one-line reason. Do not insert. Do not raise into the HTTP handler.
  3. Insert the storage row.
  4. If the insert fails: append the producer document as one JSON line to data/uploads/telemetry_outbox.jsonl (data/uploads/ is gitignored). Do not raise.
```

Retries reuse the same `id`. Consumers dedupe on `id`. A silence episode reuses one `id` for the life of that episode (`silence_started_at` + `location_id`). A new episode (after a `sale_completed`, or after the local close) gets a new `id`.

The outbox directory is `data/uploads/` because that path is already gitignored. A dedicated telemetry path needs a `.gitignore` edit, which this repo treats as a confirmed change.

## Instrumentation map

Wire these call sites. Validate after the business write has succeeded.

### `services/api/inventory.py`

| Function | Route | Emit |
| --- | --- | --- |
| `create_product` | `POST /inventory` | `product_created` with `location_scope` `chain`, `quantity` = the stored quantity |
| `apply_delta` | `PATCH /inventory/{product_id}` | `stock_count_adjusted` with `reason` `count_correction`, `delta`, `quantity_before`, `quantity_after` |

On `apply_delta` only, using threshold 10:

- `quantity_before >= 10` and `quantity_after < 10` → also `stock_threshold_crossed`
- `quantity_before < 10` and `quantity_after >= 10` → also `stock_threshold_cleared`
- A change that stays under 10 or stays at/above 10 emits only `stock_count_adjusted`

`GET /inventory` and `GET /inventory/alerts` emit nothing (a poll would inflate stockout counts).

HTTP 400 from `apply_delta` (insufficient stock, or a negative threshold on `get_alerts`) emits nothing.

`PATCH` is a count correction. A supplier receipt is an inbound order event with a real `cost`, `supplier_id`, and `location_id`. A positive `delta` on `PATCH` does not become `inbound_order_created` (that would add a purchase with no supplier price and distort `waste_ratio`).

`actor_id` is present when the inventory route is called with the staff JWT (`users.id`). The inventory router does not require auth today; omit `actor_id` when there is no user.

### `services/api/users.py`

| Function | Route | Emit |
| --- | --- | --- |
| `login` | `POST /auth/login` | `user_login_succeeded` with `method` `json` and `actor_id`, or `user_login_failed` with `failure_reason` `invalid_credentials` or `inactive_user` on the 401 branch |
| `login_for_access_token` | `POST /auth/token` | Same pair with `method` `oauth2_form` |

Emit the failure event, then raise the existing `HTTPException`. The payload has no email and no password. `register_and_login` does not emit a login event (the account-creation request is not a sign-in attempt). Failed registration emits nothing unless it becomes a 500, which `api_error` covers.

### `services/api/errors.py`

| Handler | Emit |
| --- | --- |
| `handle_unhandled_error` when it returns 500 | `api_error` with `http_status` 500 and `code` `internal_error` |
| `handle_external_service_error` | `api_error` with `http_status` 503 and `code` `service_unavailable` |

`handle_validation_error` and 4xx responses in `handle_http_exception` do not emit `api_error` (the auth failure rate already counts 401s on the login routes). `route_template` is `request.scope["route"].path` when a route matched (`/inventory/{product_id}`), otherwise the literal `unmatched`. Copy `request.method`. Do not copy the query string, the body, or `logger.exception` text into the payload.

### `uis/website/src/pages/HomePage.tsx`

On mount, emit `page_view` with `app` `website` and `path` `/`. The `*` route only redirects to `/`, so it does not emit a second event.

### `uis/backoffice` pages

On mount of the page component, emit `page_view` with `app` `backoffice` and `path` set to the pathname only:

| Component | `path` |
| --- | --- |
| `LoginPage` | `/login` |
| `RegisterPage` | `/register` |
| `AccessiblePage` | `/accessible` |
| `ProfilePage` | `/account/profile` |
| `ChangePasswordPage` | `/account/change-password` |

`/` and unknown paths redirect to `/accessible`. Emit when `AccessiblePage` mounts, not when the redirect renders. Strip `?next=` and any other query before setting `path`.

### Future writers (emit in the same request that inserts the row)

| Writer to add under `services/api/` | Emit |
| --- | --- |
| Inbound order line commit | `inbound_order_created`, then `ingredient_price_variance_detected` when the 1% rule matches |
| Outbound order line commit | `outbound_order_created` |
| Shift-close waste log | `stock_waste_registered` |
| Location-scoped stock that crosses its threshold downward | `stock_threshold_triggered` with `reason` `quantity_below_api_threshold` and `edge` `crossed_below`. One event per crossing, not per poll |
| Sales ticket close | `sale_completed` |
| Loyalty redemption | `loyalty_points_redeemed` |
| Physical card handed in once | `loyalty_card_transferred` |

Protein cover emits `stock_threshold_triggered` from a monitor (`source` `services.telemetry.cover_monitor`), at most once per location + product per 24 hours while cover stays under 3 days.

### Silence monitor

Process `services.telemetry.silence_monitor` (new module; this plan does not add it):

1. Every 5 minutes, for each of the 14 locations, compute local time.
2. If local time is outside `[11:00, 22:00)`, close any open episode and emit nothing.
3. If local time is inside the window, let `last_sale` be the latest `sale_completed.occurred_at` for that `location_id` with `business_date` equal to the location-local date. If there is no such sale, `silence_started_at` is local 11:00 converted to UTC. If the gap from `last_sale` to now is ≥ 45 minutes, `silence_started_at` is `last_sale`.
4. Emit one `location_sales_silence_detected` per open episode. `sale_count` is `0`. `evaluated_at` is the run instant.

## Worked pipeline numbers

`aggregate_location_kpis` for one chain week, location `us-mia-downtown`:

| Event | `cost` |
| --- | --- |
| `inbound_order_created` | 1000 |
| `stock_waste_registered` | 150 |
| `stock_threshold_triggered` | omitted |
| `ingredient_price_variance_detected` | omitted |

Stored weekly row: `total_purchase_cost` 1000, `total_waste_cost` 150, `waste_ratio` 0.15, `stockout_events_count` 1, `price_alert_events_count` 1, `currency` USD, `country` United States. That matches the arithmetic in `tests/pipelines/test_pipeline.py` once the fixture id is the roster id.

A COP receipt at `co-med-centro` with `list_cost` 1000000, `order_kind` `scheduled`, `surcharge_rate` 0, stores `cost` 1000000 and `currency` COP. It is summed only with other COP events for that location. It is not added to the Miami USD total.

Brasa Points on a ticket: 45,000 COP → `points_earned` 4. 27 USD → `points_earned` 2. A redemption of 15 points (the minimum balance the loyalty procedure allows before redeeming) in increments of 5 discounts `15 / 5 * 20000` = 60,000 COP, or 60 USD in Florida. The event records `balance_before` (at least 15), the points redeemed on that ticket (a multiple of 5, at least 5, and less than or equal to `balance_before`), and the `discount_amount`.

## Privacy and logging

- Logger name: `brasaland.telemetry`.
- Log `event_type`, `id`, and `schema_rejected` or `store_unavailable`. Do not log `payload`.
- `user_login_failed.failure_reason` is `invalid_credentials` or `inactive_user`.
- `api_error.message` is the public message already returned by `error_body` (`Internal server error` or the 503 public text). It is not `str(exc)` when that string might contain a host, a key, or a query.
- Page paths have no query and no fragment.

## Checklist for the person wiring this in

1. Validate each producer document against `docs/telemetry/event-schemas.json` before the insert (the `examples` arrays in that file are valid documents). The root schema is a `oneOf` over the 17 events. On failure, read the branch whose `event_type` const matches the document.
2. Write both `timestamp` and `created_at` from `occurred_at`.
3. Put business fields in `event_payload` and the small copy in `tags`.
4. Use a roster `location_id` whenever `location_scope` is `location`, and the matching currency (`COP` or `USD`).
5. From `POST /inventory` and `PATCH /inventory/{product_id}`, emit only the chain events listed for `inventory.py`.
6. Leave `GET` handlers, HTTP 400 stock rejections, and 4xx error handlers silent.
7. Keep `cost` in the location currency on inbound and waste events so `waste_ratio` stays dimensionally consistent.
8. Deduplicate on `id`.
9. Run `aggregate_location_kpis` on a four-event fixture that uses `us-mia-downtown` and expect `waste_ratio` 0.15 with `currency` USD.
10. Confirm a COP `inbound_order_created` for `co-med-centro` does not land in the USD weekly total.
