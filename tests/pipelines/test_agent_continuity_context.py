"""Evaluate: secured agent is the same Brasaland agent from prior sprints.

Proves Part 2 harness/guardrails wrap — and do not replace — the Part 1
LangGraph + MCP + memory agent, and that tools / KB / domain match
``CONTEXT-company.md``.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from data.pipelines import rag as rag_mod
from data.process.rag import COLLECTION_NAME
from services.agent import generation as generation_mod
from services.agent.graph import REQUIRED_NODES, build_agent_graph, compile_agent_graph
from services.agent.grounding import ALLOWED_SOURCE_DOCUMENTS, KB_DIR, load_context_company
from services.agent.harness.system_prompt import agent_system_prompt
from services.agent.nodes import lookup_ticket_node, retrieve_node
from services.agent.tools import lookup_inventory, lookup_ticket_via_mcp
from services.agent.tools import ticket_lookup as ticket_lookup_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_PATH = REPO_ROOT / "CONTEXT-company.md"

# Part 1 + MCP + memory nodes that must still exist on the secured graph.
PRIOR_SPRINT_NODES = (
    "receive_question",
    "decide_route",
    "retrieve",
    "generate",
    "lookup_ticket",
    "answer_ticket",
    "ticket_fallback",
    "lookup_inventory",
    "answer_inventory",
    "inventory_fallback",
    "resolve_memory_confirmation",
    "recall_memory",
    "write_memory",
)

# CONTEXT-company.md KB files (exact names).
CONTEXT_KB_FILES = (
    "brasaland-supplier-ordering.en.md",
    "brasaland-waste-protocol.en.md",
    "brasaland-loyalty-program.en.md",
    "brasaland-menu-allergens.en.md",
)


def test_secured_graph_still_includes_prior_sprint_nodes() -> None:
    """Harness adds guardrails around the same agent — prior nodes remain required."""
    for name in PRIOR_SPRINT_NODES:
        assert name in REQUIRED_NODES, f"missing prior-sprint node: {name}"
    # Part 2 wrap (not a replacement agent).
    assert "input_guardrail" in REQUIRED_NODES
    assert "output_guardrail" in REQUIRED_NODES

    graph = build_agent_graph()
    registered = set(graph.nodes.keys()) - {"__start__", "__end__"}
    for name in PRIOR_SPRINT_NODES:
        assert name in registered, f"graph missing node: {name}"

    compiled = compile_agent_graph()
    assert hasattr(compiled, "invoke")


def test_ticket_tool_still_uses_mcp_not_direct_http() -> None:
    """Same MCP ticket path from the MCP / memory sprints."""
    source = inspect.getsource(lookup_ticket_node)
    assert "lookup_ticket_via_mcp" in source
    assert "ticket_lookup.lookup_ticket(" not in source
    # Direct HTTP helper remains deprecated and is not the graph path.
    assert "deprecated" in (ticket_lookup_mod.lookup_ticket.__doc__ or "").casefold()
    assert callable(lookup_ticket_via_mcp)


def test_retrieve_still_reuses_company_rag_pipeline() -> None:
    """RAG node still calls ``data.pipelines.rag.retrieve`` (not a new KB agent)."""
    source = inspect.getsource(retrieve_node)
    assert "retrieve(" in source
    assert rag_mod.retrieve.__module__.startswith("data.pipelines")
    assert COLLECTION_NAME == "brasaland_kb"
    # Generation still composes on the same RAG system prompt base.
    assert generation_mod.SYSTEM_PROMPT is rag_mod.SYSTEM_PROMPT
    prompt = agent_system_prompt(base=rag_mod.SYSTEM_PROMPT)
    assert rag_mod.SYSTEM_PROMPT.strip() in prompt


def test_inventory_tool_still_read_only_company_tool() -> None:
    assert callable(lookup_inventory)
    from services.agent.harness.tools import authorize_tool_call

    assert authorize_tool_call("lookup_inventory", {"name_contains": "tomato"}).allowed
    denied = authorize_tool_call("lookup_inventory", {"action": "update", "quantity": 1})
    assert denied.allowed is False


def test_kb_files_and_topics_match_context_company_md() -> None:
    """Knowledge base on disk matches CONTEXT-company.md exactly."""
    ctx = load_context_company()
    assert CONTEXT_PATH.is_file()
    assert "Colombia" in ctx and "Florida" in ctx
    assert "brasaland_kb" in ctx
    assert "salesperson perspective" in ctx.casefold()

    for filename in CONTEXT_KB_FILES:
        path = KB_DIR / filename
        assert path.is_file(), f"missing CONTEXT KB file: {filename}"
        assert filename in ctx

    assert ALLOWED_SOURCE_DOCUMENTS == {
        "supplier-ordering",
        "waste-protocol",
        "loyalty-program",
        "menu-allergens",
    }


def test_harness_domain_matches_context_company_md() -> None:
    """Secured system prompt domain = Brasaland CONTEXT (not a generic agent)."""
    ctx = load_context_company()
    prompt = agent_system_prompt(base=rag_mod.SYSTEM_PROMPT)

    # Shared identity / restrictions (must appear in both CONTEXT and prompt).
    for needle in (
        "Brasaland",
        "Colombia",
        "Florida",
        "Mariana",
        "Felipe Guerrero",
        "Lucía Fernández",
        "500 USD",
        "salesperson perspective",
        "never convert",
        "zero risk",
        "100% safe",
        "There is not enough information available.",
        "Brasa Points",
    ):
        assert needle.casefold() in ctx.casefold(), f"CONTEXT missing: {needle}"
        assert needle.casefold() in prompt.casefold(), f"prompt missing: {needle}"

    # KB topic areas named in the harness (CONTEXT indexes the matching files).
    for topic in ("supplier ordering", "waste", "allergens"):
        assert topic.casefold() in prompt.casefold(), topic
    assert "brasaland-supplier-ordering.en.md" in ctx
    assert "brasaland-waste-protocol.en.md" in ctx
    assert "brasaland-menu-allergens.en.md" in ctx
    assert "brasaland-loyalty-program.en.md" in ctx


def test_context_key_people_and_restrictions_unchanged() -> None:
    ctx = load_context_company()
    assert "Mariana" in ctx and "CEO" in ctx
    assert "Felipe Guerrero" in ctx and "Operations Director" in ctx
    assert "Lucía Fernández" in ctx and "Procurement Manager" in ctx
    assert "500 USD" in ctx
    assert "never convert" in ctx.casefold()
    assert "zero risk" in ctx.casefold()
    assert "100% safe" in ctx.casefold()
    assert "There is not enough information available." in ctx
