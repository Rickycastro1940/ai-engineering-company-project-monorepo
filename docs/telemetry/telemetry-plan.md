# Brasaland Telemetry Plan

## 1. Executive summary

Brasaland’s inventory system is live across 14 locations, but operations cannot answer basic questions: inbound volume by supplier, waste by reason, threshold breaches, or attempts to bypass order-based stock edits. This plan defines a standard **Event Envelope** and an event catalogue grounded in `CONTEXT-brasaland.md` so capture, storage, and later executive reporting share one contract.

## 2. Standard Event Envelope

Every event MUST include:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `eventId` | string (UUID) | yes | Idempotency / dedup |
| `timestamp` | string (ISO 8601) | yes | UTC capture time |
| `sessionId` | string | yes | Browser or API session |
| `userId` | string | yes | Authenticated operator id (no name/email in properties) |
| `event_type` | string | yes | `entity_action` taxonomy |
| `schemaVersion` | string | yes | Current: `1.0.0` |
| `requestId` | string | yes | Correlates frontend ↔ API ↔ logs |
| `properties` | object | yes | Allowlist keys only for that `event_type` |

## 3. Mandatory metrics (from CONTEXT)

| `event_type` | Class | Hypothesis → decision | Delivery |
| --- | --- | --- | --- |
| `inbound_order_created` | mandatory | Know purchase volume by location/supplier → consolidate purchasing (Lucía) | batch |
| `outbound_order_created` | mandatory | Know consumption rate by location → adjust auto-order suggestions (Felipe) | batch |
| `stock_waste_registered` | mandatory | Know waste volume/reason/location → prioritise audits (Felipe) | batch |
| `stock_threshold_triggered` | mandatory | Know shortfalls early → adjust thresholds / replenishment | stream |
| `direct_stock_edit_rejected` | mandatory | Know bypass attempts → reinforce training/permissions (Jake) | stream |
| `ingredient_price_variance_detected` | mandatory | Know abnormal unit-cost jumps → renegotiate suppliers (Lucía/Mariana) | stream |

Shared inventory property allowlist (plus envelope): `location_id`, `country` (`CO`/`US`), `product_id`, `product_category`, `quantity`, `unit`, `currency` (`COP`/`USD`). For `stock_waste_registered` also required `reason` (`expired` \| `kitchen_error` \| `theft_suspected`). No employee names or customer data.

## 4. Inventory flow instrumentation points (≥5)

1. Authenticated access to inventory module → `section_viewed`
2. Inbound order submit success → `inbound_order_created`
3. Outbound order submit success → `outbound_order_created`
4. Waste registration → `stock_waste_registered`
5. Stock recalculation below minimum → `stock_threshold_triggered`
6. Direct stock edit attempt rejected → `direct_stock_edit_rejected`
7. Inbound unit cost vs history variance → `ingredient_price_variance_detected`
8. Order validation failure → `order_validation_failed`

## 5. Additional catalogue (≥8 across ≥3 categories)

| `event_type` | Category | Class | Hypothesis → decision | Delivery |
| --- | --- | --- | --- | --- |
| `order_validation_failed` | business/inventory | identified | Know which products fail validation most → improve UX/rules | batch |
| `login_failed` | authentication | identified | Know failure reasons volume → tighten auth / support | stream |
| `session_expired` | authentication | identified | Know forced re-auth frequency → tune session TTL | batch |
| `api_latency_recorded` | performance | identified | Know slow endpoints → prioritise backend fixes | batch |
| `page_load_timed` | performance | identified | Know slow backoffice pages → optimise critical routes | batch |
| `frontend_error_caught` | errors | identified | Know uncaught UI failures → schedule fixes | stream |
| `section_viewed` | navigation | identified | Know which sections operators use → prioritise UX | batch |
| `flow_abandoned` | navigation | identified | Know where order flows drop off → simplify steps | batch |
| `web_vital_reported` | performance | identified | Know Core Web Vitals by route → performance budget | batch |

### Property allowlists (additional)

- `order_validation_failed`: `product_id`, `reason`, `location_id`
- `login_failed`: `reason` (`invalid_credentials` \| `session_expired` \| `network_error`) — never email/password
- `session_expired`: `route`
- `api_latency_recorded`: `endpoint`, `method`, `duration_ms`, `status_code`
- `page_load_timed`: `route`, `duration_ms`
- `frontend_error_caught`: `message`, `route` — no stack secrets/PII
- `section_viewed`: `section`, `route`
- `flow_abandoned`: `flow`, `step`, `route`
- `web_vital_reported`: `name`, `value`, `route`

## 6. High-frequency strategy

- `stock_threshold_triggered`: debounce same `product_id` + `location_id` for 15 minutes.
- `api_latency_recorded` / `web_vital_reported`: sample or batch; never one HTTP call per metric (frontend queue handles batching).
- Frontend capture uses queue + flush every **10s** or **20 events**, `sendBeacon` on hide, retry with backoff.

## 7. Risks and exclusions

- Discarded: raw keystroke analytics, full form snapshots — high PII/cost, low ops value.
- Never capture passwords, emails, employee full names, or customer identifiers in `properties`.
- Currency conversion is out of scope for telemetry; record local `currency` only.
- UI language events are independent from `country` and are not mixed into inventory metrics.

## 8. Schema file

Machine-readable schemas live in `docs/telemetry/event-schemas.json` and must stay aligned with this plan.
