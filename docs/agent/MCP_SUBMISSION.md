# MCP Server — Company Tools (submission notes)

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

## How to run

See `mcps/company_tools/README.md`.

## Playground

Forward port `3001` with **public** visibility (Codespaces), mint a token from
the issuer (`GET /token`), paste the public URL + Bearer token into
[MCP Playground](https://www.mcpplayground.tech/playground).
