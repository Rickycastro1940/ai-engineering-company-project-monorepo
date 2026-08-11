"""Distinct error and exit codes for the company-tools MCP server.

Never return a generic ``"error"`` string as ``error_code``. Clients must be
able to branch on authentication, authorization, and validation failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Final


class ErrorCode:
    """Machine-readable tool / protocol failure codes (string constants)."""

    # --- Authentication (who are you?) — usually HTTP 401 at the transport ---
    AUTH_MISSING_TOKEN = "AUTH_MISSING_TOKEN"
    AUTH_INVALID_TOKEN = "AUTH_INVALID_TOKEN"
    AUTH_INVALID_AUDIENCE = "AUTH_INVALID_AUDIENCE"

    # --- Authorization (what may you do?) — tool result or HTTP 403 ----------
    AUTH_INSUFFICIENT_SCOPE = "AUTH_INSUFFICIENT_SCOPE"
    INVENTORY_WRITE_FORBIDDEN = "INVENTORY_WRITE_FORBIDDEN"

    # --- Validation (bad input / domain rules) ------------------------------
    VALIDATION_ERROR = "VALIDATION_ERROR"
    LIFECYCLE_ERROR = "LIFECYCLE_ERROR"
    NOT_FOUND = "NOT_FOUND"

    # --- Upstream / unexpected ----------------------------------------------
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    UNHANDLED_ERROR = "UNHANDLED_ERROR"


class ExitCode(IntEnum):
    """Process exit codes for the MCP server / helpers (shell / CI)."""

    SUCCESS = 0
    UNEXPECTED = 1
    CONFIG_ERROR = 2  # missing issuer, bad MCP_RESOURCE_ID, FastMCP auth enabled
    AUTH_SETUP_ERROR = 3  # cannot fetch OIDC metadata / JWKS from MCP_AUTH_ISSUER
    VALIDATION_ERROR = 4  # invalid CLI / env values before listen


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    """Catalog entry for one distinct failure code."""

    code: str
    category: str  # authentication | authorization | validation | upstream | internal
    http_status: int | None
    when: str
    oauth_transport_error: str | None = None  # MCP Auth / RFC 6750 body ``error`` if any


ERROR_CATALOG: Final[tuple[ErrorSpec, ...]] = (
    ErrorSpec(
        code=ErrorCode.AUTH_MISSING_TOKEN,
        category="authentication",
        http_status=401,
        when="No Authorization header or empty Bearer token on /mcp.",
        oauth_transport_error="missing_auth_header",
    ),
    ErrorSpec(
        code=ErrorCode.AUTH_INVALID_TOKEN,
        category="authentication",
        http_status=401,
        when="Malformed, expired, bad-signature, or wrong-issuer JWT.",
        oauth_transport_error="invalid_token",
    ),
    ErrorSpec(
        code=ErrorCode.AUTH_INVALID_AUDIENCE,
        category="authentication",
        http_status=401,
        when="JWT aud does not match MCP_RESOURCE_ID (resource indicator).",
        oauth_transport_error="invalid_token",
    ),
    ErrorSpec(
        code=ErrorCode.AUTH_INSUFFICIENT_SCOPE,
        category="authorization",
        http_status=403,
        when="Token is valid but missing required_scopes for the tool/action.",
        oauth_transport_error="insufficient_scope",
    ),
    ErrorSpec(
        code=ErrorCode.INVENTORY_WRITE_FORBIDDEN,
        category="authorization",
        http_status=403,
        when="query_inventory received a write action or write field.",
        oauth_transport_error=None,
    ),
    ErrorSpec(
        code=ErrorCode.VALIDATION_ERROR,
        category="validation",
        http_status=400,
        when="Tool input fails schema / required fields / least-privilege field rules.",
        oauth_transport_error=None,
    ),
    ErrorSpec(
        code=ErrorCode.LIFECYCLE_ERROR,
        category="validation",
        http_status=400,
        when="Incident status transition rejected by Incidents Manager lifecycle.",
        oauth_transport_error=None,
    ),
    ErrorSpec(
        code=ErrorCode.NOT_FOUND,
        category="validation",
        http_status=404,
        when="Ticket or product id not found in the Company API.",
        oauth_transport_error=None,
    ),
    ErrorSpec(
        code=ErrorCode.UPSTREAM_ERROR,
        category="upstream",
        http_status=502,
        when="Incidents Manager or inventory HTTP API failed (5xx / unexpected).",
        oauth_transport_error=None,
    ),
    ErrorSpec(
        code=ErrorCode.UNHANDLED_ERROR,
        category="internal",
        http_status=500,
        when="Unexpected exception inside a tool handler.",
        oauth_transport_error=None,
    ),
)

# MCP Auth middleware ``error`` field → our catalog code (transport layer).
TRANSPORT_OAUTH_ERROR_TO_CODE: Final[dict[str, str]] = {
    "missing_auth_header": ErrorCode.AUTH_MISSING_TOKEN,
    "invalid_request": ErrorCode.AUTH_MISSING_TOKEN,
    "invalid_token": ErrorCode.AUTH_INVALID_TOKEN,
    "insufficient_scope": ErrorCode.AUTH_INSUFFICIENT_SCOPE,
}

ALL_ERROR_CODES: Final[frozenset[str]] = frozenset(spec.code for spec in ERROR_CATALOG)

# Forbidden generic labels — must never appear as error_code.
FORBIDDEN_GENERIC_CODES: Final[frozenset[str]] = frozenset(
    {"error", "Error", "ERROR", "err", "failure", "failed", "unknown"}
)


def error_payload(
    error_code: str,
    message: str,
    *,
    tool: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured, non-generic error body for MCP tool results."""
    if error_code in FORBIDDEN_GENERIC_CODES:
        raise ValueError(f"Refusing generic error_code={error_code!r}; use ErrorCode.*")
    if error_code not in ALL_ERROR_CODES:
        raise ValueError(f"Unknown error_code={error_code!r}; add it to ERROR_CATALOG")
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


def map_transport_oauth_error(oauth_error: str | None) -> str:
    """Map MCP Auth / RFC 6750 transport ``error`` to a catalog ``ErrorCode``."""
    if not oauth_error:
        return ErrorCode.AUTH_INVALID_TOKEN
    return TRANSPORT_OAUTH_ERROR_TO_CODE.get(oauth_error, ErrorCode.AUTH_INVALID_TOKEN)
