# MCP Server — Company Tools (submission notes)

## Acceptance criteria (verified)

1. **Domain parity with existing APIs** — MCP ticket/product fields match
   `IncidentRecord` / `InventoryProduct` from `services/api` (`incident_id`,
   `location_id`, `category`, `ABIERTO|CERRADO|DESCARTADO`, `BRS-######`,
   `product_id`/`quantity`/`unit`, `source=incident_manager|inventory_manager`).
   Tools call `COMPANY_API_BASE` over HTTP; they do not replace the backends.
2. **Lifecycle status only** — `action=update` always calls
   `PATCH /api/incidents/{id}/status` via `http_clients.update_incident_status`.
   There is no generic `PATCH /api/incidents/{id}` helper.
3. **OAuth via MCP Auth** — `mcpauth.MCPAuth` in **resource-server** mode with
   OIDC (`AuthServerType.OIDC`), provider-agnostic via `MCP_AUTH_ISSUER`.
   Bearer JWT middleware blocks anonymous `tools/list` / `tools/call` (HTTP 401).
   Least-privilege **`required_scopes`**: `incidents:read` / `incidents:manage` /
   `inventory:read` enforced per tool/action. Domain HTTP clients are split so
   inventory cannot call incident routes and vice versa (inventory is GET-only).
   FastMCP built-in auth is not used (`settings.auth is None`).

Regression coverage: `tests/pipelines/test_company_tools_mcp.py`
(`test_acceptance_*`).

## Depends on existing backends

The MCP server **does not replace** the Incidents Manager or inventory module.
`mcps/company_tools/http_clients.py` issues HTTP calls to:

- `POST /api/incidents`, `PATCH /api/incidents/{id}/status`, `GET /api/incidents/{id}`
- `GET /inventory/products`, `GET /inventory/products/{id}`

Those routes live in `services/api/` (CSV-backed stores from earlier milestones).

## Transport choice

**Streamable HTTP** (port `3001`, path `/mcp`).

Remote clients (MCP Playground, other teams, partners) must reach the same
OAuth-protected resource server. stdio only works when one local process spawns
the server as a subprocess, so it cannot satisfy the RFP. MCP Auth bearer
middleware and Protected Resource Metadata are mounted on the HTTP app.

## Layout

- `mcps/company_tools/` — FastMCP + MCP Auth (`mcpauth`) resource server
- `services/api/` — `POST /api/incidents` + `PATCH /api/incidents/{id}/status`
- `services/agent/tools/mcp_incidents.py` — LangGraph client via `langchain-mcp-adapters`
- Direct `ticket_lookup.lookup_ticket` is **deprecated** for graph use

## Auth

- Library: **MCP Auth** (`mcpauth`) — not FastMCP built-in auth
- Dev issuer: `mcps/company_tools/dev_issuer.py` (local OIDC + JWKS)
- Production: set `MCP_AUTH_ISSUER` to Logto / any OIDC provider
- Scopes: `incidents:manage`, `inventory:read`

## Domain contract (must match Company APIs)

| Area | Values / fields |
| ---- | --------------- |
| Incident id | `incident_id` (`BRS-######`) |
| Statuses | `ABIERTO`, `CERRADO`, `DESCARTADO` |
| Categories | `EQUIPAMIENTO`, `ABASTECIMIENTO`, `QUEJA_CLIENTE`, `CALIDAD_ALIMENTO`, `PERSONAL` |
| Ticket fields | same as `IncidentRecord` (`date`, `location_id`, `category`, `description`, `status`, `customer_id`, `satisfaction_score`, `reporter_id`, `source`) |
| Inventory fields | same as API `InventoryProduct` (`product_id`, `name`, `quantity`, `unit`, `source`) |
| Status update | **only** `PATCH /api/incidents/{id}/status` |
| Scopes | `incidents:read`, `incidents:manage`, `inventory:read` (`required_scopes` per tool) |

## How to run

See `mcps/company_tools/README.md`.

## Playground

Forward port `3001` with **public** visibility (Codespaces / Cloudflare Tunnel),
mint a token from the issuer (`GET /token?client_id=mcp-playground`), paste the
public URL + Bearer token into
[MCP Playground](https://www.mcpplayground.tech/connect).

### Verified connection

Connected Brasaland Company Tools (`v1.29.0`) via Streamable HTTP + Bearer JWT:

1. Discovered tools: `manage_incident_ticket`, `query_inventory`
2. `query_inventory` read path succeeds against live inventory API
3. `query_inventory` with `action=update` returns `INVENTORY_WRITE_FORBIDDEN`

Screenshots: [`docs/agent/playground/`](./playground/)
