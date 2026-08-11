"""Agent memory extends the existing LangGraph + MCP agent (does not replace it)."""

from __future__ import annotations

from pathlib import Path

from data.pipelines import rag as rag_mod
from services.agent.graph import REQUIRED_NODES, build_agent_graph, compile_agent_graph
from services.agent.memory.interface import (
    DEFAULT_READ_LIMIT,
    AgentMemory,
    MemoryInterface,
)
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

    import inspect

    assert "lookup_ticket_via_mcp" in inspect.getsource(lookup_ticket_node)
    assert "via\": \"mcp\"" in inspect.getsource(lookup_ticket_node) or '"via": "mcp"' in inspect.getsource(
        lookup_ticket_node
    )
    assert lookup_ticket_via_mcp  # imported client still present


def test_explicit_memory_interface_read_write(tmp_path: Path) -> None:
    """Agent memory is an explicit R/W API — not system-prompt accumulation."""
    memory: MemoryInterface = AgentMemory(MemoryStore(tmp_path / "semantic.sqlite"))

    denied = memory.write(
        "This dish is 100% safe with zero risk.",
        kind="allergen",
        source="test",
    )
    assert denied.ok is False

    saved = memory.write(
        "Emergency orders over 500 USD require approval from Lucía Fernández.",
        source="test",
    )
    assert saved.ok is True
    assert saved.record is not None

    # Seed extras that must not all be dumped into a turn.
    for i in range(10):
        memory.write(
            f"Inventory napkin pack {i}: quantity={i} (confirmed via inventory manager).",
            kind="inventory",
            source="test",
        )

    hits = memory.read("Lucía emergency order 500 USD", limit=DEFAULT_READ_LIMIT)
    assert hits
    assert len(hits) <= DEFAULT_READ_LIMIT
    assert any("500 USD" in h.text for h in hits)

    notes = AgentMemory(MemoryStore(tmp_path / "semantic.sqlite")).format_turn_notes(hits)
    assert "MemoryInterface.read" in notes
    assert "not system prompt" in notes


def test_rag_system_prompt_is_not_used_as_memory_accumulator() -> None:
    """SYSTEM_PROMPT must stay a fixed policy string — never grow with memory."""
    prompt = rag_mod.SYSTEM_PROMPT
    assert "agent_memory" not in prompt.casefold()
    assert "Retrieved agent memory" not in prompt
    before = rag_mod.SYSTEM_PROMPT
    assert before is prompt
    assert rag_mod.SYSTEM_PROMPT == before


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
    store = MemoryStore(tmp_path / "semantic.sqlite")
    store.upsert(
        text="Minimum protein stock is 3 days of inventory.",
        kind="procurement",
        source="test",
    )
    hits = store.search("protein stock rule", limit=3)
    assert hits
    assert "3 days" in hits[0].text
    again = store.upsert(
        text="Minimum protein stock is 3 days of inventory.",
        kind="procurement",
        source="test-2",
    )
    assert again.id == hits[0].id
    assert len(store.list_records()) == 1


def test_memory_backend_docs_explain_sqlite_choice() -> None:
    doc = (
        Path(__file__).resolve().parents[2] / "docs" / "agent" / "MEMORY_BACKEND.md"
    ).read_text(encoding="utf-8")
    assert "SQLite" in doc
    assert "brasaland_kb" in doc
    assert "Redis" in doc
    assert "agent-traces" in doc or "traces" in doc


def test_compiled_graph_routes_ticket_through_recall_then_mcp() -> None:
    compiled = compile_agent_graph()
    assert "recall_memory" in compiled.get_graph().nodes
    assert "lookup_ticket" in compiled.get_graph().nodes
    assert "write_memory" in compiled.get_graph().nodes


def test_memory_interface_docs_forbid_system_prompt_dump() -> None:
    doc = (
        Path(__file__).resolve().parents[2] / "docs" / "agent" / "MEMORY_INTERFACE.md"
    ).read_text(encoding="utf-8")
    assert "MemoryInterface" in doc
    assert "system prompt" in doc.casefold()
    assert "read" in doc and "write" in doc
