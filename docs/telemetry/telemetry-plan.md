# Telemetry Plan

## Overview
This document defines the telemetry instrumentation contract for this repository.
It is implementation-focused and aligned with `docs/telemetry/event-schemas.json`.

## 1. Canonical Event Mapping

Use snake_case `event_type` values in payloads.

| Product/Event Name | event_type value |
|---|---|
| ProductViewed | `product_viewed` |
| InventoryOrderProcessed | `inventory_order_processed` |
| IncidentAnalysisTriggered | `incident_analysis_triggered` |
| IncidentAnalysisCompleted | `incident_analysis_completed` |
| StockThresholdTriggered | `stock_threshold_triggered` |
| DirectStockEditRejected | `direct_stock_edit_rejected` |
| SessionExpired | `session_expired` |

## 2. Event Catalog (What to Emit)

### 2.1 Incident Analysis

* `incident_analysis_triggered`
	* Trigger: user clicks "Analyze and Download CSV" or `POST /api/incidents/analyze` is accepted.
	* Emit timing: after input validation succeeds and before async job dispatch returns success.
	* Properties allowlist: `engine` (required), `input_file` (optional), `output_file` (optional).

* `incident_analysis_completed`
	* Trigger: analysis job completes successfully and summary is produced.
	* Emit timing: after result persistence succeeds.
	* Properties allowlist: `job_id`, `Total Processed`, `Valid Records`, `Invalid Records`, `Scored Cases`, `Average Score` (all required).

### 2.2 Inventory Management

* `product_viewed`
	* Trigger: successful `GET /inventory/products/{id}`.
	* Emit timing: after a successful product read.
	* Properties allowlist: `id` (required).

* `inventory_order_processed`
	* Trigger: successful `POST /inventory/orders/inbound` and `POST /inventory/orders/outbound`.
	* Emit timing: after order persistence succeeds.
	* Properties allowlist: `product_id`, `quantity`, `type`, `created_by`, `created_at` (all required).

### 2.3 Inventory Control and Access Friction Signals

* `stock_threshold_triggered`
	* Trigger: low-stock threshold alert creation.
	* Properties allowlist: `product_id`, `sku`, `current_stock`.

* `direct_stock_edit_rejected`
	* Trigger: blocked direct stock mutation attempts.
	* Properties allowlist: `product_id`, `quantity`, `created_by`, `reason`.

* `session_expired`
	* Trigger: request/session expiration path detected by auth layer.
	* Properties allowlist: none (explicit empty object).

## 3. Batch / Stream Decision Rationale

This strategy is based on business urgency, business value, and signal quality, not technical preference.

* Batch decision for orders: `inventory_order_processed` is emitted once per line item in multi-item orders.
	* Why: each line item is a business transaction and must be count-accurate for operations.

* Stream-like behavior for user navigation: `product_viewed` is rate-controlled.
	* Why: repeated rapid views are low incremental business value and create noise.

## 4. Rate Controls

### 4.1 Events with Controls

* `product_viewed`
	* Debounce: same `id` and `sessionId` within 2 seconds.
	* Throttle: after first accepted event, allow at most one additional event every 30 seconds per (`sessionId`, `userId`, `id`).

### 4.2 Events without Controls

* `inventory_order_processed`: no throttle/debounce.
* `incident_analysis_triggered`: no throttle/debounce.
* `incident_analysis_completed`: no throttle/debounce.

### 4.3 Guardrails

* Never drop transactional/KPI events (`inventory_order_processed`, `incident_analysis_completed`).
* Apply controls only to behavior events where duplicates are non-actionable.

## 5. Envelope and Instrumentation Rules

Every event must include the standard envelope fields:
`eventId`, `timestamp` (ISO-8601), `sessionId`, `userId`, `event_type`, `schemaVersion`, `requestId`, `properties`.

Instrumentation details:

* `eventId`: UUIDv4 generated at emit time.
* `timestamp`: UTC ISO-8601 with timezone suffix.
* `schemaVersion`: use `1.0.0` for this plan.
* `requestId`: propagated from inbound request context; generate UUIDv4 if absent.
* Emission reliability: if telemetry transport fails, do not fail the business request; log and continue.

## 6. Sensitive Data, Anonymisation, and Sanitisation

### 6.1 Never Capture

* Authentication secrets: bearer tokens, passwords, refresh tokens, cookies, authorization headers.
* Free-text incident `description`.

### 6.2 Conditionally Sensitive Fields

* `customer_id` and `reporter_id` are excluded unless legal basis is documented.
* If legal basis exists, store only `sha256(salt + value)` digest, never raw value.

### 6.3 Envelope Identifier Treatment

* `userId`: use platform pseudonymous identifier only. Do not use email/username.
* `sessionId`: random opaque identifier.
* `requestId`: random opaque identifier.

### 6.4 Sanitisation Controls

* Validate properties against allowlist-only schema before emit.
* Drop unknown keys.
* Reject any property value that matches secret patterns (tokens, auth headers).

## 7. Risks and Exclusions

### 7.1 Discarded Events and Why

* `CredentialFailure` (discarded for now): no credential-validation flow is implemented in this scope, so signal quality would be low.
* Generic or non-canonical event names are discarded (for example `stock_alert`, `item_movement`, `inbound_order_created`) to prevent taxonomy drift.

### 7.2 Known Risk

* Auth outcomes are still coarse in some code paths; `session_expired` can still include mixed causes until auth taxonomy is expanded.
