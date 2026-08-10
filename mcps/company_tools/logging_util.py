"""Structured invocation logging for every MCP tool call (traceability).

Every tool invocation emits one JSON log line with at least:

* ``tool`` — which tool ran
* ``client_id`` — which OAuth client (from the Bearer token)
* ``result`` — ``success`` or ``error`` (never a bare generic dump)
* ``error_code`` — distinct catalog code when ``result`` is ``error``

Logger name: ``mcps.company_tools.invocations`` (INFO).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, Callable

from mcpauth import MCPAuth

from mcps.company_tools.errors import ErrorCode

INVOCATION_LOGGER_NAME = "mcps.company_tools.invocations"
logger = logging.getLogger(INVOCATION_LOGGER_NAME)

# Ensure invocation logs are visible even if the app root logger is quiet.
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = True


def client_id_from_auth(mcp_auth: MCPAuth) -> str:
    info = mcp_auth.auth_info
    if info is None:
        return "anonymous"
    return info.client_id or info.subject or "unknown-client"


def _auth_trace(mcp_auth: MCPAuth) -> dict[str, Any]:
    info = mcp_auth.auth_info
    if info is None:
        return {
            "client_id": "anonymous",
            "subject": None,
            "scopes": [],
        }
    return {
        "client_id": info.client_id or info.subject or "unknown-client",
        "subject": info.subject,
        "scopes": list(info.scopes or []),
    }


def _result_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Compact, non-sensitive outcome for logs (no full ticket/product bodies)."""
    summary: dict[str, Any] = {"ok": bool(payload.get("ok", False))}
    if payload.get("action") is not None:
        summary["action"] = payload.get("action")
    if payload.get("error_code"):
        summary["error_code"] = payload.get("error_code")
    ticket = payload.get("ticket")
    if isinstance(ticket, dict) and ticket.get("incident_id"):
        summary["incident_id"] = ticket.get("incident_id")
        if ticket.get("status") is not None:
            summary["status"] = ticket.get("status")
    products = payload.get("products")
    if isinstance(products, list):
        summary["product_count"] = len(products)
    return summary


def log_invocation(
    *,
    tool: str,
    client_id: str,
    input_summary: dict[str, Any],
    result: str,
    duration_ms: int,
    error_code: str | None = None,
    subject: str | None = None,
    scopes: list[str] | None = None,
    result_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit one structured invocation log line and return the entry."""
    if result not in {"success", "error"}:
        raise ValueError(f"result must be 'success' or 'error', got {result!r}")
    entry: dict[str, Any] = {
        "event": "tool_invocation",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "tool": tool,
        "client_id": client_id,
        "subject": subject,
        "scopes": list(scopes or []),
        "input_summary": input_summary,
        "result": result,
        "duration_ms": duration_ms,
    }
    if error_code:
        entry["error_code"] = error_code
    if result_summary is not None:
        entry["result_summary"] = result_summary
    logger.info(json.dumps(entry, ensure_ascii=True, default=str))
    return entry


def timed_call(
    *,
    tool: str,
    mcp_auth: MCPAuth,
    input_summary: dict[str, Any],
    fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Run ``fn`` and **always** log tool / client / result for traceability."""
    started = time.perf_counter()
    auth_trace = _auth_trace(mcp_auth)
    client_id = auth_trace["client_id"]
    try:
        payload = fn()
    except Exception as exc:  # noqa: BLE001
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        log_invocation(
            tool=tool,
            client_id=client_id,
            subject=auth_trace.get("subject"),
            scopes=auth_trace.get("scopes") or [],
            input_summary=input_summary,
            result="error",
            duration_ms=duration_ms,
            error_code=ErrorCode.UNHANDLED_ERROR,
            result_summary={"ok": False, "error_code": ErrorCode.UNHANDLED_ERROR},
        )
        raise exc

    duration_ms = max(0, int((time.perf_counter() - started) * 1000))
    ok = bool(payload.get("ok", True)) and payload.get("error_code") is None
    error_code = None if ok else str(payload.get("error_code") or ErrorCode.UNHANDLED_ERROR)
    log_invocation(
        tool=tool,
        client_id=client_id,
        subject=auth_trace.get("subject"),
        scopes=auth_trace.get("scopes") or [],
        input_summary=input_summary,
        result="success" if ok else "error",
        duration_ms=duration_ms,
        error_code=error_code,
        result_summary=_result_summary(payload),
    )
    if "duration_ms" not in payload:
        payload = {**payload, "duration_ms": duration_ms}
    return payload
