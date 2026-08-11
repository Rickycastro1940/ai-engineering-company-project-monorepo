"""Prove the ticket tool reads from the real incident manager — not fake data.

Calls go through ``GET /api/incidents`` / ``GET /api/incidents/{id}`` on the
company FastAPI app (CSV-backed store). No hardcoded ticket payloads in the tool.
"""

from __future__ import annotations

import csv
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from services.agent.tools.contracts import TicketLookupInput
from services.agent.tools.ticket_lookup import (
    INCIDENT_BY_ID_PATH_TEMPLATE,
    INCIDENTS_LIST_PATH,
    TICKET_LOOKUP_TIMEOUT_SECONDS,
    lookup_ticket,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = REPO_ROOT / "scripts" / "incidents-COMPANY.csv"


def _csv_row(incident_id: str) -> dict[str, str]:
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row.get("incident_id") or "").strip() == incident_id:
                return row
    raise AssertionError(f"{incident_id} missing from {CSV_PATH}")


@pytest.fixture()
def incident_app():
    """Load the real monorepo FastAPI app (incident manager + agent)."""
    from api.app import app

    return app


@pytest.fixture()
def real_api_transport(incident_app):
    """httpx transport that delegates to the real FastAPI incident routes."""
    tc = TestClient(incident_app)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        path = request.url.path
        assert path == INCIDENTS_LIST_PATH or path.startswith("/api/incidents/")
        params = dict(request.url.params)
        response = tc.get(path, params=params or None)
        return httpx.Response(
            response.status_code,
            headers={"content-type": "application/json"},
            content=response.content,
            request=request,
        )

    return httpx.MockTransport(handler)


def test_tool_get_by_id_hits_real_incident_api_not_hardcoded(real_api_transport):
    """GET /api/incidents/{id} returns CSV-backed fields — no invented status."""
    expected = _csv_row("BRS-000002")
    result = lookup_ticket(
        TicketLookupInput(ticket_id="BRS-000002"),
        base_url="http://incident-manager",
        transport=real_api_transport,
        timeout_seconds=TICKET_LOOKUP_TIMEOUT_SECONDS,
    )

    assert result.ok is True
    assert result.error is None
    assert len(result.tickets) == 1
    ticket = result.tickets[0]
    assert ticket.incident_id == expected["incident_id"]
    assert ticket.status == expected["status"]
    assert ticket.category == expected["category"]
    assert ticket.date == expected["date"]
    assert ticket.location_id == (expected["location_id"] or None)
    assert ticket.description == expected["description"]
    assert ticket.source == "incident_manager"


def test_tool_list_hits_real_get_api_incidents(real_api_transport):
    """GET /api/incidents?status=ABIERTO returns live open tickets from the CSV."""
    with CSV_PATH.open(encoding="utf-8") as handle:
        expected_open = {
            row["incident_id"]
            for row in csv.DictReader(handle)
            if row.get("status") == "ABIERTO"
        }
    result = lookup_ticket(
        TicketLookupInput(status="ABIERTO"),
        base_url="http://incident-manager",
        transport=real_api_transport,
    )

    assert result.ok is True
    got = {t.incident_id for t in result.tickets}
    assert got == expected_open
    assert "BRS-000002" in got
    # Closed tickets must not appear in an ABIERTO filter result.
    assert "BRS-000001" not in got


def test_incident_api_endpoints_serve_company_csv(incident_app):
    """Direct service check: the manager endpoints expose the company CSV."""
    tc = TestClient(incident_app)
    by_id = tc.get("/api/incidents/BRS-000001")
    assert by_id.status_code == 200
    body = by_id.json()
    expected = _csv_row("BRS-000001")
    assert body["status"] == expected["status"]
    assert body["category"] == expected["category"]
    assert body["description"] == expected["description"]

    listing = tc.get("/api/incidents")
    assert listing.status_code == 200
    ids = {item["incident_id"] for item in listing.json()}
    assert "BRS-000001" in ids and "BRS-000002" in ids


def test_tool_paths_are_only_incident_manager_gets():
    """Contract: tool may only target the two read-only incident routes."""
    assert INCIDENTS_LIST_PATH == "/api/incidents"
    assert INCIDENT_BY_ID_PATH_TEMPLATE == "/api/incidents/{incident_id}"


def test_tool_module_contains_no_hardcoded_ticket_rows():
    """Guardrail — ticket_lookup.py must not embed BRS-* payload tables."""
    source = (
        REPO_ROOT / "services" / "agent" / "tools" / "ticket_lookup.py"
    ).read_text(encoding="utf-8")
    assert "BRS-000001" not in source
    assert "BRS-000002" not in source
    assert "Late produce delivery" not in source
    assert "Grill temperature spike" not in source


def test_live_network_call_against_running_incident_manager():
    """When uvicorn is up, the tool uses real HTTP to GET /api/incidents/{id}."""
    base = "http://127.0.0.1:8000"
    try:
        probe = httpx.get(f"{base}/api/incidents/BRS-000002", timeout=2.0)
    except httpx.HTTPError:
        pytest.skip("incident manager not running on :8000")
    if probe.status_code != 200:
        pytest.skip(f"incident manager probe returned {probe.status_code}")

    expected = probe.json()
    result = lookup_ticket(
        TicketLookupInput(ticket_id="BRS-000002"),
        base_url=base,
        timeout_seconds=TICKET_LOOKUP_TIMEOUT_SECONDS,
    )
    assert result.ok is True
    assert result.tickets[0].incident_id == expected["incident_id"]
    assert result.tickets[0].status == expected["status"]
    assert result.tickets[0].category == expected["category"]
    assert result.tickets[0].date == expected["date"]
