"""Incident ticket management tool — create / update status / get_status."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mcps.company_tools.clients import incidents as incident_client
from mcps.company_tools.errors import ErrorCode, error_payload

TOOL_NAME = "manage_incident_ticket"
Action = Literal["create", "update", "get_status"]


class ManageIncidentInput(BaseModel):
    """Input schema published via MCP discovery (self-explanatory)."""

    model_config = ConfigDict(extra="forbid")

    action: Action = Field(
        description=(
            "create: open a new ticket; update: change status via the Incidents "
            "Manager lifecycle endpoint; get_status: look up one ticket by id."
        )
    )
    ticket_id: str | None = Field(
        default=None,
        description="Required for update and get_status (e.g. BRS-000002).",
    )
    category: str | None = Field(
        default=None,
        description=(
            "Required for create. Must match Incidents Manager categories: "
            "EQUIPAMIENTO | ABASTECIMIENTO | QUEJA_CLIENTE | CALIDAD_ALIMENTO | PERSONAL."
        ),
    )
    description: str | None = Field(
        default=None,
        description="Required for create. Short description of the incident.",
    )
    status: str | None = Field(
        default=None,
        description=(
            "For create: initial status (default ABIERTO). For update: target status only "
            "(ABIERTO | CERRADO | DESCARTADO). Updates go through PATCH /api/incidents/{id}/status."
        ),
    )
    date: str | None = Field(default=None, description="Optional ISO date for create (YYYY-MM-DD).")
    location_id: str | None = Field(default=None, description="Optional location id (e.g. COL-01).")
    customer_id: str | None = Field(default=None, description="Optional customer id.")
    satisfaction_score: float | None = Field(
        default=None,
        description="Optional satisfaction score forwarded to POST /api/incidents.",
    )
    reporter_id: str | None = Field(default=None, description="Optional reporter id.")


def _ticket_from_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "incident_id": payload.get("incident_id"),
        "date": payload.get("date"),
        "location_id": payload.get("location_id"),
        "category": payload.get("category"),
        "description": payload.get("description"),
        "status": payload.get("status"),
        "customer_id": payload.get("customer_id"),
        "satisfaction_score": payload.get("satisfaction_score"),
        "reporter_id": payload.get("reporter_id"),
        "source": payload.get("source", "incident_manager"),
    }


def manage_incident_ticket(
    *,
    action: Action,
    ticket_id: str | None = None,
    category: str | None = None,
    description: str | None = None,
    status: str | None = None,
    date: str | None = None,
    location_id: str | None = None,
    customer_id: str | None = None,
    satisfaction_score: float | None = None,
    reporter_id: str | None = None,
) -> dict[str, Any]:
    """Execute create / update / get_status against the live Incidents Manager."""
    try:
        inp = ManageIncidentInput(
            action=action,
            ticket_id=ticket_id,
            category=category,
            description=description,
            status=status,
            date=date,
            location_id=location_id,
            customer_id=customer_id,
            satisfaction_score=satisfaction_score,
            reporter_id=reporter_id,
        )
    except Exception as exc:  # noqa: BLE001
        return error_payload(
            ErrorCode.VALIDATION_ERROR,
            f"Invalid manage_incident_ticket input: {exc}",
            tool=TOOL_NAME,
        )

    if inp.action == "get_status":
        if not inp.ticket_id:
            return error_payload(
                ErrorCode.VALIDATION_ERROR,
                "ticket_id is required for action=get_status",
                tool=TOOL_NAME,
            )
        response = incident_client.get_incident(inp.ticket_id)
        if response.status_code == 404:
            return error_payload(
                ErrorCode.NOT_FOUND,
                f"Ticket {inp.ticket_id} was not found in the Incidents Manager.",
                tool=TOOL_NAME,
            )
        if response.status_code >= 400:
            return error_payload(
                ErrorCode.UPSTREAM_ERROR,
                f"Incidents Manager returned HTTP {response.status_code}.",
                tool=TOOL_NAME,
            )
        return {"ok": True, "action": "get_status", "ticket": _ticket_from_response(response.json())}

    if inp.action == "create":
        if not inp.category or not inp.description:
            return error_payload(
                ErrorCode.VALIDATION_ERROR,
                "category and description are required for action=create",
                tool=TOOL_NAME,
            )
        # Body keys must match IncidentCreateInput in services/api/incidents_store.py.
        body: dict[str, Any] = {
            "category": inp.category,
            "description": inp.description,
            "status": inp.status or "ABIERTO",
        }
        if inp.date:
            body["date"] = inp.date
        if inp.location_id:
            body["location_id"] = inp.location_id
        if inp.customer_id:
            body["customer_id"] = inp.customer_id
        if inp.satisfaction_score is not None:
            body["satisfaction_score"] = inp.satisfaction_score
        if inp.reporter_id:
            body["reporter_id"] = inp.reporter_id
        response = incident_client.create_incident(body)
        if response.status_code >= 400:
            return error_payload(
                ErrorCode.UPSTREAM_ERROR if response.status_code >= 500 else ErrorCode.VALIDATION_ERROR,
                response.text or f"Create failed with HTTP {response.status_code}",
                tool=TOOL_NAME,
            )
        return {"ok": True, "action": "create", "ticket": _ticket_from_response(response.json())}

    # update — status lifecycle only (ignore unrelated fields; least privilege)
    if not inp.ticket_id:
        return error_payload(
            ErrorCode.VALIDATION_ERROR,
            "ticket_id is required for action=update",
            tool=TOOL_NAME,
        )
    if not inp.status:
        return error_payload(
            ErrorCode.VALIDATION_ERROR,
            "status is required for action=update (sent to PATCH /api/incidents/{id}/status)",
            tool=TOOL_NAME,
        )
    # Reject attempts to smuggle non-status mutations through update.
    extras = {
        k: v
        for k, v in {
            "category": inp.category,
            "description": inp.description,
            "date": inp.date,
            "location_id": inp.location_id,
            "customer_id": inp.customer_id,
            "satisfaction_score": inp.satisfaction_score,
            "reporter_id": inp.reporter_id,
        }.items()
        if v is not None
    }
    if extras:
        return error_payload(
            ErrorCode.VALIDATION_ERROR,
            "action=update only accepts ticket_id+status (lifecycle). "
            "Other fields are not allowed — least privilege.",
            tool=TOOL_NAME,
            details={"rejected_fields": extras},
        )
    response = incident_client.update_incident_status(inp.ticket_id, inp.status)
    if response.status_code == 404:
        return error_payload(
            ErrorCode.NOT_FOUND,
            f"Ticket {inp.ticket_id} was not found in the Incidents Manager.",
            tool=TOOL_NAME,
        )
    if response.status_code == 400:
        return error_payload(
            ErrorCode.LIFECYCLE_ERROR,
            response.json().get("detail") if response.headers.get("content-type", "").startswith("application/json") else response.text,
            tool=TOOL_NAME,
        )
    if response.status_code >= 400:
        return error_payload(
            ErrorCode.UPSTREAM_ERROR,
            f"Status update failed with HTTP {response.status_code}.",
            tool=TOOL_NAME,
        )
    return {"ok": True, "action": "update", "ticket": _ticket_from_response(response.json())}
