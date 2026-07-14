# Backoffice telemetry capture

Implements the frontend half of **Company's Telemetry – Frontend capture** for Brasaland.

## Setup

```bash
# Terminal 1 — FastAPI stub
cd services/api
export TELEMETRY_ENDPOINT=http://localhost:8000/telemetry/events
python main.py

# Terminal 2 — backoffice
cd uis/backoffice
cp .env.local.example .env.local   # if needed
npm install
npm run dev
```

Open `http://localhost:5173`. Use the nav + inventory actions, then confirm batches in DevTools → Network → `POST /telemetry/events` → `200 { "received": N }`.

## Contract

- Plan: `docs/telemetry/telemetry-plan.md`
- Schemas: `docs/telemetry/event-schemas.json`
- Single public API: `track(eventType, properties)` in `src/services/telemetry.ts`
- Env: `NEXT_PUBLIC_TELEMETRY_ENDPOINT` (never hardcoded in source)

## Instrumented coverage

**Mandatory CONTEXT metrics** (inventory/orders/suppliers actions):

- `inbound_order_created`
- `outbound_order_created`
- `stock_waste_registered`
- `stock_threshold_triggered`
- `direct_stock_edit_rejected`
- `ingredient_price_variance_detected`

**Technical baseline:**

- Errors: `frontend_error_caught`
- Performance: `page_load_timed`, `api_latency_recorded`
- Navigation: `section_viewed` on Dashboard, Inventory, Orders, Suppliers, Auth
