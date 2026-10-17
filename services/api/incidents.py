"""Incident manager routes for Felipe Guerrero and Mariana Restrepo.

Mounted on the central FastAPI app. Historical rows come from scripts/seed_incidents.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import incident_store  # noqa: E402
from packages.shared.incident_rules import (  # noqa: E402
    BRANCH_VALUES,
    MODEL_CATEGORIES,
    MODEL_ORIGINS,
    MODEL_STATUSES,
    FieldError,
    transition_error,
    validate_incident_payload,
)

router = APIRouter(tags=["incidents"])


def _validation_response(errors: list[FieldError]) -> JSONResponse:
    payload = [error.as_dict() for error in errors]
    first = payload[0]
    message = first["message"] if len(payload) == 1 else "Please correct the highlighted fields."
    return JSONResponse(
        status_code=400,
        content={
            "status": 400,
            "code": "bad_request",
            "message": message,
            "field": first["field"],
            "detail": {
                "field": first["field"],
                "message": message,
                "errors": payload,
            },
        },
    )


def _unknown_filter(name: str, value: str | None, allowed: frozenset[str] | tuple[str, ...]) -> JSONResponse | None:
    if value is None or value == "":
        return None
    if value not in allowed:
        return _validation_response([FieldError(name, f"Choose a valid {name}.")])
    return None


@router.get("/api/incidents/summary")
def incident_summary():
    return incident_store.summary()


@router.get("/api/incidents")
def list_incidents(
    status: str | None = None,
    origin: str | None = None,
    branch: str | None = None,
    category: str | None = None,
):
    for name, value, allowed in (
        ("status", status, MODEL_STATUSES),
        ("origin", origin, MODEL_ORIGINS),
        ("branch", branch, BRANCH_VALUES),
        ("category", category, MODEL_CATEGORIES),
    ):
        rejected = _unknown_filter(name, value, allowed)
        if rejected is not None:
            return rejected
    return incident_store.list_incidents(
        status=status or None,
        origin=origin or None,
        branch=branch or None,
        category=category or None,
    )


@router.post("/api/incidents")
def create_incident(payload: dict = Body(...)):
    errors = validate_incident_payload(payload)
    if errors:
        return _validation_response(errors)
    stored = incident_store.insert_incident(
        {
            "title": str(payload["title"]).strip(),
            "description": str(payload["description"]).strip(),
            "category": payload["category"],
            "status": payload["status"],
            "origin": payload["origin"],
            "branch": payload["branch"],
        }
    )
    return JSONResponse(status_code=201, content=stored)


@router.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str):
    stored = incident_store.get_incident(incident_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="That incident was not found.")
    return stored


@router.patch("/api/incidents/{incident_id}/status")
def patch_status(incident_id: str, payload: dict = Body(...)):
    if not isinstance(payload, dict) or "status" not in payload:
        return _validation_response([FieldError("status", "Choose a valid status.")])
    current = incident_store.get_incident(incident_id)
    if current is None:
        raise HTTPException(status_code=404, detail="That incident was not found.")
    error = transition_error(current["status"], payload.get("status"))
    if error is not None:
        return _validation_response([error])
    updated = incident_store.update_status(incident_id, str(payload["status"]))
    if updated is None:
        raise HTTPException(status_code=404, detail="That incident was not found.")
    return updated
