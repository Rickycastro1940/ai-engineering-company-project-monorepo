# CONTEXT-company.md — Brasaland data pipelines contract

**Source company briefing:** root [`CONTEXT.md`](./CONTEXT.md) (Welcome to Brasaland).
**Pipeline design:** [`data/pipelines/PIPELINE_DESIGN.md`](./data/pipelines/PIPELINE_DESIGN.md).

This file is the source of truth for the business-performance pipeline’s **KPI names**, **destination table schema**, and **reporting endpoint contract**. Engineering telemetry (`GET /telemetry/report`, `services/telemetry/analysis.py`) is out of scope here and must stay untouched.

**Audience:** Mariana Restrepo (CEO), Felipe Guerrero (Operations), Lucía Fernández (Procurement).
**Cadence:** Monday 07:00 America/Bogota, previous chain week `[Monday 00:00, next Monday 00:00)`.

---

## KPIs to Measure

Grain: **one row per `location_id` per chain week**. Costs stay in the location currency (COP in Colombia, USD in Florida). Do not convert currencies in this table.

| KPI (business name) | Column name | Formula | Source `event_type` (mandatory telemetry) |
| --- | --- | --- | --- |
| Purchase cost | `total_purchase_cost` | Sum of `event_payload.cost` | `inbound_order_created` |
| Waste cost | `total_waste_cost` | Sum of `event_payload.cost` | `stock_waste_registered` |
| Waste ratio | `waste_ratio` | `total_waste_cost / total_purchase_cost` when purchase > 0, else `0` (4 decimal places) | the two cost events above |
| Stockout frequency | `stockout_events_count` | Count of rows | `stock_threshold_triggered` |
| Price alert frequency | `price_alert_events_count` | Count of rows | `ingredient_price_variance_detected` |

Dimension columns on every row:

| Column | Rule |
| --- | --- |
| `location_id` | Roster id from `services/api/locations.py` (e.g. `co-med-centro`, `us-mia-downtown`) |
| `week_start` | Chain-week Monday `YYYY-MM-DD` |
| `country` | Join to `locations`: `Colombia` or `United States` (unmatched → `Unknown`) |
| `currency` | Join to `locations`: `COP` or `USD` (unmatched fallback `USD`) |

Primary key: `(location_id, week_start)`.

---

## Destination table schema

Schema: **`reporting`** (analytical). Never write these tables into `telemetry_events`.

### `reporting.weekly_location_performance`

| Column | Type | Notes |
| --- | --- | --- |
| `location_id` | text | PK part 1 |
| `week_start` | date | PK part 2 |
| `total_purchase_cost` | float | KPI |
| `total_waste_cost` | float | KPI |
| `waste_ratio` | float | KPI |
| `stockout_events_count` | integer | KPI |
| `price_alert_events_count` | integer | KPI |
| `country` | text | Dimension |
| `currency` | text | Dimension |

Load strategy: **upsert** on `(location_id, week_start)` assigning recomputed totals (never add deltas).

### `reporting.pipeline_runs` (execution log)

| Column | Type | Notes |
| --- | --- | --- |
| `run_id` | uuid | PK |
| `started_at` | timestamptz | UTC |
| `finished_at` | timestamptz | nullable until done |
| `window_start` / `window_end` | text | Chain-week bounds passed to the run |
| `records_processed` | integer | Deduped extract row count |
| `status` | text | `Running` \| `Success` \| `Failed` |
| `error_message` | text | Public failure text; null on success |

SQL reference: `data/pipelines/reporting_schema.sql`.

---

## Endpoint contract (`services/reporting/` only)

These routes are **not** in `services/telemetry/`. They import flows/helpers from `data/pipelines/`. No KPI arithmetic in the HTTP layer.

| Role | Method + path | Behaviour |
| --- | --- | --- |
| Status | `GET /reporting/pipeline-runs/latest` | Newest `reporting.pipeline_runs` row (mirrored in `data/pipelines/last_run.json`) |
| Manual trigger | `POST /reporting/pipeline-runs` | Body `{ "start_date", "end_date" }` → enqueue Prefect flow via Celery; **202** `{ "task_id" }` |
| KPI query | `GET /reporting/weekly-location-performance` | Optional `week_start`; reads **only** `reporting.weekly_location_performance` |

Example KPI response shape:

```json
{
  "week_start": "2026-09-21",
  "locations": [
    {
      "location_id": "us-mia-downtown",
      "country": "United States",
      "currency": "USD",
      "total_purchase_cost": 1000,
      "total_waste_cost": 150,
      "waste_ratio": 0.15,
      "stockout_events_count": 1,
      "price_alert_events_count": 1
    }
  ]
}
```

---

## Mandatory telemetry event fields (extract inputs)

Read-only from `telemetry_events` (plus `locations` dimension). Required `event_type` values for this pipeline are the four KPI sources above. Payload fields used:

| Field | Where | Used for |
| --- | --- | --- |
| `id` | event row | Dedupe before sum (corrected receipts keep the same id) |
| `event_type` | event row | KPI branch |
| `created_at` | event row | Chain-week window (`gte` / `lt`) |
| `event_payload.location_id` | JSON | Group key |
| `event_payload.cost` | JSON | Purchase / waste sums (missing → 0) |

Do **not** modify `telemetry_events`, `services/telemetry/analysis.py`, or `GET /telemetry/report`.

---

## Monorepo placement

| Path | Role |
| --- | --- |
| `data/pipelines/pipeline.py` | Main Prefect entry (`brasaland_weekly_performance_pipeline`) |
| `data/raw/` | Extract snapshots / intermediate files for a run |
| `data/process/` | Reusable transforms (`location_kpis.py`) |
| `data/eval/` | Fixtures + validation outputs |
| `services/reporting/` | Status / trigger / KPI HTTP shell |

---

## Monthly consolidated sales (`data/raw/brasaland_sales.csv`)

Separate from the weekly KPI table above. This is the historical series for the sales forecast (Mariana, Felipe, Lucía). The file in the monorepo is the official series from `content/contexts/sales-forecasting/brasaland/brasaland_sales.csv`. Do not regenerate it.

Grain: **one row per month**, all 14 locations already consolidated. Range: `2016-01-01` through `2025-12-01` (120 months). Target: `revenue_usd`.

| Column | Type | Description |
| --- | --- | --- |
| `month` | date (`YYYY-MM-01`) | First day of the reported month |
| `revenue_usd` | float | Total sales for the month, consolidated in USD (illustrative rate 1 USD = 4,000 COP) |
| `covers_served` | int | Guests served that month across all 14 locations |
| `avg_ticket_usd` | float | Average ticket for the month in USD |
| `market` | string | `colombia`, `florida`, or `consolidated`. This file only has `consolidated` rows. That is the series the model trains on |

Seasonality already in the file: January is about 12–18% under the previous year’s average; December is about 20–30% above that year’s average; other months stay near the trend (±5%). Annual growth is about 5%, alternating near 3% and 7%.

Training uses the first 8 years (`2016`–`2023`). The check set is the 2 most recent years (`2024`–`2025`). The model must not see those test years during training. Blank or null cells are dropped before that split. Dollar and cover features are scaled with a scaler fit on the training rows only.

**Which forecast error costs more.** Underestimating sales is the costlier miss. Felipe buys meat and produce from the expected volume. December is already about 20–30% above that year’s average; a forecast that is low in that month leaves the 14 kitchens short and the location stocks out, so the cover is lost. Overestimating raises waste cost, which the weekly KPI already tracks and which the next order can trim. A large miss on a peak month costs more than the same dollar error spread across quiet months, so RMSE is the primary error and MAE is the companion.
