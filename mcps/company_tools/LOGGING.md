# Invocation logging — Brasaland Company Tools MCP

Every tool invocation is logged for traceability: **which tool**, **which
client**, and **what result**.

Implementation: [`logging_util.py`](./logging_util.py) (`timed_call` wraps both
MCP tools in [`server.py`](./server.py)).

## Logger

| | |
| --- | --- |
| Name | `mcps.company_tools.invocations` |
| Level | `INFO` |
| Format | One JSON object per line |

## Required fields

| Field | Meaning |
| ----- | ------- |
| `event` | Always `tool_invocation` |
| `timestamp` | UTC ISO-8601 |
| `tool` | `manage_incident_ticket` or `query_inventory` |
| `client_id` | OAuth `client_id` (or `sub` / `anonymous`) from the Bearer token |
| `subject` | JWT `sub` when present |
| `scopes` | Token scopes at call time |
| `input_summary` | Non-sensitive inputs (e.g. `action`, `ticket_id`, `product_id`) |
| `result` | `success` or `error` |
| `error_code` | Catalog code when `result` is `error` (see [`ERRORS.md`](./ERRORS.md)) |
| `result_summary` | Compact outcome (`ok`, `incident_id`, `product_count`, …) |
| `duration_ms` | Handler latency |

Auth denials (`AUTH_INSUFFICIENT_SCOPE`) and validation failures are logged as
`result=error` with the distinct `error_code` — never a generic `"error"` code.

## Example

```json
{
  "event": "tool_invocation",
  "timestamp": "2026-08-10T18:45:01.123456Z",
  "tool": "manage_incident_ticket",
  "client_id": "mcp-playground",
  "subject": "agent-support",
  "scopes": ["incidents:manage", "inventory:read"],
  "input_summary": {"action": "update", "ticket_id": "BRS-000011"},
  "result": "success",
  "result_summary": {"ok": true, "action": "update", "incident_id": "BRS-000011", "status": "CERRADO"},
  "duration_ms": 18
}
```

```json
{
  "event": "tool_invocation",
  "timestamp": "2026-08-10T18:45:02.000000Z",
  "tool": "query_inventory",
  "client_id": "inv-only",
  "subject": "agent-support",
  "scopes": ["inventory:read"],
  "input_summary": {"action": "update", "product_id": "1", "name_contains": null},
  "result": "error",
  "error_code": "INVENTORY_WRITE_FORBIDDEN",
  "result_summary": {"ok": false, "error_code": "INVENTORY_WRITE_FORBIDDEN"},
  "duration_ms": 1
}
```
