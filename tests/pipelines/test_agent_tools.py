"""Part 2 evals — routing between RAG and the ticket tool, plus fallbacks.

    uv run pytest tests/pipelines/test_agent_tools.py -q
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from services.agent.graph import compile_agent_graph, run_agent
from services.agent.tools.contracts import TicketLookupInput, TicketLookupOutput, TicketRecord
from services.agent.tools.routing import classify_sources
from services.agent.tools.ticket_lookup import (
    TICKET_FALLBACK_MESSAGE,
    TICKET_LOOKUP_TIMEOUT_SECONDS,
    build_ticket_http_timeout,
    lookup_ticket,
)
from services.agent.tracing import load_trace
from services.api.incidents_store import get_incident, load_incidents

REPO_ROOT = Path(__file__).resolve().parents[2]

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

SAMPLE_TICKET = TicketRecord(
    incident_id="BRS-000002",
    date="2026-06-01",
    location_id="COL-02",
    category="ABASTECIMIENTO",
    description="Late produce delivery",
    status="ABIERTO",
    customer_id="CLI-0002",
    satisfaction_score=None,
    reporter_id="MGR-02",
    source="incident_manager",
)


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


def test_ticket_lookup_input_requires_id_or_filters():
    """Typed contract: empty input is rejected."""
    with pytest.raises(ValidationError):
        TicketLookupInput()


def test_ticket_lookup_input_accepts_ticket_id_or_filters():
    by_id = TicketLookupInput(ticket_id="BRS-000002")
    assert by_id.ticket_id == "BRS-000002"
    by_filters = TicketLookupInput(status="ABIERTO", category="EQUIPAMIENTO")
    assert by_filters.status == "ABIERTO"
    assert by_filters.category == "EQUIPAMIENTO"


def test_ticket_record_matches_incident_api_fields():
    """Output fields mirror the incident API / CSV contract."""
    payload = SAMPLE_TICKET.model_dump()
    assert set(payload) >= {
        "incident_id",
        "date",
        "location_id",
        "category",
        "description",
        "status",
        "customer_id",
        "satisfaction_score",
        "reporter_id",
        "source",
    }
    live = get_incident("BRS-000002")
    assert live is not None
    assert live.status == "ABIERTO"
    assert live.category == "ABASTECIMIENTO"
    assert live.source == "incident_manager"


def test_incident_store_reads_real_company_csv():
    """Tool/API data comes from scripts/incidents-COMPANY.csv — not a fake set."""
    records = load_incidents()
    assert len(records) >= 5
    ids = {r.incident_id for r in records}
    assert "BRS-000001" in ids
    assert "BRS-000002" in ids


def test_lookup_ticket_http_get_by_id_uses_real_shape():
    """HTTP tool returns typed TicketLookupOutput from GET /api/incidents/{id}."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url).endswith("/api/incidents/BRS-000002")
        return httpx.Response(200, json=SAMPLE_TICKET.model_dump())

    transport = httpx.MockTransport(handler)
    result = lookup_ticket(
        TicketLookupInput(ticket_id="BRS-000002"),
        transport=transport,
    )
    assert result.ok is True
    assert result.error is None
    assert len(result.tickets) == 1
    assert result.tickets[0].status == "ABIERTO"
    assert result.tickets[0].category == "ABASTECIMIENTO"
    assert result.tickets[0].date == "2026-06-01"
    assert result.tickets[0].source == "incident_manager"


def test_lookup_ticket_timeout_returns_fallback_not_invented_status():
    """Explicit numeric timeout → honest fallback, never a made-up status."""
    assert TICKET_LOOKUP_TIMEOUT_SECONDS == 5.0

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout", request=request)

    transport = httpx.MockTransport(handler)
    result = lookup_ticket(
        TicketLookupInput(ticket_id="BRS-000002"),
        transport=transport,
        timeout_seconds=TICKET_LOOKUP_TIMEOUT_SECONDS,
    )
    assert result.ok is False
    assert result.error == "timeout"
    assert result.tickets == []
    assert "couldn't confirm" in (result.message or "").casefold() or result.message == TICKET_FALLBACK_MESSAGE


def test_lookup_ticket_not_found_is_honest():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    result = lookup_ticket(
        TicketLookupInput(ticket_id="BRS-999999"),
        transport=httpx.MockTransport(handler),
    )
    assert result.ok is False
    assert result.error == "not_found"
    assert result.tickets == []


def test_classify_routes_ticket_question_to_tool_not_rag():
    decision = classify_sources("What is the status of ticket BRS-000002?")
    assert decision["needs_ticket"] is True
    assert decision["needs_rag"] is False
    assert decision["route"] == "ticket"
    assert decision["ticket_query"]["ticket_id"] == "BRS-000002"


def test_classify_routes_policy_question_to_rag_not_tool():
    decision = classify_sources("What is the minimum stock rule for proteins?")
    assert decision["needs_rag"] is True
    assert decision["needs_ticket"] is False
    assert decision["route"] == "retrieve"
    assert decision["ticket_query"] is None


def test_eval_tool_required_question_uses_ticket_not_rag(trace_dir: Path):
    """Eval — ticket status question must resolve via the ticket tool, not RAG."""
    ok_result = TicketLookupOutput(ok=True, tickets=[SAMPLE_TICKET], error=None)

    with patch("services.agent.nodes.retrieve") as mock_retrieve, patch(
        "services.agent.nodes.lookup_ticket", return_value=ok_result
    ) as mock_lookup:
        result = _run_and_save_trace(
            "What is the status of ticket BRS-000002?",
            trace_dir,
        )

    mock_retrieve.assert_not_called()
    assert mock_lookup.call_count == 1
    called = mock_lookup.call_args.args[0]
    assert getattr(called, "ticket_id", None) == "BRS-000002" or (
        isinstance(called, dict) and called.get("ticket_id") == "BRS-000002"
    )
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert trace["node_order"] == [
        "receive_question",
        "decide_route",
        "lookup_ticket",
        "answer_ticket",
    ]
    assert "lookup_ticket" in trace["node_order"]
    assert "decide_route" in trace["node_order"]
    assert "retrieve" not in trace["node_order"]
    assert "generate" not in trace["node_order"]
    assert "answer_ticket" in trace["node_order"]
    decide = next(s for s in trace["steps"] if s["node_name"] == "decide_route")
    assert decide["output"]["decision"] == "ticket_tool"
    assert decide["output"]["needs_ticket"] is True
    assert decide["output"]["needs_rag"] is False
    assert trace["sources_used"] == ["ticket"]
    assert "ABIERTO" in (trace["answer"] or "")
    assert "BRS-000002" in (trace["answer"] or "")
    assert "ABASTECIMIENTO" in (trace["answer"] or "")


def test_eval_rag_required_question_skips_ticket_tool(trace_dir: Path):
    """Eval — policy question must resolve via RAG, not the ticket tool."""
    with patch("services.agent.nodes.lookup_ticket") as mock_lookup:
        result = _run_and_save_trace(
            "What is the minimum stock rule for proteins?",
            trace_dir,
            **{
                "services.agent.nodes.retrieve": lambda q: [PROTEIN_STOCK_CHUNK],
                "services.agent.nodes.generate_answer": lambda q, ctx: GROUNDED_ANSWER,
            },
        )

    mock_lookup.assert_not_called()
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert trace["node_order"] == [
        "receive_question",
        "decide_route",
        "retrieve",
        "generate",
    ]
    assert "lookup_ticket" not in trace["node_order"]
    assert "decide_route" in trace["node_order"]
    decide = next(s for s in trace["steps"] if s["node_name"] == "decide_route")
    assert decide["output"]["decision"] == "rag"
    assert decide["output"]["needs_ticket"] is False
    assert trace["sources_used"] == ["rag"]
    assert "3 days" in (trace["answer"] or "")


def test_eval_ticket_fallback_when_service_unavailable(trace_dir: Path):
    """Optional fallback eval — timeout/error → honest answer, no invented status."""
    failed = TicketLookupOutput(
        ok=False,
        tickets=[],
        error="timeout",
        message=TICKET_FALLBACK_MESSAGE,
    )
    with patch("services.agent.nodes.lookup_ticket", return_value=failed), patch(
        "services.agent.nodes.retrieve"
    ) as mock_retrieve:
        result = _run_and_save_trace(
            "Status of ticket BRS-000002?",
            trace_dir,
        )

    mock_retrieve.assert_not_called()
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert "ticket_fallback" in trace["node_order"]
    assert "lookup_ticket" in trace["node_order"]
    answer = (trace["answer"] or "").casefold()
    assert "couldn't confirm" in answer or "could not find" in answer
    # Never invent a concrete ticket status on failure.
    assert "status=abierto" not in answer
    assert "status=cerrado" not in answer


def test_eval_decide_route_both_runs_ticket_then_rag(trace_dir: Path):
    """Conditional agent can use the ticket tool *in addition to* the RAG."""
    ok_result = TicketLookupOutput(ok=True, tickets=[SAMPLE_TICKET], error=None)
    result = _run_and_save_trace(
        "What is the status of ticket BRS-000002 and what is the minimum stock rule for proteins?",
        trace_dir,
        **{
            "services.agent.nodes.lookup_ticket": lambda q, **_: ok_result,
            "services.agent.nodes.retrieve": lambda q: [PROTEIN_STOCK_CHUNK],
            "services.agent.nodes.generate_answer": lambda q, ctx: GROUNDED_ANSWER,
        },
    )
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    order = trace["node_order"]
    assert order.index("decide_route") < order.index("lookup_ticket")
    assert order.index("lookup_ticket") < order.index("retrieve")
    assert order.index("retrieve") < order.index("generate")
    decide = next(s for s in trace["steps"] if s["node_name"] == "decide_route")
    assert decide["output"]["decision"] == "ticket_tool_and_rag"
    assert decide["output"]["needs_ticket"] is True
    assert decide["output"]["needs_rag"] is True
    assert trace["sources_used"] == ["ticket", "rag"]
    assert "3 days" in (trace["answer"] or "")
    assert "BRS-000002" in (trace["answer"] or "") or "ABIERTO" in (trace["answer"] or "")


def test_graph_registers_lookup_ticket_and_decide_route_nodes():
    """Graph must include the ticket tool node and the conditional router."""
    from services.agent.graph import REQUIRED_NODES, build_agent_graph

    graph = build_agent_graph()
    registered = set(graph.nodes.keys())
    assert "lookup_ticket" in registered
    assert "decide_route" in registered
    assert "lookup_ticket" in REQUIRED_NODES
    assert "decide_route" in REQUIRED_NODES


def test_tool_is_read_only_get_only():
    """Ticket tool must only issue GET (never POST/PUT/PATCH/DELETE)."""
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, json=SAMPLE_TICKET.model_dump())

    lookup_ticket(
        TicketLookupInput(ticket_id="BRS-000002"),
        transport=httpx.MockTransport(handler),
    )
    assert methods == ["GET"]


def test_timeout_constant_is_explicit_and_numeric():
    assert isinstance(TICKET_LOOKUP_TIMEOUT_SECONDS, (int, float))
    assert 3.0 <= float(TICKET_LOOKUP_TIMEOUT_SECONDS) <= 5.0
    timeout = build_ticket_http_timeout()
    assert timeout.connect == TICKET_LOOKUP_TIMEOUT_SECONDS
    assert timeout.read == TICKET_LOOKUP_TIMEOUT_SECONDS


def test_slow_incident_service_does_not_hang_call():
    """A silent TCP acceptor must abort within the timeout — graph must not hang."""
    import socket
    import threading
    import time

    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.listen(1)
    stop = threading.Event()

    def _accept_and_stall() -> None:
        sock.settimeout(2.0)
        try:
            conn, _ = sock.accept()
            while not stop.wait(0.05):
                pass
            conn.close()
        except OSError:
            pass

    thread = threading.Thread(target=_accept_and_stall, daemon=True)
    thread.start()
    short_timeout = 0.4
    started = time.perf_counter()
    try:
        result = lookup_ticket(
            TicketLookupInput(ticket_id="BRS-000002"),
            base_url=f"http://127.0.0.1:{port}",
            timeout_seconds=short_timeout,
        )
    finally:
        stop.set()
        sock.close()
        thread.join(timeout=2.0)

    elapsed = time.perf_counter() - started
    assert result.ok is False
    assert result.error == "timeout"
    assert result.tickets == []
    # Must finish near the timeout, not hang for tens of seconds.
    assert elapsed < short_timeout + 1.5


def test_eval_graph_timeout_routes_to_fallback_without_hanging(trace_dir: Path):
    """Graph-level: ticket timeout → ticket_fallback; run completes quickly."""
    import time

    timed_out = TicketLookupOutput(
        ok=False,
        tickets=[],
        error="timeout",
        message=TICKET_FALLBACK_MESSAGE,
    )
    started = time.perf_counter()
    with patch(
        "services.agent.nodes.lookup_ticket",
        return_value=timed_out,
    ) as mock_lookup, patch("services.agent.nodes.retrieve") as mock_retrieve:
        result = _run_and_save_trace(
            "Status of ticket BRS-000002?",
            trace_dir,
        )

    elapsed = time.perf_counter() - started
    mock_retrieve.assert_not_called()
    mock_lookup.assert_called_once()
    # Node must pass the explicit numeric timeout into the tool.
    assert mock_lookup.call_args.kwargs.get("timeout_seconds") == TICKET_LOOKUP_TIMEOUT_SECONDS
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert "lookup_ticket" in trace["node_order"]
    assert "ticket_fallback" in trace["node_order"]
    lookup_step = next(s for s in trace["steps"] if s["node_name"] == "lookup_ticket")
    assert lookup_step["output"]["timeout_seconds"] == TICKET_LOOKUP_TIMEOUT_SECONDS
    assert lookup_step["output"]["error"] == "timeout"
    assert elapsed < 2.0
    assert "couldn't confirm" in (trace["answer"] or "").casefold()
