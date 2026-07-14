# Company Context (API + UI Aligned)

This file defines the canonical domain vocabulary for this{PageDown} repository.
Entity names, field keys, and UI labels below must be used exactly as written.

## Domain Scope

The current implementation includes two business domains:

1. Incident Analysis
2. Inventory Management

## Incident Analysis

### Primary Entity: Incident Record

Required CSV columns:

- incident_id
- date
- location_id
- category
- description
- status
- customer_id
- satisfaction_score
- reporter_id

Allowed category values:

- EQUIPAMIENTO
- ABASTECIMIENTO
- QUEJA_CLIENTE
- CALIDAD_ALIMENTO
- PERSONAL

Allowed status values:

- ABIERTO
- CERRADO
- DESCARTADO

Validation rules in active service logic:

- description must be at least 10 characters
- satisfaction_score is required when status is CERRADO
- satisfaction_score must be an integer from 1 to 5 when provided

### API Names and Payload Keys

Analyze request payload keys:

- input_file
- output_file
- engine

Engine values:

- native
- pandas

Incident API routes:

- POST /api/incidents/anylayze
- POST /api/incidents/anylayze/summary
- POST /api/incidents/anylayze/upload
- POST /api/incidents/anylayze/upload/summary
- POST /api/incidents/analyze
- POST /api/incidents/analyze/summary
- POST /api/incidents/analyze/upload
- POST /api/incidents/analyze/upload/summary
- GET /api/incidents/results/export

Summary response keys consumed by the UI:

- general_metrics
- category_breakdown
- satisfaction_index
- output_file

Nested keys consumed by the UI:

- general_metrics.total_processed
- general_metrics.valid_records
- general_metrics.invalid_records
- satisfaction_index.scored_cases
- satisfaction_index.average_score
- satisfaction_index.score_distribution

### UI Labels (Incident Web UI)

Form labels:

- Input CSV path
- Output CSV path
- Engine

Action labels:

- Analyze and Download CSV
- Upload CSV and Analyze
- Download Last Results CSV
- Download Results as CSV

Section labels:

- Incident Analysis
- General Metrics
- Category Breakdown
- Satisfaction Index

Metric card labels:

- Total Processed
- Valid Records
- Invalid Records
- Scored Cases
- Average Score

Table headers:

- Category
- Count
- Score
- Count

## Inventory Management

### Primary Entity: Product

Fields used by the Backoffice inventory client:

- id
- name
- sku
- category
- price
- quantity
- unit
- current_stock

### Inventory Order Entities

Order payload keys used by the Backoffice inventory client:

- product_id
- quantity

Order type vocabulary in API schemas:

- INBOUND
- OUTBOUND

Order response fields in API schemas:

- id
- type
- created_by
- created_at
- items

### API Names and Routes (Inventory)

Routes used by Backoffice inventory client:

- GET /inventory/products
- GET /inventory/products/{id}
- POST /inventory/orders/inbound
- POST /inventory/orders/outbound
- GET /inventory/orders

Additional inventory routes used by the root agent flow:

- GET /inventory
- POST /inventory
- PATCH /inventory/{product_id}
- GET /inventory/alerts

Agent tool vocabulary:

- list_inventory
- add_product
- update_stock
- get_low_stock_alerts

Agent inventory payload keys:

- name
- quantity
- unit
- product_id
- delta
- threshold

## Naming Rules

- Keep API field keys in snake_case exactly as implemented.
- Keep enum values uppercase exactly as implemented.
- Keep UI labels in title case exactly as shown.
- Do not introduce synonyms for canonical entity names (for example, use Product, Incident Record, Inbound Order, Outbound Order).

## Implementation Source of Truth

These names were aligned with the current implementation in:

- services/api/constants.py
- services/api/validator.py
- services/api/schemas.py
- services/api/app.py
- services/api/inventory.py
- uis/backoffice/lib/inventory.ts
- uis/web/index.html
- agent.py
