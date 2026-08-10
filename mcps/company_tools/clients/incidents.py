"""Least-privilege HTTP client for the Incidents Manager only.

Exposes only the operations ``manage_incident_ticket`` needs:
``GET`` by id, ``POST`` create, and lifecycle ``PATCH .../status``.
Does not include inventory routes or a generic incident PATCH.
"""

from __future__ import annotations

from typing import Any

import httpx

from mcps.company_tools.clients.base import api_base, build_timeout, json_headers

INCIDENTS_COLLECTION_PATH = "/api/incidents"
INCIDENT_BY_ID_PATH = "/api/incidents/{incident_id}"
INCIDENT_STATUS_PATH = "/api/incidents/{incident_id}/status"

# Fields accepted on create — mirrors IncidentCreateInput (no extras).
CREATE_ALLOWED_FIELDS = frozenset(
    {
        "category",
        "description",
        "status",
        "date",
        "location_id",
        "customer_id",
        "satisfaction_score",
        "reporter_id",
    }
)


def get_incident(ticket_id: str, *, base_url: str | None = None) -> httpx.Response:
    """Read a single ticket by id (no collection list)."""
    root = (base_url or api_base()).rstrip("/")
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=json_headers()) as client:
        return client.get(INCIDENT_BY_ID_PATH.format(incident_id=ticket_id))


def create_incident(payload: dict[str, Any], *, base_url: str | None = None) -> httpx.Response:
    """Create a ticket — only IncidentCreateInput keys are forwarded."""
    body = {k: v for k, v in payload.items() if k in CREATE_ALLOWED_FIELDS and v is not None}
    root = (base_url or api_base()).rstrip("/")
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=json_headers()) as client:
        return client.post(INCIDENTS_COLLECTION_PATH, json=body)


def update_incident_status(
    ticket_id: str,
    status: str,
    *,
    base_url: str | None = None,
) -> httpx.Response:
    """Status changes MUST use the lifecycle endpoint, not a generic PATCH."""
    root = (base_url or api_base()).rstrip("/")
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=json_headers()) as client:
        return client.patch(
            INCIDENT_STATUS_PATH.format(incident_id=ticket_id),
            json={"status": status},  # status only — least privilege
        )
