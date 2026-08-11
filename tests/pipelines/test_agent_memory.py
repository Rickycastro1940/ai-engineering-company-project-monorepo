"""Agent memory extends the existing LangGraph + MCP agent (does not replace it)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.agent.graph import REQUIRED_NODES, build_agent_graph, compile_agent_graph
from services.agent.memory.policy import evaluate_memory_candidate
from services.agent.memory.store import MemoryStore
from services.agent.nodes import lookup_ticket_node
from services.agent.tools.mcp_incidents import lookup_ticket_via_mcp


def test_memory_nodes_extend_same_mcp_graph() -> None:
    """Memory is added to the MCP/RAG graph — ticket node still MCP-only."""
    assert "recall_memory" in REQUIRED_NODES
    assert "write_memory" in REQUIRED_NODES
    assert "lookup_ticket" in REQUIRED_NODES

    graph = build_agent_graph()
    nodes = set(graph.nodes.keys())
    assert {"recall_memory", "write_memory", "lookup_ticket", "retrieve"} <= nodes

    source = Path(lookup_ticket_node.__code__.co_filename).read_text(encoding="utf-8")
    # lookup_ticket_node lives in nodes.py — assert MCP import still used by graph module wiring
    import inspect

    assert "lookup_ticket_via_mcp" in inspect.getsource(lookup_ticket_node)
    assert "via\": \"mcp\"" in inspect.getsource(lookup_ticket_node) or '"via": "mcp"' in inspect.getsource(
        lookup_ticket_node
    )
    assert lookup_ticket_via_mcp  # imported client still present


def test_policy_blocks_forbidden_memory_and_allows_ops_facts() -> None:
    deny = evaluate_memory_candidate("This dish is 100% safe with zero risk of allergy.")
    assert deny.allowed is False
    assert deny.reason == "absolute_allergen_safety"

    deny_fx = evaluate_memory_candidate("Convert 500 USD to COP for emergency orders.")
    assert deny_fx.allowed is False

    deny_unknown = evaluate_memory_candidate("There is not enough information available.")
    assert deny_unknown.allowed is False

    allow = evaluate_memory_candidate(
        "Emergency orders over 500 USD require approval from Lucía Fernández (Procurement)."
    )
    assert allow.allowed is True
    assert allow.kind == "procurement"


def test_memory_store_upsert_and_search(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "semantic.json")
    store.upsert(
        text="Minimum protein stock is 3 days of inventory.",
        kind="procurement",
        source="test",
    )
    hits = store.search("protein stock rule", limit=3)
    assert hits
    assert "3 days" in hits[0].text


def test_compiled_graph_routes_ticket_through_recall_then_mcp() -> None:
    compiled = compile_agent_graph()
    assert "recall_memory" in compiled.get_graph().nodes
    assert "lookup_ticket" in compiled.get_graph().nodes
    assert "write_memory" in compiled.get_graph().nodes
