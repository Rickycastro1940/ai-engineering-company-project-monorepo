"""Complete confirmation cycles: approve→recall and reject→unchanged memory."""

from __future__ import annotations

from pathlib import Path

from services.agent.memory.audit import MemoryAuditLog, MemoryDecisionAudit
from services.agent.memory.confirmation import resolve_memory_confirmation_node
from services.agent.memory.interface import AgentMemory
from services.agent.memory.nodes import recall_memory_node, write_memory_node
from services.agent.memory.pending import PendingProposalStore
from services.agent.memory.store import MemoryStore

FACT = "Emergency orders over 500 USD require Procurement Manager approval."


def _patch(monkeypatch, *, pstore, mem, audit_path: Path):
    monkeypatch.setattr(
        "services.agent.memory.nodes.get_pending_store", lambda: pstore
    )
    monkeypatch.setattr(
        "services.agent.memory.nodes.get_agent_memory", lambda: mem
    )
    monkeypatch.setattr(
        "services.agent.memory.nodes.log_memory_decision",
        lambda **kw: _audit(audit_path, **kw),
    )
    monkeypatch.setattr(
        "services.agent.memory.confirmation.get_pending_store", lambda: pstore
    )
    monkeypatch.setattr(
        "services.agent.memory.confirmation.get_agent_memory", lambda: mem
    )
    monkeypatch.setattr(
        "services.agent.memory.confirmation.log_memory_decision",
        lambda **kw: _audit(audit_path, **kw),
    )


def _audit(audit_path: Path, **kw):
    return MemoryAuditLog(audit_path).append(
        MemoryDecisionAudit(
            id="cycle",
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


def _propose_turn(monkeypatch, tmp_path: Path):
    pstore = PendingProposalStore(tmp_path / "pending.json")
    mem = AgentMemory(MemoryStore(tmp_path / "sem.sqlite"))
    audit_path = tmp_path / "audit.jsonl"
    _patch(monkeypatch, pstore=pstore, mem=mem, audit_path=audit_path)

    out = write_memory_node(
        {
            "question": "When do emergency orders need approval?",
            "answer": (
                f"{FACT}\n\n"
                f'Would you like me to remember this for later: "{FACT}"?'
            ),
            "memory_proposal": {
                "applicable": True,
                "action": "add",
                "fact": FACT,
                "previous_fact": None,
                "why": "New durable supplier-ordering fact.",
            },
            "memory_hits": [],
            "steps": [],
            "sources_used": [],
        }
    )
    assert out["memory_writes"] == []
    assert out["memory_pending_proposal"] is not None
    assert pstore.has_pending()
    assert mem._store.count() == 0
    return pstore, mem, audit_path


def test_cycle_a_approve_then_recall_in_future_interaction(
    tmp_path: Path, monkeypatch
) -> None:
    """Cycle A: propose → approve → later recall hits the stored fact."""
    pstore, mem, audit_path = _propose_turn(monkeypatch, tmp_path)

    # A2 — approve
    approved = resolve_memory_confirmation_node(
        {"question": "yes", "steps": [], "sources_used": []}
    )
    assert approved["memory_confirmation"]["outcome"] == "approved"
    assert approved["memory_writes"]
    assert pstore.get() is None
    assert any(FACT in r.text for r in mem._store.list_records())
    entries = MemoryAuditLog(audit_path).list_entries()
    assert entries[-1]["outcome"] == "approved"
    assert entries[-1]["originating_message"] == "yes"
    assert "timestamp" in entries[-1]
    assert "proposal" in entries[-1]

    # A3 — future interaction recalls the fact
    recalled = recall_memory_node(
        {
            "question": "Remind me of the emergency order approval rule.",
            "steps": [],
            "sources_used": [],
        }
    )
    assert recalled["memory_hits"]
    assert any(FACT in (h.get("text") or "") for h in recalled["memory_hits"])


def test_cycle_b_reject_leaves_memory_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    """Cycle B: propose → reject → later recall does not surface that fact."""
    pstore, mem, audit_path = _propose_turn(monkeypatch, tmp_path)
    assert mem._store.count() == 0

    # B2 — reject
    rejected = resolve_memory_confirmation_node(
        {"question": "no", "steps": [], "sources_used": []}
    )
    assert rejected["memory_confirmation"]["outcome"] == "rejected"
    assert rejected.get("memory_writes") == []
    assert pstore.get() is None
    assert mem._store.count() == 0
    entries = MemoryAuditLog(audit_path).list_entries()
    assert entries[-1]["outcome"] == "rejected"
    assert entries[-1]["originating_message"] == "no"

    # B3 — future interaction: no semantic hit for the rejected proposal
    recalled = recall_memory_node(
        {
            "question": "Remind me of the emergency order approval rule.",
            "steps": [],
            "sources_used": [],
        }
    )
    assert recalled["memory_hits"] == []
    assert mem._store.count() == 0


def test_confirmation_cycles_are_documented() -> None:
    doc = Path("docs/agent/MEMORY_CONFIRMATION.md").read_text(encoding="utf-8")
    assert "Complete cycles" in doc
    assert "Cycle A" in doc and "Cycle B" in doc
    assert "approve" in doc.casefold()
    assert "reject" in doc.casefold()
    assert "future" in doc.casefold()
    assert "unchanged" in doc.casefold()
    assert FACT in doc or "500 USD" in doc
