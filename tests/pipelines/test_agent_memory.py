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
from services.agent.memory.nodes import write_memory_node
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
from services.agent.memory.self_evaluate import self_evaluate_worth_remembering
from services.agent.memory.store import MemoryRecord, MemoryStore
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


def test_self_eval_criterion_new_corrected_not_always() -> None:
    """Explicit criterion: remember only new or corrected facts — not always."""
    existing = [
        MemoryRecord(
            id="m1",
            kind="supplier_ordering",
            text="Emergency orders over 500 USD require Procurement Manager approval.",
            source="test",
            created_at="t0",
            updated_at="t0",
        )
    ]

    # Exact duplicate → skip (must not always write).
    dup = self_evaluate_worth_remembering(
        "Emergency orders over 500 USD require Procurement Manager approval.",
        kind="supplier_ordering",
        existing=existing,
    )
    assert dup.remember is False
    assert dup.verdict == "skip_duplicate"

    # Near-paraphrase / redundant → skip.
    red = self_evaluate_worth_remembering(
        "Emergency orders over 500 USD require Procurement Manager approval",
        kind="supplier_ordering",
        existing=existing,
    )
    assert red.remember is False
    assert red.verdict in {"skip_duplicate", "skip_redundant"}

    # Numeric correction → remember as corrected.
    corr = self_evaluate_worth_remembering(
        "Emergency orders over 1000 USD require Procurement Manager approval.",
        kind="supplier_ordering",
        existing=existing,
    )
    assert corr.remember is True
    assert corr.verdict == "corrected"
    assert corr.related_id == "m1"

    # Unrelated domain fact → new.
    fresh = self_evaluate_worth_remembering(
        "Brasa Points loyalty tiers and redemption rules apply to members.",
        kind="loyalty",
        existing=existing,
    )
    assert fresh.remember is True
    assert fresh.verdict == "new"

    # Empty interaction → skip.
    empty = self_evaluate_worth_remembering("", kind=None, existing=[])
    assert empty.remember is False
    assert empty.verdict == "skip_no_candidate"


def test_write_memory_node_self_evaluates_before_write(tmp_path: Path, monkeypatch) -> None:
    """write_memory must self-evaluate; duplicate interactions do not re-write."""
    store = MemoryStore(tmp_path / "semantic.sqlite")
    memory = AgentMemory(store)
    monkeypatch.setattr(
        "services.agent.memory.nodes.get_agent_memory",
        lambda: memory,
    )

    first = {
        "question": "emergency order approval?",
        "answer": "Emergency orders over 500 USD require Procurement Manager approval.",
        "retrieved": [{"source_document": "brasaland-supplier-ordering.en.md"}],
        "memory_hits": [],
        "steps": [],
        "sources_used": [],
    }
    out1 = write_memory_node(first)  # type: ignore[arg-type]
    assert out1["memory_writes"]
    assert out1["memory_self_evaluations"][0]["verdict"] == "new"
    assert out1["steps"][0]["output"]["always_write"] is False

    # Same interaction again → skip_duplicate (not always write).
    out2 = write_memory_node(first)  # type: ignore[arg-type]
    assert out2["memory_writes"] == []
    assert out2["memory_self_evaluations"][0]["verdict"] == "skip_duplicate"

    # Corrected threshold → write with corrected verdict.
    corrected_state = {
        **first,
        "answer": "Emergency orders over 1000 USD require Procurement Manager approval.",
    }
    out3 = write_memory_node(corrected_state)  # type: ignore[arg-type]
    assert out3["memory_writes"]
    assert out3["memory_self_evaluations"][0]["verdict"] == "corrected"
    # Old 500 USD fact replaced.
    texts = [r.text for r in store.list_records()]
    assert any("1000 USD" in t for t in texts)
    assert not any("500 USD" in t and "1000" not in t for t in texts)


def test_write_memory_skips_when_no_candidates() -> None:
    from services.agent.memory.nodes import write_memory_node as _write

    out = _write(
        {
            "question": "status of ticket BRS-000002?",
            "answer": "Ticket BRS-000002 is ABIERTO.",
            "retrieved": [],
            "memory_hits": [],
            "steps": [],
            "sources_used": [],
        }
    )
    assert out["memory_writes"] == []
    assert out["memory_self_evaluations"][0]["verdict"] == "skip_no_candidate"
