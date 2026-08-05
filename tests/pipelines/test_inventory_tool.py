"""Stretch evals — inventory tool against live GET /inventory/products."""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from services.agent.graph import compile_agent_graph, run_agent
from services.agent.tools.contracts import InventoryLookupInput, InventoryLookupOutput
from services.agent.tools.inventory_lookup import (
    INVENTORY_FALLBACK_MESSAGE,
    INVENTORY_LOOKUP_TIMEOUT_SECONDS,
    PRODUCTS_LIST_PATH,
    lookup_inventory,
)
from services.agent.tools.routing import classify_sources
from services.agent.tracing import load_trace

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_CSV = REPO_ROOT / "products.csv"


@pytest.fixture()
def trace_dir(tmp_path: Path) -> Path:
    return tmp_path / "traces"


def _run_and_save_trace(question: str, trace_dir: Path, **node_patches) -> dict:
    patchers = []
    for target, value in node_patches.items():
        p = patch(target, value)
        patchers.append(p)
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


def test_inventory_csv_is_company_data_not_fake():
    assert PRODUCTS_CSV.is_file()
    with PRODUCTS_CSV.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    names = {r["name"] for r in rows}
    assert "Tomatoes" in names
    assert "Mozzarella" in names


def test_inventory_api_serves_products_csv():
    from api.app import app

    tc = TestClient(app)
    response = tc.get("/inventory/products")
    assert response.status_code == 200
    body = response.json()
    assert any(p["name"] == "Tomatoes" and p["quantity"] == 25 for p in body)
    by_id = tc.get("/inventory/products/1")
    assert by_id.status_code == 200
    assert by_id.json()["name"] == "Tomatoes"


def test_lookup_inventory_hits_real_get_inventory_products():
    from api.app import app

    tc = TestClient(app)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path.startswith("/inventory/products")
        response = tc.get(request.url.path, params=dict(request.url.params))
        return httpx.Response(response.status_code, content=response.content, request=request)

    result = lookup_inventory(
        InventoryLookupInput(name_contains="Tomatoes"),
        base_url="http://inventory-manager",
        transport=httpx.MockTransport(handler),
        timeout_seconds=INVENTORY_LOOKUP_TIMEOUT_SECONDS,
    )
    assert result.ok is True
    assert len(result.products) == 1
    assert result.products[0].name == "Tomatoes"
    assert result.products[0].quantity == 25
    assert result.products[0].source == "inventory_manager"


def test_inventory_timeout_constant_and_fallback_message():
    assert INVENTORY_LOOKUP_TIMEOUT_SECONDS == 5.0
    assert PRODUCTS_LIST_PATH == "/inventory/products"
    assert "couldn't confirm" in INVENTORY_FALLBACK_MESSAGE.casefold()


def test_classify_routes_stock_question_to_inventory_not_rag():
    decision = classify_sources("Do we have stock of tomatoes?")
    assert decision["needs_inventory"] is True
    assert decision["needs_rag"] is False
    assert decision["needs_ticket"] is False
    assert decision["route"] == "inventory"
    assert decision["inventory_query"]["name_contains"] == "Tomatoes"


def test_classify_keeps_stock_rule_on_rag_not_inventory():
    decision = classify_sources("What is the minimum stock rule for proteins?")
    assert decision["needs_rag"] is True
    assert decision["needs_inventory"] is False
    assert decision["route"] == "retrieve"


def test_eval_inventory_question_uses_inventory_tool(trace_dir: Path):
    ok = InventoryLookupOutput(
        ok=True,
        products=[
            {
                "product_id": "1",
                "name": "Tomatoes",
                "quantity": 25,
                "unit": "kg",
                "source": "inventory_manager",
            }
        ],
    )
    with patch("services.agent.nodes.retrieve") as mock_retrieve, patch(
        "services.agent.nodes.lookup_inventory", return_value=ok
    ) as mock_inv:
        result = _run_and_save_trace(
            "Do we have stock of tomatoes?",
            trace_dir,
        )

    mock_retrieve.assert_not_called()
    mock_inv.assert_called_once()
    assert mock_inv.call_args.kwargs.get("timeout_seconds") == INVENTORY_LOOKUP_TIMEOUT_SECONDS
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert "lookup_inventory" in trace["node_order"]
    assert "decide_route" in trace["node_order"]
    assert "retrieve" not in trace["node_order"]
    assert "answer_inventory" in trace["node_order"]
    assert trace["sources_used"] == ["inventory"]
    assert "Tomatoes" in (trace["answer"] or "")
    assert "quantity=25" in (trace["answer"] or "")


def test_eval_inventory_fallback_never_invents_stock(trace_dir: Path):
    failed = InventoryLookupOutput(
        ok=False,
        products=[],
        error="timeout",
        message=INVENTORY_FALLBACK_MESSAGE,
    )
    with patch("services.agent.nodes.lookup_inventory", return_value=failed), patch(
        "services.agent.nodes.retrieve"
    ) as mock_retrieve:
        result = _run_and_save_trace("Do we have stock of mozzarella?", trace_dir)

    mock_retrieve.assert_not_called()
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert "inventory_fallback" in trace["node_order"]
    answer = (trace["answer"] or "").casefold()
    assert "couldn't confirm" in answer
    assert "quantity=8" not in answer
    assert "quantity=25" not in answer


def test_inventory_tool_module_has_no_hardcoded_product_rows():
    source = (
        REPO_ROOT / "services" / "agent" / "tools" / "inventory_lookup.py"
    ).read_text(encoding="utf-8")
    assert "Tomatoes" not in source
    assert "Mozzarella" not in source
    assert "Napkins" not in source
