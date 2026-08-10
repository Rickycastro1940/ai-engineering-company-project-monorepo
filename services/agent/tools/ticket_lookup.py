"""DEPRECATED for LangGraph graph use — prefer MCP client path.

.. deprecated::
    The support agent must call Incidents Manager through the company-tools
    MCP server (``services.agent.tools.mcp_incidents``) via
    ``langchain-mcp-adapters``. This module remains only for formatting helpers
    and historical direct-HTTP reference; ``lookup_ticket`` must not be wired
    into the compiled graph.

Read-only ticket lookup tool — HTTP only against the live incident manager.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from services.agent.tools.contracts import (
    TicketLookupInput,
    TicketLookupOutput,
    TicketRecord,
)

# Explicit numeric timeout (seconds) — Part 2 acceptance criterion.
# If the incident manager does not respond in time, the call aborts and the
# graph takes the ticket_fallback path instead of hanging.
TICKET_LOOKUP_TIMEOUT_SECONDS: float = 5.0


def build_ticket_http_timeout(seconds: float = TICKET_LOOKUP_TIMEOUT_SECONDS) -> httpx.Timeout:
    """Build an explicit httpx Timeout for connect / read / write / pool.

    A single float is not enough for reviewers to see the contract; this makes
    every phase of the HTTP call bound to the same numeric limit.
    """
    limit = float(seconds)
    if limit <= 0:
        raise ValueError("ticket lookup timeout must be a positive number of seconds")
    return httpx.Timeout(limit, connect=limit, read=limit, write=limit, pool=limit)

# Live incident manager base URL (override with INCIDENT_API_BASE in deploy).
DEFAULT_INCIDENT_API_BASE = "http://127.0.0.1:8000"

# Paths on the existing incident manager — the only URLs this tool may call.
INCIDENTS_LIST_PATH = "/api/incidents"
INCIDENT_BY_ID_PATH_TEMPLATE = "/api/incidents/{incident_id}"

# Honest fallback when the tool times out, errors, or the ticket does not exist.
# Never invent a status / category / date — this exact phrase is the recovery answer.
TICKET_FALLBACK_MESSAGE = (
    "I couldn't confirm that ticket's status right now. "
    "Please try again shortly or check the incident manager directly."
)

# Status values that must never appear in a fallback answer (would imply invention).
_INVENTED_STATUS_MARKERS = (
    "status=abierto",
    "status=cerrado",
    "status=descartado",
    "status: abierto",
    "status: cerrado",
    "status: descartado",
)


def _incident_api_base() -> str:
    return (os.getenv("INCIDENT_API_BASE") or DEFAULT_INCIDENT_API_BASE).rstrip("/")


def _auth_headers() -> dict[str, str]:
    """Optional backend-to-backend auth from env (none required today)."""
    headers: dict[str, str] = {"Accept": "application/json"}
    token = os.getenv("INCIDENT_API_TOKEN") or os.getenv("INCIDENT_API_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _record_from_payload(payload: dict[str, Any]) -> TicketRecord:
    """Map an incident-manager JSON body to the typed tool output record."""
    return TicketRecord(
        incident_id=str(payload.get("incident_id") or ""),
        date=str(payload.get("date") or ""),
        location_id=payload.get("location_id"),
        category=str(payload.get("category") or ""),
        description=str(payload.get("description") or ""),
        status=str(payload.get("status") or ""),
        customer_id=payload.get("customer_id"),
        satisfaction_score=payload.get("satisfaction_score"),
        reporter_id=payload.get("reporter_id"),
        source=str(payload.get("source") or "incident_manager"),
    )


def format_ticket_answer(output: TicketLookupOutput) -> str:
    """Render an honest natural-language answer from a tool result (no invention).

    On any failure (timeout, service error, missing ticket) returns
    ``TICKET_FALLBACK_MESSAGE`` — never a made-up status/category/date.
    """
    if not output.ok:
        return honest_ticket_fallback_answer(output)

    if not output.tickets:
        return honest_ticket_fallback_answer(output)

    lines: list[str] = []
    for ticket in output.tickets:
        lines.append(
            f"Ticket {ticket.incident_id}: status={ticket.status}, "
            f"category={ticket.category}, date={ticket.date}, "
            f"location={ticket.location_id or 'n/a'}, "
            f"source={ticket.source}. "
            f"Description: {ticket.description}"
        )
    return "\n".join(lines)


def honest_ticket_fallback_answer(output: TicketLookupOutput | None = None) -> str:
    """Canonical fallback text when the tool fails or the ticket does not exist.

    Always includes ``I couldn't confirm that ticket's status right now``.
    Never fabricates ABIERTO / CERRADO / DESCARTADO (or any other status).
    """
    base = TICKET_FALLBACK_MESSAGE
    if output is not None and output.error == "not_found":
        # Keep the required honest phrase; optionally name the missing id.
        detail = (output.message or "").strip()
        if detail and "couldn't confirm" not in detail.casefold():
            # Prefixed so the course-required phrase is always present.
            answer = f"{TICKET_FALLBACK_MESSAGE} {detail}"
        else:
            answer = detail or base
    else:
        answer = (output.message if output and output.message else None) or base
        if "couldn't confirm" not in answer.casefold():
            answer = TICKET_FALLBACK_MESSAGE

    lowered = answer.casefold()
    for marker in _INVENTED_STATUS_MARKERS:
        if marker in lowered:
            return TICKET_FALLBACK_MESSAGE
    return answer


def _failed(
    started: float,
    *,
    error: str,
    message: str,
) -> TicketLookupOutput:
    return TicketLookupOutput(
        ok=False,
        tickets=[],
        error=error,  # type: ignore[arg-type]
        message=message,
        duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
    )


def lookup_ticket(
    query: TicketLookupInput | dict[str, Any],
    *,
    base_url: str | None = None,
    timeout_seconds: float = TICKET_LOOKUP_TIMEOUT_SECONDS,
    transport: httpx.BaseTransport | None = None,
) -> TicketLookupOutput:
    """Call the incident manager via GET only. Never creates/updates/deletes.

    Always reads responses from ``GET /api/incidents`` or
    ``GET /api/incidents/{id}`` on the incident manager. This module does not
    contain ticket rows — if the service is down, the tool fails honestly.

    Parameters
    ----------
    query:
        Typed ``TicketLookupInput`` (or dict matching that schema).
    base_url:
        Incident manager origin; defaults to ``INCIDENT_API_BASE`` / localhost:8000.
    timeout_seconds:
        Explicit numeric HTTP timeout in seconds (default
        ``TICKET_LOOKUP_TIMEOUT_SECONDS`` = 5). Applied to connect/read/write/pool
        so a silent incident service cannot hang the graph.
    transport:
        Optional httpx transport for tests (``MockTransport`` against the real
        FastAPI app). Leave unset in production so traffic hits the running
        incident manager over the network.
    """
    started = time.perf_counter()
    try:
        if isinstance(query, dict):
            inp = TicketLookupInput.model_validate(query)
        else:
            inp = query
    except Exception as exc:  # noqa: BLE001
        return _failed(
            started,
            error="invalid_input",
            message=f"Invalid ticket lookup input: {exc}",
        )

    root = (base_url or _incident_api_base()).rstrip("/")
    headers = _auth_headers()
    http_timeout = build_ticket_http_timeout(timeout_seconds)

    try:
        with httpx.Client(
            base_url=root,
            timeout=http_timeout,
            transport=transport,
            headers=headers,
        ) as client:
            if inp.ticket_id:
                ticket_id = inp.ticket_id.strip()
                path = INCIDENT_BY_ID_PATH_TEMPLATE.format(incident_id=ticket_id)
                response = client.get(path)
                if response.status_code == 404:
                    return _failed(
                        started,
                        error="not_found",
                        message=(
                            f"{TICKET_FALLBACK_MESSAGE} "
                            f"Ticket {ticket_id} was not found in the incident manager."
                        ),
                    )
                if response.status_code in (401, 403):
                    return _failed(started, error="auth_error", message=TICKET_FALLBACK_MESSAGE)
                if response.status_code >= 400:
                    return _failed(started, error="service_error", message=TICKET_FALLBACK_MESSAGE)
                payload = response.json()
                ticket = _record_from_payload(payload if isinstance(payload, dict) else {})
                return TicketLookupOutput(
                    ok=True,
                    tickets=[ticket],
                    error=None,
                    message=None,
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                )

            params: dict[str, str] = {}
            if inp.status:
                params["status"] = inp.status
            if inp.category:
                params["category"] = inp.category
            if inp.location_id:
                params["location_id"] = inp.location_id
            if inp.date_from:
                params["date_from"] = inp.date_from
            if inp.date_to:
                params["date_to"] = inp.date_to

            response = client.get(INCIDENTS_LIST_PATH, params=params or None)
            if response.status_code in (401, 403):
                return _failed(started, error="auth_error", message=TICKET_FALLBACK_MESSAGE)
            if response.status_code >= 400:
                return _failed(started, error="service_error", message=TICKET_FALLBACK_MESSAGE)

            payload = response.json()
            items = payload if isinstance(payload, list) else payload.get("incidents", [])
            tickets = [_record_from_payload(item) for item in items if isinstance(item, dict)]
            return TicketLookupOutput(
                ok=True,
                tickets=tickets,
                error=None,
                message=None if tickets else "No tickets matched those filters.",
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
            )
    except httpx.TimeoutException:
        return _failed(started, error="timeout", message=TICKET_FALLBACK_MESSAGE)
    except Exception:  # noqa: BLE001
        return _failed(started, error="service_error", message=TICKET_FALLBACK_MESSAGE)
