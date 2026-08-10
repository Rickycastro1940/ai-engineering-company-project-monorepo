"""Structured invocation logging for MCP tool calls."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, Callable

from mcpauth import MCPAuth

logger = logging.getLogger("mcps.company_tools")


def client_id_from_auth(mcp_auth: MCPAuth) -> str:
    info = mcp_auth.auth_info
    if info is None:
        return "anonymous"
    return info.client_id or info.subject or "unknown-client"


def log_invocation(
    *,
    tool: str,
    client_id: str,
    input_summary: dict[str, Any],
    result: str,
    duration_ms: int,
    error_code: str | None = None,
) -> None:
    entry = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "client_id": client_id,
        "tool": tool,
        "input_summary": input_summary,
        "result": result,
        "duration_ms": duration_ms,
    }
    if error_code:
        entry["error_code"] = error_code
    logger.info(json.dumps(entry, ensure_ascii=True, default=str))


def timed_call(
    *,
    tool: str,
    mcp_auth: MCPAuth,
    input_summary: dict[str, Any],
    fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Run ``fn``, emit one structured log line, and return its result."""
    started = time.perf_counter()
    client_id = client_id_from_auth(mcp_auth)
    try:
        payload = fn()
    except Exception as exc:  # noqa: BLE001
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        log_invocation(
            tool=tool,
            client_id=client_id,
            input_summary=input_summary,
            result="error",
            duration_ms=duration_ms,
            error_code="UNHANDLED_ERROR",
        )
        raise exc

    duration_ms = max(0, int((time.perf_counter() - started) * 1000))
    ok = bool(payload.get("ok", True)) and "error_code" not in payload
    log_invocation(
        tool=tool,
        client_id=client_id,
        input_summary=input_summary,
        result="success" if ok else "error",
        duration_ms=duration_ms,
        error_code=None if ok else str(payload.get("error_code")),
    )
    if "duration_ms" not in payload:
        payload = {**payload, "duration_ms": duration_ms}
    return payload
