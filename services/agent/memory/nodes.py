"""LangGraph nodes that extend the existing agent with recall + write memory."""

from __future__ import annotations

import time
from typing import Any

from services.agent.memory.apply_proposal import decide_from_memory_proposal
from services.agent.memory.interface import DEFAULT_READ_LIMIT, get_agent_memory
from services.agent.memory.proposal import MemoryProposal
from services.agent.memory.store import MemoryRecord
from services.agent.state import AgentState


def _step(
    state: AgentState,
    node_name: str,
    status: str,
    started: float,
    *,
    notes: str | None = None,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "node_name": node_name,
        "sequence": len(state.get("steps") or []) + 1,
        "status": status,
        "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
        "notes": notes,
        "output": output or {},
    }


def _records_from_hits(
    hits: list[Any],
    *,
    kind: str | None,
) -> list[MemoryRecord]:
    out: list[MemoryRecord] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        if kind and hit.get("kind") and hit.get("kind") != kind:
            continue
        text = str(hit.get("text") or "").strip()
        if not text:
            continue
        out.append(
            MemoryRecord(
                id=str(hit.get("id") or ""),
                kind=str(hit.get("kind") or kind or ""),
                text=text,
                source=str(hit.get("source") or ""),
                created_at=str(hit.get("created_at") or ""),
                updated_at=str(hit.get("updated_at") or ""),
                metadata=dict(hit.get("metadata") or {}),
            )
        )
    return out


def recall_memory_node(state: AgentState) -> dict[str, Any]:
    """Explicit ``memory.read`` before tools/RAG (bounded; does not dump the store).

    Does not replace MCP ticket lookup or RAG — only supplements state.
    """
    started = time.perf_counter()
    question = state.get("question") or ""
    memory = get_agent_memory()
    hits = memory.read(question, limit=DEFAULT_READ_LIMIT)
    payload = [h.as_dict() for h in hits]
    return {
        "memory_hits": payload,
        "sources_used": ["memory"] if payload else [],
        "steps": [
            _step(
                state,
                "recall_memory",
                "ok",
                started,
                notes=(
                    f"memory.read hits={len(payload)} "
                    f"limit={DEFAULT_READ_LIMIT} (explicit R/W interface)"
                ),
                output={
                    "source": "memory",
                    "api": "MemoryInterface.read",
                    "hit_count": len(payload),
                    "limit": DEFAULT_READ_LIMIT,
                    "kinds": [h.get("kind") for h in payload],
                    "ids": [h.get("id") for h in payload],
                    "dumped_full_store": False,
                },
            )
        ],
    }


def write_memory_node(state: AgentState) -> dict[str, Any]:
    """Persist from the generate-call ``memory_proposal`` when applicable.

    Self-evaluation is the structured field from the **same** model call as the
    user answer — not a second LLM call. CONTEXT policy still gates writes.
    """
    started = time.perf_counter()
    memory = get_agent_memory()
    written: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []

    raw_proposal = state.get("memory_proposal")
    proposal: MemoryProposal | dict[str, Any] | None
    if isinstance(raw_proposal, MemoryProposal):
        proposal = raw_proposal
    elif isinstance(raw_proposal, dict):
        proposal = raw_proposal
    else:
        proposal = None

    kind_hint = None
    if isinstance(proposal, MemoryProposal) and proposal.fact:
        from services.agent.memory.policy import infer_kind

        kind_hint = infer_kind(proposal.fact)
    elif isinstance(proposal, dict) and proposal.get("fact"):
        from services.agent.memory.policy import infer_kind

        kind_hint = infer_kind(str(proposal["fact"]))

    related = []
    if proposal and (
        (isinstance(proposal, MemoryProposal) and proposal.fact)
        or (isinstance(proposal, dict) and proposal.get("fact"))
    ):
        fact_text = (
            proposal.fact
            if isinstance(proposal, MemoryProposal)
            else str(proposal.get("fact") or "")
        )
        related = list(memory.related_for_self_eval(fact_text, kind=kind_hint))
    seen = {r.id for r in related if r.id}
    for hit_rec in _records_from_hits(state.get("memory_hits") or [], kind=kind_hint):
        if hit_rec.id and hit_rec.id in seen:
            continue
        related.append(hit_rec)
        if hit_rec.id:
            seen.add(hit_rec.id)

    decision = decide_from_memory_proposal(proposal, existing=related)
    evaluations.append(decision.as_dict())

    if decision.remember and decision.fact and decision.kind:
        result = memory.write(
            decision.fact,
            kind=decision.kind,
            source="memory_proposal",
            metadata={
                "self_eval": "structured_memory_proposal",
                "verdict": decision.verdict,
                "why": decision.reason,
                "proposal": decision.proposal,
            },
            replace_id=decision.replace_id if decision.verdict == "change" else None,
        )
        if result.ok and result.record is not None:
            written.append(result.record.as_dict())
        else:
            rejected.append(
                {
                    "fact": decision.fact,
                    "reason": result.decision.reason,
                }
            )
    else:
        rejected.append(
            {
                "fact": decision.fact,
                "reason": f"self_eval:{decision.verdict}",
                "detail": decision.reason,
            }
        )

    return {
        "memory_writes": written,
        "memory_self_evaluations": evaluations,
        "sources_used": ["memory"] if written else [],
        "route": "done",
        "steps": [
            _step(
                state,
                "write_memory",
                "ok",
                started,
                notes=(
                    f"memory_proposal verdict={decision.verdict} "
                    f"wrote={len(written)} (same-call structured field; not always write)"
                ),
                output={
                    "source": "memory",
                    "api": "memory_proposal+MemoryInterface.write",
                    "always_write": False,
                    "second_model_call": False,
                    "written_count": len(written),
                    "rejected_count": len(rejected),
                    "written_ids": [w.get("id") for w in written],
                    "self_evaluations": evaluations,
                    "rejected": rejected[:5],
                    "memory_proposal": decision.proposal,
                },
            )
        ],
    }


def recalled_records_from_state(state: AgentState) -> list[Any]:
    """Rebuild MemoryRecord-like dicts already loaded by ``recall_memory`` (no re-dump)."""
    return _records_from_hits(state.get("memory_hits") or [], kind=None)[
        :DEFAULT_READ_LIMIT
    ]
