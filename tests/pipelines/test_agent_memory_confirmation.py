"""User confirmation: explicit intent, one pending, audit log, resume."""

from __future__ import annotations

from pathlib import Path

from services.agent.graph import REQUIRED_NODES, build_agent_graph
from services.agent.memory.audit import MemoryAuditLog, MemoryDecisionAudit
from services.agent.memory.confirmation import resolve_memory_confirmation_node
from services.agent.memory.intent import ConfirmationIntent, classify_confirmation_intent
from services.agent.memory.interface import AgentMemory
from services.agent.memory.nodes import write_memory_node
from services.agent.memory.pending import (
    PendingProposalStore,
    new_pending_from_proposal,
)
from services.agent.memory.store import MemoryStore


def _patch_confirmation(monkeypatch, *, pstore, mem, audit_path: Path):
    monkeypatch.setattr(
        "services.agent.memory.confirmation.get_pending_store", lambda: pstore
    )
    monkeypatch.setattr(
        "services.agent.memory.confirmation.get_agent_memory", lambda: mem
    )

    def _log(**kw):
        return MemoryAuditLog(audit_path).append(
            MemoryDecisionAudit(
                id="a1",
                timestamp="t",
                outcome=kw["outcome"],
                originating_message=kw["originating_message"],
                proposal=kw["proposal"],
                intent=kw.get("intent"),
                intent_reason=kw.get("intent_reason"),
                residual_question=kw.get("residual_question"),
                edited_fact=kw.get("edited_fact"),
            )
        )

    monkeypatch.setattr(
        "services.agent.memory.confirmation.log_memory_decision", _log
    )


def test_resolve_memory_confirmation_is_on_graph() -> None:
    assert "resolve_memory_confirmation" in REQUIRED_NODES
    graph = build_agent_graph()
    assert "resolve_memory_confirmation" in graph.nodes


def test_intent_classifier_is_explicit_not_substring_yes() -> None:
    pending = new_pending_from_proposal(
        {"fact": "Locations must keep 3 days of protein stock.", "action": "add"},
        originating_message="protein stock?",
        kind="supplier_ordering",
    )
    # Must NOT approve merely because "yes" appears inside another word/phrase.
    yesterday = classify_confirmation_intent(
        "What about yesterday's waste escalation thresholds?",
        pending,
    )
    assert yesterday.intent == ConfirmationIntent.TOPIC_CHANGE

    approve = classify_confirmation_intent("yes", pending)
    assert approve.intent == ConfirmationIntent.APPROVE

    approve_residual = classify_confirmation_intent(
        "yes, what is the status of ticket BRS-000002?",
        pending,
    )
    assert approve_residual.intent == ConfirmationIntent.APPROVE
    assert approve_residual.residual_question is not None
    assert "BRS-000002" in approve_residual.residual_question

    reject = classify_confirmation_intent("no thanks", pending)
    assert reject.intent == ConfirmationIntent.REJECT

    edit = classify_confirmation_intent(
        "actually, remember: Emergency orders over 500 USD need Lucía Fernández.",
        pending,
    )
    assert edit.intent == ConfirmationIntent.EDIT
    assert edit.edited_fact is not None
    assert "500 USD" in edit.edited_fact

    ambiguous = classify_confirmation_intent("maybe later", pending)
    assert ambiguous.intent == ConfirmationIntent.AMBIGUOUS


def test_one_pending_proposal_limit(tmp_path: Path, monkeypatch) -> None:
    pending_path = tmp_path / "pending.json"
    store = PendingProposalStore(pending_path)
    monkeypatch.setattr(
        "services.agent.memory.nodes.get_pending_store",
        lambda: store,
    )
    monkeypatch.setattr(
        "services.agent.memory.nodes.get_agent_memory",
        lambda: AgentMemory(MemoryStore(tmp_path / "semantic.sqlite")),
    )
    monkeypatch.setattr(
        "services.agent.memory.nodes.log_memory_decision",
        lambda **kw: None,
    )

    first = {
        "question": "protein stock?",
        "answer": (
            'Would you like me to remember this for later: '
            '"Locations must keep 3 days of main protein inventory."?'
        ),
        "memory_proposal": {
            "applicable": True,
            "action": "add",
            "fact": "Locations must keep 3 days of main protein inventory.",
            "previous_fact": None,
            "why": "new",
        },
        "memory_hits": [],
        "steps": [],
        "sources_used": [],
    }
    out1 = write_memory_node(first)  # type: ignore[arg-type]
    assert out1["memory_pending_proposal"] is not None
    assert store.has_pending()

    out2 = write_memory_node(first)  # type: ignore[arg-type]
    assert out2["steps"][0]["output"].get("suppressed_second_proposal") is True
    assert out2["memory_writes"] == []


def test_default_discard_on_topic_change_and_ambiguous(
    tmp_path: Path, monkeypatch
) -> None:
    pstore = PendingProposalStore(tmp_path / "pending.json")
    mem = AgentMemory(MemoryStore(tmp_path / "sem.sqlite"))
    audit_path = tmp_path / "audit.jsonl"
    pending = new_pending_from_proposal(
        {
            "fact": "Locations must keep 3 days of main protein inventory.",
            "action": "add",
            "why": "new",
        },
        originating_message="protein?",
        kind="supplier_ordering",
    )
    pstore.set(pending)
    _patch_confirmation(monkeypatch, pstore=pstore, mem=mem, audit_path=audit_path)

    out = resolve_memory_confirmation_node(
        {
            "question": "What is the status of ticket BRS-000002?",
            "steps": [],
            "sources_used": [],
        }
    )
    assert out["memory_confirmation"]["outcome"] == "discarded_topic_change"
    assert out["question"].startswith("What is the status")
    assert pstore.get() is None
    assert out["route"] == "decide"

    pstore.set(pending)
    out2 = resolve_memory_confirmation_node(
        {"question": "hmm not sure", "steps": [], "sources_used": []}
    )
    assert out2["memory_confirmation"]["outcome"] == "discarded_ambiguous"
    assert pstore.get() is None


def test_approve_writes_and_resume_with_residual(tmp_path: Path, monkeypatch) -> None:
    pstore = PendingProposalStore(tmp_path / "pending.json")
    mem = AgentMemory(MemoryStore(tmp_path / "sem.sqlite"))
    audit_path = tmp_path / "audit.jsonl"
    pending = new_pending_from_proposal(
        {
            "fact": "Locations must keep 3 days of main protein inventory.",
            "action": "add",
            "why": "new",
        },
        originating_message="protein?",
        kind="supplier_ordering",
    )
    pstore.set(pending)
    _patch_confirmation(monkeypatch, pstore=pstore, mem=mem, audit_path=audit_path)

    out = resolve_memory_confirmation_node(
        {
            "question": "yes, how many kg of tomatoes are in stock?",
            "steps": [],
            "sources_used": [],
        }
    )
    assert out["memory_confirmation"]["outcome"] == "approved"
    assert out["memory_writes"]
    assert "tomatoes" in (out.get("question") or "")
    assert pstore.get() is None
    entries = MemoryAuditLog(audit_path).list_entries()
    assert entries
    assert entries[-1]["outcome"] == "approved"
    assert "originating_message" in entries[-1]
    assert "timestamp" in entries[-1]
    assert "proposal" in entries[-1]


def test_confirmation_docs_exist() -> None:
    doc = Path("docs/agent/MEMORY_CONFIRMATION.md")
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "explicit intent" in text.casefold()
    assert "one pending" in text.casefold()
    assert "discard" in text.casefold()
    assert "audit" in text.casefold()
    assert "resume" in text.casefold()
