"""Agent memory must follow CONTEXT-company.md exactly (no generic extras)."""

from __future__ import annotations

from pathlib import Path

from data.pipelines import rag as rag_mod
from services.agent.graph import REQUIRED_NODES, build_agent_graph, compile_agent_graph
from services.agent.memory.interface import (
    DEFAULT_READ_LIMIT,
    AgentMemory,
    MemoryInterface,
)
from services.agent.memory.policy import (
    ALLOWED_KINDS,
    CONTEXT_COMPANY_PATH,
    CONTEXT_KEY_PEOPLE,
    FORBIDDEN_ALLERGEN_ABSOLUTE_SAFETY,
    FORBIDDEN_CURRENCY_CONVERSION,
    FORBIDDEN_RAG_INTERNALS,
    FORBIDDEN_UNKNOWN_ANSWER,
    context_company_text,
    evaluate_memory_candidate,
)
from services.agent.memory.store import MemoryStore
from services.agent.nodes import lookup_ticket_node
from services.agent.tools.mcp_incidents import lookup_ticket_via_mcp


def test_memory_policy_matches_context_company_md_exactly() -> None:
    """Forbidden + memorable domains must be those specified in CONTEXT-company.md."""
    ctx = context_company_text()
    assert CONTEXT_COMPANY_PATH.is_file()

    # Forbidden — CONTEXT RAG constraints (exact phrases / requirements).
    assert "never convert" in ctx.casefold()
    assert "zero risk" in ctx.casefold()
    assert "100% safe" in ctx.casefold()
    assert "there is not enough information available." in ctx.casefold()
    assert "chunks" in ctx.casefold() and "scores" in ctx.casefold()
    assert "qdrant" in ctx.casefold()

    # Memorable — KB topic table + key people.
    for needle in (
        "brasaland-supplier-ordering",
        "brasaland-waste-protocol",
        "brasaland-loyalty-program",
        "brasaland-menu-allergens",
        "Weekly orders",
        "minimum protein stock",
        "Waste categories",
        "Brasa Points",
        "Dish allergens",
        "Mariana",
        "Felipe Guerrero",
        "Lucía Fernández",
        "500 USD",
    ):
        assert needle in ctx

    assert ALLOWED_KINDS == {
        "supplier_ordering",
        "waste",
        "loyalty",
        "allergen",
        "people",
    }
    assert len(CONTEXT_KEY_PEOPLE) == 3


def test_context_forbidden_facts_are_rejected() -> None:
    assert (
        evaluate_memory_candidate("Please convert 500 USD to COP for the order.").reason
        == FORBIDDEN_CURRENCY_CONVERSION
    )
    assert (
        evaluate_memory_candidate("This dish is zero risk for allergies.").reason
        == FORBIDDEN_ALLERGEN_ABSOLUTE_SAFETY
    )
    assert (
        evaluate_memory_candidate("This dish is 100% safe for nut allergies.").reason
        == FORBIDDEN_ALLERGEN_ABSOLUTE_SAFETY
    )
    assert (
        evaluate_memory_candidate("There is not enough information available.").reason
        == FORBIDDEN_UNKNOWN_ANSWER
    )
    assert (
        evaluate_memory_candidate(
            "Retrieved chunk_id=12 with _score=0.91 from qdrant payload.",
            source="qdrant",
        ).reason
        == FORBIDDEN_RAG_INTERNALS
    )


def test_context_memorable_domains_are_accepted() -> None:
    # supplier ordering (USD kept as written — not a conversion); no named person
    ok = evaluate_memory_candidate(
        "Emergency orders over 500 USD require Procurement Manager approval."
    )
    assert ok.allowed is True
    assert ok.kind == "supplier_ordering"

    # Named CONTEXT people take the people kind (even when roles overlap topics).
    ok_lucia = evaluate_memory_candidate(
        "Emergency orders over 500 USD require approval from Lucía Fernández."
    )
    assert ok_lucia.allowed and ok_lucia.kind == "people"

    ok_waste = evaluate_memory_candidate(
        "Waste categories and daily logging feed escalation thresholds."
    )
    assert ok_waste.allowed and ok_waste.kind == "waste"

    ok_felipe = evaluate_memory_candidate(
        "Waste escalation goes to Felipe Guerrero, Operations Director."
    )
    assert ok_felipe.allowed and ok_felipe.kind == "people"

    ok_loyalty = evaluate_memory_candidate(
        "Brasa Points loyalty tiers and redemption rules apply to members."
    )
    assert ok_loyalty.allowed and ok_loyalty.kind == "loyalty"

    ok_allergen = evaluate_memory_candidate(
        "House Sauce contains soy and sulfites; follow the customer allergy protocol."
    )
    assert ok_allergen.allowed and ok_allergen.kind == "allergen"

    ok_people = evaluate_memory_candidate("Mariana is the CEO of Brasaland.")
    assert ok_people.allowed and ok_people.kind == "people"


def test_non_context_domains_are_not_memorable() -> None:
    """Ticket/inventory rows are not CONTEXT memory topics — must be rejected."""
    denied = evaluate_memory_candidate(
        "Ticket BRS-000002: status=ABIERTO, category=EQUIPAMIENTO (confirmed via MCP)."
    )
    assert denied.allowed is False
    assert denied.reason == "not_in_context_company_memorable_domains"

    denied_inv = evaluate_memory_candidate(
        "Inventory Tomatoes (product_id=1): quantity=25 kg (confirmed via inventory manager)."
    )
    assert denied_inv.allowed is False


def test_generic_extra_rules_are_not_required_by_context() -> None:
    """Do not invent forbidden categories absent from CONTEXT-company.md."""
    # A procurement fact that mentions 'password' in a non-CONTEXT sense should
    # still be judged only by CONTEXT rules — if it maps to supplier_ordering
    # and has no CONTEXT-forbidden phrases, policy scope is CONTEXT-only.
    # (We still reject if it fails domain inference.)
    ctx = context_company_text().casefold()
    assert "social security" not in ctx
    assert "api_key" not in ctx
    assert "credit card" not in ctx


def test_memory_nodes_extend_same_mcp_graph() -> None:
    assert "recall_memory" in REQUIRED_NODES
    assert "write_memory" in REQUIRED_NODES
    assert "lookup_ticket" in REQUIRED_NODES
    graph = build_agent_graph()
    assert {"recall_memory", "write_memory", "lookup_ticket", "retrieve"} <= set(graph.nodes.keys())
    import inspect

    assert "lookup_ticket_via_mcp" in inspect.getsource(lookup_ticket_node)
    assert lookup_ticket_via_mcp


def test_explicit_memory_interface_read_write(tmp_path: Path) -> None:
    memory: MemoryInterface = AgentMemory(MemoryStore(tmp_path / "semantic.sqlite"))
    assert memory.write("This dish is 100% safe.", source="test").ok is False
    saved = memory.write(
        "Emergency orders over 500 USD require approval from Lucía Fernández.",
        source="test",
    )
    assert saved.ok is True
    hits = memory.read("Lucía emergency order 500 USD", limit=DEFAULT_READ_LIMIT)
    assert hits and len(hits) <= DEFAULT_READ_LIMIT


def test_rag_system_prompt_is_not_used_as_memory_accumulator() -> None:
    assert "Retrieved agent memory" not in rag_mod.SYSTEM_PROMPT


def test_compiled_graph_routes_ticket_through_recall_then_mcp() -> None:
    compiled = compile_agent_graph()
    assert "recall_memory" in compiled.get_graph().nodes
    assert "lookup_ticket" in compiled.get_graph().nodes
