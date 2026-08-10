# Tool discovery (`--help` equivalent)

External agents discover these tools via MCP `tools/list`. Each entry includes
**name**, **description**, **inputSchema**, and **outputSchema** — no human
context required beyond this document / the live discovery payload.

Schemas are defined in `schemas.py` and published by FastMCP from the annotated
tool signatures in `server.py`.

---

## `manage_incident_ticket`

| | |
| --- | --- |
| **Title** | Manage Brasaland incident tickets |
| **OAuth scope** | `required_scopes`: `incidents:read` (get_status) or `incidents:manage` (create/update) |
| **Upstream** | Incidents Manager HTTP API |

### Actions

| `action` | Required inputs | Upstream call |
| --- | --- | --- |
| `create` | `category`, `description` | `POST /api/incidents` |
| `update` | `ticket_id`, `status` | `PATCH /api/incidents/{id}/status` |
| `get_status` | `ticket_id` | `GET /api/incidents/{id}` |

### Input (summary)

- `action` — `create` \| `update` \| `get_status`
- `ticket_id` — e.g. `BRS-000002`
- `category`, `description`, `status`, `date`, `location_id`, `customer_id`, `satisfaction_score`, `reporter_id`
- Categories must match Incidents Manager: `EQUIPAMIENTO | ABASTECIMIENTO | QUEJA_CLIENTE | CALIDAD_ALIMENTO | PERSONAL`
- Statuses: `ABIERTO | CERRADO | DESCARTADO` (updates only via lifecycle `PATCH .../status`)

### Output (summary)

```json
{
  "ok": true,
  "action": "get_status",
  "ticket": {
    "incident_id": "BRS-000002",
    "status": "ABIERTO",
    "category": "ABASTECIMIENTO",
    "description": "…",
    "date": "2026-06-01",
    "location_id": "COL-02",
    "source": "incident_manager"
  },
  "duration_ms": 12
}
```

Error shape: `{ "ok": false, "error_code": "NOT_FOUND|VALIDATION_ERROR|LIFECYCLE_ERROR|…", "message": "…", "tool": "manage_incident_ticket" }`

---

## `query_inventory`

| | |
| --- | --- |
| **Title** | Query Brasaland inventory (read-only) |
| **OAuth scope** | `required_scopes`: `inventory:read` |
| **Upstream** | `GET /inventory/products` (products.csv-backed) |

### Read inputs

- `action` — `query` \| `get` \| `list` \| `read` (default `query`)
- `product_id` — e.g. `"1"`
- `name_contains` — case-insensitive name filter

### Explicit write rejection

Any of these triggers **`INVENTORY_WRITE_FORBIDDEN`** (not a missing tool):

- `action` in `update|create|delete|write|patch|put`
- non-empty `quantity`, `delta`, `unit`, or `name`

### Output (summary)

```json
{
  "ok": true,
  "products": [
    {
      "product_id": "1",
      "name": "Tomatoes",
      "quantity": 25,
      "unit": "kg",
      "source": "inventory_manager"
    }
  ],
  "duration_ms": 8
}
```

Write-reject shape:

```json
{
  "ok": false,
  "error_code": "INVENTORY_WRITE_FORBIDDEN",
  "message": "Inventory tool is read-only. Write operations are not permitted on this MCP server.",
  "tool": "query_inventory"
}
```

---

## Dump live discovery

With the MCP server running and a Bearer token:

```bash
# After MCP initialize/session, call tools/list — or locally:
uv run python -c "import asyncio,json; from mcps.company_tools.server import mcp; \
tools=asyncio.run(mcp.list_tools()); print(json.dumps([t.model_dump() for t in tools], indent=2))"
```
