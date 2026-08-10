# MCP Server — Company Tools (submission notes)

## Acceptance criteria (verified)

0. **Location + start + discovery** — Server package lives under
   `mcps/company_tools/` (`server.py` / `__main__.py`). `create_app()` boots a
   Starlette ASGI app (Streamable HTTP on `/mcp`). Tools are exposed through
   standard MCP discovery: in-process `mcp.list_tools()` and authenticated
   JSON-RPC `tools/list` both return `manage_incident_ticket` and
   `query_inventory` with descriptions + `inputSchema`. Confirmed by
   `test_mcp_server_lives_under_mcps_and_starts` and
   `test_mcp_standard_discovery_exposes_tools`.
0b. **Self-explanatory discovery (no source required)** — Each tool's
   `tools/list` entry includes a clear `description`, `title`, full
   `inputSchema` (every property described), and `outputSchema`. External
   clients can learn actions, required fields, statuses/categories, OAuth
   scopes, and inventory write rejection (`INVENTORY_WRITE_FORBIDDEN`) from
   discovery alone. Snapshot: [`docs/agent/mcp-tools-discovery.json`](./mcp-tools-discovery.json).
   Confirmed by `test_mcp_discovery_descriptions_and_schemas_self_explanatory`.
1. **Domain parity with existing APIs** — MCP ticket/product fields match
   `IncidentRecord` / `InventoryProduct` from `services/api` (`incident_id`,
   `location_id`, `category`, `ABIERTO|CERRADO|DESCARTADO`, `BRS-######`,
   `product_id`/`quantity`/`unit`, `source=incident_manager|inventory_manager`).
   Tools call `COMPANY_API_BASE` over HTTP; they do not replace the backends.
2. **Lifecycle status only** — `action=update` always calls
   `PATCH /api/incidents/{id}/status` via `http_clients.update_incident_status`.
   There is no generic `PATCH /api/incidents/{id}` helper.
2b. **Inventory queries + write rejection** — `query_inventory` correctly serves
   read actions (`list` / `get` / `query` / `read`) against the live inventory
   API (`product_id`, `name`, `quantity`, `unit`, `source=inventory_manager`).
   Any write action (`update|create|delete|write|patch|put`) or write field
   (`quantity` / `delta` / `unit` / `name`) returns
   **`INVENTORY_WRITE_FORBIDDEN`** (explicit reject, not a missing tool). The
   inventory HTTP client is GET-only. Confirmed by
   `test_inventory_query_and_write_rejection` and
   `test_inventory_mcp_query_and_write_rejection_over_tools_call`.
3. **OAuth via MCP Auth** — `mcpauth.MCPAuth` in **resource-server** mode with
   OIDC (`AuthServerType.OIDC`), provider-agnostic via `MCP_AUTH_ISSUER`.
   **Clients without a valid OAuth access token cannot list or execute any
   tool**: missing / garbage / wrong-audience Bearer → HTTP **401** on
   `tools/list`, `tools/call` (both `manage_incident_ticket` and
   `query_inventory`), and even `initialize`. Confirmed by
   `test_mandatory_oauth_blocks_unauthenticated_list_and_invoke` (+ invalid/
   wrong-audience cases). Least-privilege **`required_scopes`**:
   `incidents:read` / `incidents:manage` / `inventory:read` enforced per
   tool/action. Domain HTTP clients are split so inventory cannot call
   incident routes and vice versa (inventory is GET-only). FastMCP built-in
   auth is not used (`settings.auth is None`).

## Distinct error / exit codes

Auth, authorization, and validation failures use **named** codes (never a
generic `"error"`). See [`mcps/company_tools/ERRORS.md`](../mcps/company_tools/ERRORS.md):

- Authentication → `AUTH_MISSING_TOKEN` / `AUTH_INVALID_TOKEN` / `AUTH_INVALID_AUDIENCE` (HTTP 401)
- Authorization → `AUTH_INSUFFICIENT_SCOPE` / `INVENTORY_WRITE_FORBIDDEN`
- Validation → `VALIDATION_ERROR` / `LIFECYCLE_ERROR` / `NOT_FOUND`
- Process exits → `ExitCode` 0/1/2/3/4

The three categories are **pairwise distinct** in both `error_code` and
`message` (sampled live in
`test_auth_authz_validation_errors_have_distinct_codes_and_messages`).

## Invocation logging (tool + client + result)

Every MCP tool call is wrapped in `timed_call` and emits **≥1** JSON log line
(`event=tool_invocation`) with required fields `tool`, `client_id`, and
`result` (`success`|`error`). See [`mcps/company_tools/LOGGING.md`](../mcps/company_tools/LOGGING.md).
Confirmed by `test_every_tool_invocation_is_logged_with_tool_client_and_result`
(covers both tools, success and error paths).

## Agent migration (LangGraph → MCP)

- [x] Graph `lookup_ticket` node uses `lookup_ticket_via_mcp` +
  `langchain-mcp-adapters` (`MultiServerMCPClient` / Streamable HTTP).
- [x] Direct HTTP `lookup_ticket` deprecated and not re-exported from
  `services.agent.tools` — single path to Incidents Manager.
- [x] RAG vs tools routing (`decide_route`) unchanged; confirmed by
  `tests/pipelines/test_agent_mcp_migration.py`.

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
- Scopes: `incidents:read`, `incidents:manage`, `inventory:read`

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

**Localhost alone will not work** from MCP Playground. Expose/forward port
`3001` with **public** visibility (Codespaces forwarded URL or Cloudflare
Tunnel), mint a token (`GET /token?client_id=mcp-playground`), paste the
**public** `https://…/mcp` URL + `Authorization: Bearer …` into
[MCP Playground Connect](https://www.mcpplayground.tech/connect).

### Verified public connection + complete flows per tool

Connected Brasaland Company Tools via **public** Streamable HTTP URL + Bearer JWT
(not localhost). Ran one complete flow per exposed tool:

**`manage_incident_ticket`**
1. `create` → `BRS-000013` (`EQUIPAMIENTO`, `ABIERTO`, `COL-01`)
2. `get_status` → `ABIERTO`
3. `update` → `CERRADO` via lifecycle `PATCH /api/incidents/{id}/status`

**`query_inventory`**
1. `list` → products from live inventory (`Tomatoes`, `Mozzarella`, `Napkins`)
2. `action=update` → `INVENTORY_WRITE_FORBIDDEN`

Evidence (screenshots + JSON): [`docs/agent/playground/`](./playground/)
