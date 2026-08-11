"""Agent memory: CONTEXT policy + structured memory_proposal (one generate call)."""

from __future__ import annotations

from pathlib import Path

from data.pipelines import rag as rag_mod
from services.agent.generation import parse_agent_turn_json
from services.agent.graph import REQUIRED_NODES, build_agent_graph, compile_agent_graph
from services.agent.memory.apply_proposal import decide_from_memory_proposal
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
from services.agent.memory.proposal import MemoryProposal
from services.agent.memory.store import MemoryRecord, MemoryStore
from services.agent.nodes import lookup_ticket_node
from services.agent.tools.mcp_incidents import lookup_ticket_via_mcp


def test_memory_policy_matches_context_company_md_exactly() -> None:
    """Forbidden + memorable domains must be those specified in CONTEXT-company.md."""
    ctx = context_company_text()
    assert CONTEXT_COMPANY_PATH.is_file()

    assert "never convert" in ctx.casefold()
    assert "zero risk" in ctx.casefold()
    assert "100% safe" in ctx.casefold()
    assert "there is not enough information available." in ctx.casefold()
    assert "chunks" in ctx.casefold() and "scores" in ctx.casefold()
    assert "qdrant" in ctx.casefold()

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
    ok = evaluate_memory_candidate(
        "Emergency orders over 500 USD require Procurement Manager approval."
    )
    assert ok.allowed is True
    assert ok.kind == "supplier_ordering"

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


def test_structured_turn_parses_answer_and_memory_proposal() -> None:
    """One JSON object → user answer + optional memory_proposal (no second call)."""
    raw = """
    {
      "answer": "Locations must keep 3 days of main protein inventory.",
      "memory_proposal": {
        "applicable": true,
        "action": "add",
        "fact": "Locations must keep 3 days of main protein inventory.",
        "previous_fact": null,
        "why": "New durable supplier-ordering fact."
      }
    }
    """
    turn = parse_agent_turn_json(raw)
    assert "3 days" in turn.answer
    assert turn.memory_proposal.applicable is True
    assert turn.memory_proposal.action == "add"
    assert turn.memory_proposal.fact is not None
    assert "why" in (turn.memory_proposal.why or "").casefold() or turn.memory_proposal.why


def test_memory_proposal_self_eval_not_always_write() -> None:
    """applicable=false → skip; add → write; change → replace; duplicates skipped."""
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

    skip = decide_from_memory_proposal(
        MemoryProposal(applicable=False, why="nothing new"),
        existing=existing,
    )
    assert skip.remember is False
    assert skip.verdict == "skip_not_applicable"

    add = decide_from_memory_proposal(
        MemoryProposal(
            applicable=True,
            action="add",
            fact="Brasa Points loyalty tiers and redemption rules apply to members.",
            why="New loyalty fact",
        ),
        existing=existing,
    )
    assert add.remember is True
    assert add.verdict == "add"

    change = decide_from_memory_proposal(
        MemoryProposal(
            applicable=True,
            action="change",
            fact="Emergency orders over 1000 USD require Procurement Manager approval.",
            previous_fact="Emergency orders over 500 USD require Procurement Manager approval.",
            why="Corrected approval threshold",
        ),
        existing=existing,
    )
    assert change.remember is True
    assert change.verdict == "change"
    assert change.replace_id == "m1"

    dup = decide_from_memory_proposal(
        MemoryProposal(
            applicable=True,
            action="add",
            fact="Emergency orders over 500 USD require Procurement Manager approval.",
            why="repeat",
        ),
        existing=existing,
    )
    assert dup.remember is False
    assert dup.verdict == "skip_duplicate"


def test_write_memory_node_uses_structured_proposal(tmp_path: Path, monkeypatch) -> None:
    store = MemoryStore(tmp_path / "semantic.sqlite")
    memory = AgentMemory(store)
    monkeypatch.setattr(
        "services.agent.memory.nodes.get_agent_memory",
        lambda: memory,
    )

    state = {
        "question": "emergency order approval?",
        "answer": "Emergency orders over 500 USD require Procurement Manager approval.",
        "memory_proposal": {
            "applicable": True,
            "action": "add",
            "fact": "Emergency orders over 500 USD require Procurement Manager approval.",
            "previous_fact": None,
            "why": "New durable supplier-ordering fact from grounded KB answer.",
        },
        "memory_hits": [],
        "steps": [],
        "sources_used": [],
    }
    out1 = write_memory_node(state)  # type: ignore[arg-type]
    assert out1["memory_writes"]
    assert out1["memory_self_evaluations"][0]["verdict"] == "add"
    assert out1["steps"][0]["output"]["always_write"] is False
    assert out1["steps"][0]["output"]["second_model_call"] is False

    # Same proposal again → skip_duplicate (not always write).
    out2 = write_memory_node(state)  # type: ignore[arg-type]
    assert out2["memory_writes"] == []
    assert out2["memory_self_evaluations"][0]["verdict"] == "skip_duplicate"

    # Change proposal replaces prior fact.
    prior = store.list_records()[0].text
    out3 = write_memory_node(
        {
            **state,
            "memory_proposal": {
                "applicable": True,
                "action": "change",
                "fact": "Emergency orders over 1000 USD require Procurement Manager approval.",
                "previous_fact": prior,
                "why": "Corrected approval threshold",
            },
        }
    )  # type: ignore[arg-type]
    assert out3["memory_writes"]
    assert out3["memory_self_evaluations"][0]["verdict"] == "change"
    texts = [r.text for r in store.list_records()]
    assert any("1000 USD" in t for t in texts)
    assert not any("500 USD" in t and "1000" not in t for t in texts)


def test_write_memory_skips_when_proposal_not_applicable() -> None:
    out = write_memory_node(
        {
            "question": "status of ticket BRS-000002?",
            "answer": "Ticket BRS-000002 is ABIERTO.",
            "memory_proposal": {
                "applicable": False,
                "action": None,
                "fact": None,
                "previous_fact": None,
                "why": "ticket_path_not_in_context_memorable_domains",
            },
            "memory_hits": [],
            "steps": [],
            "sources_used": [],
        }
    )
    assert out["memory_writes"] == []
    assert out["memory_self_evaluations"][0]["verdict"] == "skip_not_applicable"


def test_documented_nothing_to_remember_examples() -> None:
    """At least three interactions must be dismissible as nothing to remember."""
    from pathlib import Path

    from services.agent.memory.proposal import NOTHING_TO_REMEMBER_EXAMPLES

    assert len(NOTHING_TO_REMEMBER_EXAMPLES) >= 3

    doc = (
        Path(__file__).resolve().parents[2] / "docs" / "agent" / "MEMORY_SELF_EVAL.md"
    ).read_text(encoding="utf-8")
    assert "Examples that must NOT generate a proposal" in doc

    required_ids = {"ticket_status", "inventory_quantity", "unknown_answer"}
    assert required_ids <= {ex["id"] for ex in NOTHING_TO_REMEMBER_EXAMPLES}

    for ex in NOTHING_TO_REMEMBER_EXAMPLES:
        assert ex["user"].strip()
        assert ex["why_dismiss"].strip()
        assert ex["why_code"].strip()
        # Doc mirrors each example's user question.
        assert ex["user"] in doc or ex["user"].replace("'", "’") in doc
        # Dismissing via structured proposal must not write.
        decision = decide_from_memory_proposal(
            MemoryProposal.nothing_to_remember(ex["why_code"]),
            existing=[],
        )
        assert decision.remember is False
        assert decision.verdict == "skip_not_applicable"

    # Model instructions also name the three dismiss classes.
    from services.agent.generation import STRUCTURED_TURN_INSTRUCTIONS

    lowered = STRUCTURED_TURN_INSTRUCTIONS.casefold()
    assert "ticket" in lowered and "inventory" in lowered
    assert "there is not enough information available" in lowered
    assert "applicable=false" in lowered
    assert "default" in lowered
