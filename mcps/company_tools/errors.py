"""Distinct error codes for the company-tools MCP server."""

from __future__ import annotations

from typing import Any


class ErrorCode:
    AUTH_MISSING_TOKEN = "AUTH_MISSING_TOKEN"
    AUTH_INVALID_TOKEN = "AUTH_INVALID_TOKEN"
    AUTH_INSUFFICIENT_SCOPE = "AUTH_INSUFFICIENT_SCOPE"
    INVENTORY_WRITE_FORBIDDEN = "INVENTORY_WRITE_FORBIDDEN"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    LIFECYCLE_ERROR = "LIFECYCLE_ERROR"


def error_payload(
    error_code: str,
    message: str,
    *,
    tool: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured, non-generic error body for MCP tool results."""
    payload: dict[str, Any] = {
        "ok": False,
        "error_code": error_code,
        "message": message,
    }
    if tool:
        payload["tool"] = tool
    if details:
        payload["details"] = details
    return payload
