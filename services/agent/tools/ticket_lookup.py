"""Read-only ticket lookup tool — HTTP only against the live incident manager.

Data source (non-negotiable)
---------------------------
This tool **only** issues:

- ``GET {base}/api/incidents``
- ``GET {base}/api/incidents/{id}``

against the company's existing incident manager service. Ticket fields come
from that response — never from a parallel fake dataset, hardcoded ticket
table, or invented status/category/date values.

Auth
----
The Brasaland incident manager currently has **no authentication** on those
GETs. If auth is added later, pass credentials via env
(``INCIDENT_API_TOKEN`` / ``INCIDENT_API_KEY``) — never hardcode a token.

Timeout
-------
Every call uses an explicit numeric timeout of ``TICKET_LOOKUP_TIMEOUT_SECONDS``
(5 seconds). On timeout / error / not-found the tool returns a structured
``TicketLookupOutput`` with ``ok=False`` — the graph must never invent a status.
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

# Explicit numeric timeout required by Part 2 acceptance criteria.
TICKET_LOOKUP_TIMEOUT_SECONDS: float = 5.0

# Live incident manager base URL (override with INCIDENT_API_BASE in deploy).
DEFAULT_INCIDENT_API_BASE = "http://127.0.0.1:8000"

# Paths on the existing incident manager — the only URLs this tool may call.
INCIDENTS_LIST_PATH = "/api/incidents"
INCIDENT_BY_ID_PATH_TEMPLATE = "/api/incidents/{incident_id}"

TICKET_FALLBACK_MESSAGE = (
    "I couldn't confirm that ticket's status right now. "
    "Please try again shortly or check the incident manager directly."
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
    """Render an honest natural-language answer from a tool result (no invention)."""
    if not output.ok:
        if output.error == "not_found":
            return (
                output.message
                or "I could not find that ticket in the incident manager."
            )
        return output.message or TICKET_FALLBACK_MESSAGE

    if not output.tickets:
        return "No tickets matched those filters in the incident manager."

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
        Explicit numeric HTTP timeout (default 5s).
    transport:
        Optional httpx transport for tests (``MockTransport`` / ``ASGITransport``
        against the real FastAPI app). Leave unset in production so traffic hits
        the running incident manager over the network.
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

    try:
        with httpx.Client(
            base_url=root,
            timeout=timeout_seconds,
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
                            f"I could not find ticket {ticket_id} "
                            "in the incident manager."
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
