# Brasaland Company Tools MCP Server

Exposes Incidents Manager ticket management and **read-only** inventory queries
over the Model Context Protocol, protected by **OAuth via [MCP Auth](https://mcp-auth.dev/)**
(`mcpauth`) — not FastMCP's built-in auth.

## Dependencies (`uv add` only)

Installed in the monorepo with **`uv add`** (never `pip install`):

```bash
uv add fastmcp "mcpauth>=0.2.0b1" "langchain-mcp-adapters>=0.1.0"
```

Also present: `mcp[cli]` (provides `mcp.server.fastmcp` used by the server), `pyjwt[crypto]`.

## Depends on existing backends (does not replace them)

The MCP server is a **thin OAuth-protected facade**. It never owns incident or
inventory data. Every tool call is an HTTP request to the company API already
built in previous milestones:

| MCP tool | Upstream service | Live routes |
| -------- | ---------------- | ----------- |
| `manage_incident_ticket` | Incidents Manager (`services/api`) | `POST /api/incidents`, `PATCH /api/incidents/{id}/status`, `GET /api/incidents/{id}` |
| `query_inventory` | Inventory module (`services/api/inventory.py` → `products.csv`) | `GET /inventory/products`, `GET /inventory/products/{id}` |

Implementation: `http_clients.py` → `httpx` → `COMPANY_API_BASE` (default
`http://127.0.0.1:8000`). No CSV reads, no parallel fake stores, no in-process
incident/inventory logic inside `mcps/`.

```text
MCP client ──OAuth──► mcps/company_tools ──HTTP──► services/api (Incidents + Inventory)
```

The company API **must be running** before the MCP server is useful.

## Transport

**Streamable HTTP** on port `3001` (path `/mcp`).

Chosen because the RFP requires remote clients (MCP Playground, other teams,
partners). stdio only works when one local process spawns the server; HTTP lets
multiple authenticated clients share one OAuth-protected resource server.

## Tools

| Tool | Scopes | Operations |
| ---- | ------ | ---------- |
| `manage_incident_ticket` | `incidents:manage` | `create`, `update` (via `PATCH /api/incidents/{id}/status`), `get_status` |
| `query_inventory` | `inventory:read` | read-only query; writes → `INVENTORY_WRITE_FORBIDDEN` |

Domain values match the live Company APIs: statuses `ABIERTO|CERRADO|DESCARTADO`,
categories `EQUIPAMIENTO|ABASTECIMIENTO|QUEJA_CLIENTE|CALIDAD_ALIMENTO|PERSONAL`,
ticket ids `BRS-######`, inventory `product_id`/`quantity`/`unit`.

Full discovery docs (name / description / input / output — MCP `--help`):
[`TOOLS.md`](./TOOLS.md) and [`docs/agent/mcp-tools-discovery.json`](../../docs/agent/mcp-tools-discovery.json).

## Auth (mandatory — MCP Auth resource-server mode)

Company tools are **not** exposed without OAuth. Prefer **MCP Auth** (`mcpauth`)
over FastMCP built-in auth so the flow matches the MCP Authorization spec.

| Concern | Implementation |
| ------- | -------------- |
| Mode | OAuth 2.1 **resource server** (`protected_resources` + PRM) |
| Protocol | **OIDC** metadata / JWKS via `MCP_AUTH_ISSUER` (provider-agnostic) |
| Transport gate | `bearer_auth_middleware("jwt", audience=resource)` on `/mcp` → HTTP 401 without a valid access token |
| Scopes | `incidents:manage`, `inventory:read` (advertised + enforced per tool) |
| Not used | FastMCP `AuthSettings` / built-in auth |

```bash
# Production / staging — point at Logto (or any OIDC provider)
export MCP_AUTH_ISSUER=https://your-tenant.logto.app/oidc
export MCP_RESOURCE_ID=https://mcp.brasaland.example/mcp
```

## Error codes

| Code | Meaning |
| ---- | ------- |
| `AUTH_MISSING_TOKEN` | No Bearer token (HTTP 401 from MCP Auth middleware) |
| `AUTH_INVALID_TOKEN` | Invalid / expired JWT (HTTP 401) |
| `AUTH_INSUFFICIENT_SCOPE` | Token lacks the tool's required scope |
| `INVENTORY_WRITE_FORBIDDEN` | Write attempt on read-only inventory tool |
| `VALIDATION_ERROR` | Bad tool input |
| `LIFECYCLE_ERROR` | Invalid incident status transition |
| `NOT_FOUND` | Ticket / product missing upstream |
| `UPSTREAM_ERROR` | Incidents / inventory API failure |

## Run locally

Prerequisites: company API on `:8000` (incidents + inventory).

```bash
# Terminal 1 — company API
uv run uvicorn services.api.app:app --port 8000

# Terminal 2 — local OIDC issuer (dev / tests; production uses Logto etc.)
export MCP_AUTH_ISSUER=http://127.0.0.1:3002
export MCP_RESOURCE_ID=http://127.0.0.1:3001/mcp
uv run uvicorn mcps.company_tools.dev_issuer:app --port 3002

# Terminal 3 — MCP server
uv run uvicorn mcps.company_tools.server:create_app --factory --host 0.0.0.0 --port 3001
```

Mint a token for Playground / agent:

```bash
curl -s 'http://127.0.0.1:3002/token?client_id=mcp-playground'
```

## MCP Playground

1. Forward port `3001` with **public** visibility (Codespaces / Cloudflare Tunnel).
2. Paste the public MCP URL (`https://…/mcp`) into [MCP Playground Connect](https://www.mcpplayground.tech/connect).
3. Add auth header `Authorization: Bearer <token>` from `GET /token?client_id=mcp-playground`.
4. Confirm tools `manage_incident_ticket` and `query_inventory`, then exercise each once; try `query_inventory` with `action=update` and confirm `INVENTORY_WRITE_FORBIDDEN`.

Verified screenshots: [`docs/agent/playground/`](../../docs/agent/playground/).

## Agent migration

The LangGraph support agent loads incident tools via `langchain-mcp-adapters`
(`services/agent/tools/mcp_incidents.py`). Direct HTTP ticket lookup is
deprecated and no longer used by the graph.
