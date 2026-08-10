# Brasaland Company Tools MCP Server

Exposes Incidents Manager ticket management and **read-only** inventory queries
over the Model Context Protocol, protected by **OAuth via [MCP Auth](https://mcp-auth.dev/)**
(`mcpauth`) — not FastMCP's built-in auth.

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

1. Forward port `3001` with **public** visibility (Codespaces) or expose the host.
2. Paste the public base URL into [MCP Playground](https://www.mcpplayground.tech/playground).
3. Connect with a Bearer access token from the issuer.
4. Exercise each tool once; try `query_inventory` with `action=update` and confirm `INVENTORY_WRITE_FORBIDDEN`.

## Agent migration

The LangGraph support agent loads incident tools via `langchain-mcp-adapters`
(`services/agent/tools/mcp_incidents.py`). Direct HTTP ticket lookup is
deprecated and no longer used by the graph.
