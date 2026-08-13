# Error and exit codes — Brasaland Company Tools MCP

Clients **must not** treat failures as a generic `"error"`. Every failure is a
distinct machine-readable code so authentication, authorization, and validation
can be handled separately.

Canonical definitions live in [`errors.py`](./errors.py)
(`ErrorCode`, `ExitCode`, `ERROR_CATALOG`).

---

## 1. Tool result shape (after a valid MCP session)

Successful and failed tool calls return JSON (via MCP `tools/call` content).
Failures always look like:

```json
{
  "ok": false,
  "error_code": "AUTH_INSUFFICIENT_SCOPE",
  "message": "Token needs one of required_scopes: incidents:manage",
  "tool": "manage_incident_ticket",
  "details": { "required_scopes_any_of": ["incidents:manage"], "present": ["inventory:read"] }
}
```

| Field | Meaning |
| ----- | ------- |
| `ok` | Always `false` on failure |
| `error_code` | One of the catalog codes below — **never** `"error"` |
| `message` | Human-readable detail |
| `tool` | Tool name that produced the failure |
| `details` | Optional structured context (missing scopes, rejected fields, …) |

---

## 2. Catalog — authentication / authorization / validation

| `error_code` | Category | Typical HTTP | When |
| ------------ | -------- | ------------ | ---- |
| `AUTH_MISSING_TOKEN` | authentication | **401** | No `Authorization: Bearer` on `/mcp` |
| `AUTH_INVALID_TOKEN` | authentication | **401** | Malformed, expired, bad signature, wrong issuer |
| `AUTH_INVALID_AUDIENCE` | authentication | **401** | JWT `aud` ≠ `MCP_RESOURCE_ID` |
| `AUTH_INSUFFICIENT_SCOPE` | authorization | **403** / tool result | Token valid but missing `required_scopes` for the tool/action |
| `INVENTORY_WRITE_FORBIDDEN` | authorization | tool result | `query_inventory` write action or write field |
| `VALIDATION_ERROR` | validation | tool result | Bad/missing input; update with non-status fields |
| `LIFECYCLE_ERROR` | validation | tool result | Illegal incident status transition |
| `NOT_FOUND` | validation | tool result | Unknown `ticket_id` / `product_id` upstream |
| `UPSTREAM_ERROR` | upstream | tool result | Company API 5xx / unexpected HTTP failure |
| `UNHANDLED_ERROR` | internal | tool result | Unexpected exception in a tool handler |

### Authentication vs authorization

| Concern | Codes | Layer |
| ------- | ----- | ----- |
| **Authentication** — prove identity | `AUTH_MISSING_TOKEN`, `AUTH_INVALID_TOKEN`, `AUTH_INVALID_AUDIENCE` | MCP Auth bearer middleware on `/mcp` (request never reaches tools) |
| **Authorization** — least privilege | `AUTH_INSUFFICIENT_SCOPE`, `INVENTORY_WRITE_FORBIDDEN` | Per-tool `required_scopes` gate / write rejection |
| **Validation** — bad input / domain rules | `VALIDATION_ERROR`, `LIFECYCLE_ERROR`, `NOT_FOUND` | Tool + Incidents Manager lifecycle |

---

## 3. Transport layer (before tools run)

Unauthenticated or invalid Bearer requests never list or invoke tools. MCP Auth
middleware responds with **HTTP 401** and an OAuth-style body, for example:

```json
{
  "error": "missing_auth_header",
  "error_description": "Missing `Authorization` header. Please provide a valid bearer token."
}
```

Map the transport `error` field to our catalog:

| Transport `error` (MCP Auth / RFC 6750) | Catalog `error_code` | HTTP |
| --------------------------------------- | -------------------- | ---- |
| `missing_auth_header` / `invalid_request` | `AUTH_MISSING_TOKEN` | 401 |
| `invalid_token` | `AUTH_INVALID_TOKEN` (or `AUTH_INVALID_AUDIENCE` when `aud` mismatches) | 401 |
| `insufficient_scope` | `AUTH_INSUFFICIENT_SCOPE` | 403 |

Helper: `map_transport_oauth_error()` in `errors.py`.

`WWW-Authenticate` includes `resource_metadata` pointing at Protected Resource
Metadata so clients can discover the OIDC issuer and scopes.

---

## 4. Process exit codes (server / CI)

When starting the MCP process (`uvicorn` / `python -m mcps.company_tools`), use:

| Exit code | Name | When |
| --------- | ---- | ---- |
| `0` | `ExitCode.SUCCESS` | Process ended cleanly |
| `1` | `ExitCode.UNEXPECTED` | Uncaught exception |
| `2` | `ExitCode.CONFIG_ERROR` | Bad/missing config (e.g. FastMCP built-in auth enabled, invalid resource URL) |
| `3` | `ExitCode.AUTH_SETUP_ERROR` | Cannot load OIDC metadata / JWKS from `MCP_AUTH_ISSUER` |
| `4` | `ExitCode.VALIDATION_ERROR` | Invalid CLI/env values before listen |

These are **process** exit statuses for operators — distinct from tool
`error_code` strings returned to MCP clients.

---

## 5. Examples

**Missing token (transport):**

```http
POST /mcp HTTP/1.1
→ 401
{"error":"missing_auth_header","error_description":"…"}
```
→ catalog: `AUTH_MISSING_TOKEN`

**Valid inventory token calling incident create (authorization):**

```json
{
  "ok": false,
  "error_code": "AUTH_INSUFFICIENT_SCOPE",
  "message": "Token needs one of required_scopes: incidents:manage",
  "tool": "manage_incident_ticket"
}
```

**Write on read-only inventory (authorization):**

```json
{
  "ok": false,
  "error_code": "INVENTORY_WRITE_FORBIDDEN",
  "message": "Inventory tool is read-only. Write operations are not permitted on this MCP server.",
  "tool": "query_inventory"
}
```

**Update with non-status fields (validation):**

```json
{
  "ok": false,
  "error_code": "VALIDATION_ERROR",
  "message": "action=update only accepts ticket_id+status (lifecycle). Other fields are not allowed — least privilege.",
  "tool": "manage_incident_ticket",
  "details": { "rejected_fields": { "category": "EQUIPAMIENTO" } }
}
```
