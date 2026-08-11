"""Part 2 routing evals — tools must hit the real company backends.

Acceptance
----------
- ≥1 question resolved with a **tool** (not RAG)
- ≥1 question resolved with the **RAG** (not a tool)
- Optional: fallback when the incident service is unavailable

Tools under test call ``GET /api/incidents`` / ``GET /inventory/products`` on
the real FastAPI app (CSV-backed). Ticket routing patches
``lookup_ticket_via_mcp`` (the graph's only Incidents path). No hardcoded
ticket/product payloads are injected into the tool return value.
"""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from services.agent.graph import compile_agent_graph, run_agent
from services.agent.tools.inventory_lookup import (
    INVENTORY_LOOKUP_TIMEOUT_SECONDS,
    lookup_inventory,
)
from services.agent.tools.contracts import (
    TicketLookupInput,
    TicketLookupOutput,
    TicketRecord,
)
from services.agent.tools.ticket_lookup import (
    TICKET_FALLBACK_MESSAGE,
    TICKET_LOOKUP_TIMEOUT_SECONDS,
)
from services.agent.tracing import load_trace
from tests.pipelines.agent_test_helpers import grounded_turn

REPO_ROOT = Path(__file__).resolve().parents[2]
INCIDENTS_CSV = REPO_ROOT / "scripts" / "incidents-COMPANY.csv"
PRODUCTS_CSV = REPO_ROOT / "products.csv"

PROTEIN_STOCK_CHUNK = {
    "source_document": "supplier-ordering",
    "section": "Minimum stock rule",
    "text": (
        "Minimum stock rule: no location should operate with less than 3 days of "
        "main protein inventory. An emergency order requires approval from "
        "Lucía Fernández (Procurement Manager) if it exceeds 500 USD."
    ),
    "_score": 0.91,
}
GROUNDED_ANSWER = (
    "Every Brasaland location must keep at least 3 days of main protein inventory. "
    "Emergency orders over 500 USD need approval from Lucía Fernández."
)


@pytest.fixture()
def trace_dir(tmp_path: Path) -> Path:
    return tmp_path / "traces"


@pytest.fixture()
def company_app():
    from api.app import app

    return app


@pytest.fixture()
def real_backend_transport(company_app):
    """httpx transport → real FastAPI routes (incidents + inventory CSV stores)."""
    tc = TestClient(company_app)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        path = request.url.path
        assert path.startswith("/api/incidents") or path.startswith("/inventory/")
        response = tc.get(path, params=dict(request.url.params) or None)
        return httpx.Response(
            response.status_code,
            headers={"content-type": "application/json"},
            content=response.content,
            request=request,
        )

    return httpx.MockTransport(handler)


def _csv_incident(incident_id: str) -> dict[str, str]:
    with INCIDENTS_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("incident_id") == incident_id:
                return row
    raise AssertionError(f"{incident_id} missing from company incidents CSV")


def _csv_product(name: str) -> dict[str, str]:
    with PRODUCTS_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row.get("name") or "").casefold() == name.casefold():
                return row
    raise AssertionError(f"{name} missing from company products.csv")


def _run_and_save_trace(question: str, trace_dir: Path, **node_patches) -> dict:
    patchers = [patch(target, value) for target, value in node_patches.items()]
    for p in patchers:
        p.start()
    try:
        with patch("services.agent.tracing.DEFAULT_TRACE_DIR", trace_dir), patch(
            "services.agent.graph.save_trace"
        ) as mock_save:
            from services.agent.tracing import save_trace as real_save

            mock_save.side_effect = lambda record, **_: real_save(record, trace_dir=trace_dir)
            with patch("services.agent.graph._COMPILED_GRAPH", compile_agent_graph()):
                return run_agent(question)
    finally:
        for p in reversed(patchers):
            p.stop()


def _ticket_via_real_backend(transport: httpx.BaseTransport):
    """Stand-in for MCP get_status: read the real incident API (no deprecated HTTP tool)."""

    def _call(query, **kwargs):
        if isinstance(query, dict):
            inp = TicketLookupInput.model_validate(query)
        else:
            inp = query
        ticket_id = (inp.ticket_id or "").strip()
        with httpx.Client(
            base_url="http://company-backend",
            transport=transport,
            timeout=TICKET_LOOKUP_TIMEOUT_SECONDS,
        ) as client:
            response = client.get(f"/api/incidents/{ticket_id}")
        if response.status_code == 404:
            return TicketLookupOutput(
                ok=False,
                tickets=[],
                error="not_found",
                message=TICKET_FALLBACK_MESSAGE,
            )
        if response.status_code >= 400:
            return TicketLookupOutput(
                ok=False,
                tickets=[],
                error="service_error",
                message=TICKET_FALLBACK_MESSAGE,
            )
        payload = response.json()
        ticket = TicketRecord(
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
        return TicketLookupOutput(ok=True, tickets=[ticket])

    return _call


def _inventory_via_real_backend(transport: httpx.BaseTransport):
    def _call(query, **kwargs):
        return lookup_inventory(
            query,
            base_url="http://company-backend",
            transport=transport,
            timeout_seconds=INVENTORY_LOOKUP_TIMEOUT_SECONDS,
        )

    return _call


def test_eval_tool_required_reads_real_incident_service_not_rag(
    trace_dir: Path, real_backend_transport
):
    """Eval 1 — tool question: status comes from GET /api/incidents/{id}, not RAG."""
    expected = _csv_incident("BRS-000002")

    with patch("services.agent.nodes.retrieve") as mock_retrieve, patch(
        "services.agent.nodes.lookup_ticket_via_mcp",
        side_effect=_ticket_via_real_backend(real_backend_transport),
    ), patch("services.agent.nodes.lookup_inventory") as mock_inv:
        result = _run_and_save_trace(
            "What is the status of ticket BRS-000002?",
            trace_dir,
        )

    mock_retrieve.assert_not_called()
    mock_inv.assert_not_called()
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)

    assert "lookup_ticket" in trace["node_order"]
    assert "retrieve" not in trace["node_order"]
    assert "generate" not in trace["node_order"]
    assert trace["sources_order"] == ["ticket"]
    assert trace["source_summary"] == "ticket_only"

    # Values must match the company CSV / live incident API — not invented.
    assert expected["status"] in (trace["answer"] or "")
    assert expected["category"] in (trace["answer"] or "")
    assert expected["incident_id"] in (trace["answer"] or "")
    assert expected["description"] in (trace["answer"] or "")


def test_eval_rag_required_skips_tools(trace_dir: Path):
    """Eval 2 — policy question: RAG only; incident/inventory tools must not run."""
    with patch("services.agent.nodes.lookup_ticket_via_mcp") as mock_ticket, patch(
        "services.agent.nodes.lookup_inventory"
    ) as mock_inv:
        result = _run_and_save_trace(
            "What is the minimum stock rule for proteins?",
            trace_dir,
            **{
                "services.agent.nodes.retrieve": lambda q: [PROTEIN_STOCK_CHUNK],
                "services.agent.nodes.generate_agent_turn": lambda q, ctx, recalled=None: grounded_turn(),
            },
        )

    mock_ticket.assert_not_called()
    mock_inv.assert_not_called()
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)

    assert trace["node_order"] == [
        "receive_question",
        "decide_route",
        "recall_memory",
        "retrieve",
        "generate",
        "write_memory",
    ]
    assert "lookup_ticket" not in trace["node_order"]
    assert "lookup_inventory" not in trace["node_order"]
    assert trace["sources_order"] == ["rag"]
    assert trace["source_summary"] == "rag_only"
    assert "3 days" in (trace["answer"] or "")
    assert "Lucía Fernández" in (trace["answer"] or "")


def test_eval_fallback_when_incident_service_unavailable(trace_dir: Path):
    """Optional Eval 3 — silent/failed incident service → honest fallback, no status."""

    def _timeout_tool(query, **kwargs):
        from services.agent.tools.contracts import TicketLookupOutput

        return TicketLookupOutput(
            ok=False,
            tickets=[],
            error="timeout",
            message=TICKET_FALLBACK_MESSAGE,
        )

    with patch("services.agent.nodes.lookup_ticket_via_mcp", side_effect=_timeout_tool), patch(
        "services.agent.nodes.retrieve"
    ) as mock_retrieve:
        result = _run_and_save_trace(
            "What is the status of ticket BRS-000002?",
            trace_dir,
        )

    mock_retrieve.assert_not_called()
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert "ticket_fallback" in trace["node_order"]
    answer = (trace["answer"] or "").casefold()
    assert "couldn't confirm that ticket's status right now" in answer
    assert "status=abierto" not in answer
    assert "status=cerrado" not in answer


def test_eval_inventory_tool_reads_real_products_csv(
    trace_dir: Path, real_backend_transport
):
    """Stretch — inventory question hits GET /inventory/products (real products.csv)."""
    expected = _csv_product("Tomatoes")

    with patch("services.agent.nodes.retrieve") as mock_retrieve, patch(
        "services.agent.nodes.lookup_inventory",
        side_effect=_inventory_via_real_backend(real_backend_transport),
    ), patch("services.agent.nodes.lookup_ticket_via_mcp") as mock_ticket:
        result = _run_and_save_trace(
            "Do we have stock of tomatoes?",
            trace_dir,
        )

    mock_retrieve.assert_not_called()
    mock_ticket.assert_not_called()
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert "lookup_inventory" in trace["node_order"]
    assert "retrieve" not in trace["node_order"]
    assert trace["sources_order"] == ["inventory"]
    assert expected["name"] in (trace["answer"] or "")
    assert f"quantity={expected['quantity']}" in (trace["answer"] or "")
