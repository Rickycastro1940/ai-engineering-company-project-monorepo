"""LangGraph nodes that extend the existing agent with recall + propose memory.

Part 1: applicable proposals are shown to the user inside the answer. Durable
writes happen only after explicit confirmation intent (see confirmation.py).
At most one pending proposal may exist at a time.
"""

from __future__ import annotations

import time
from typing import Any

from services.agent.memory.apply_proposal import decide_from_memory_proposal
from services.agent.memory.audit import log_memory_decision
from services.agent.memory.interface import DEFAULT_READ_LIMIT, get_agent_memory
from services.agent.memory.pending import get_pending_store, new_pending_from_proposal
from services.agent.memory.proposal import (
    MemoryProposal,
    attach_proposal_question_to_answer,
)
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
    """Explicit ``memory.read`` before tools/RAG (bounded; does not dump the store)."""
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
    """Open at most one pending proposal for the user — never write semantics here.

    If a pending proposal already exists, suppress a second one.
    """
    started = time.perf_counter()
    memory = get_agent_memory()
    pending_store = get_pending_store()
    evaluations: list[dict[str, Any]] = []

    raw_proposal = state.get("memory_proposal")
    proposal: MemoryProposal | dict[str, Any] | None
    if isinstance(raw_proposal, MemoryProposal):
        proposal = raw_proposal
    elif isinstance(raw_proposal, dict):
        proposal = raw_proposal
    else:
        proposal = None

    # Abandon TTL-expired pending before considering a new proposal.
    abandoned = pending_store.take_expired()
    if abandoned is not None:
        log_memory_decision(
            outcome="discarded_pending_ttl",
            originating_message=str(state.get("question") or ""),
            proposal=abandoned.as_dict(),
            intent=None,
            intent_reason="pending_ttl_expired_before_new_proposal",
        )

    # Hard rule: only one *active* pending proposal at a time.
    existing_pending = pending_store.get_active()
    if existing_pending is not None:
        evaluations.append(
            {
                "remember": False,
                "verdict": "skip_pending_already_open",
                "reason": "one_pending_proposal_limit",
                "existing_pending_id": existing_pending.id,
            }
        )
        return {
            "memory_writes": [],
            "memory_pending_proposal": existing_pending.as_dict(),
            "memory_self_evaluations": evaluations,
            "sources_used": [],
            "route": "done",
            "steps": [
                _step(
                    state,
                    "write_memory",
                    "ok",
                    started,
                    notes=(
                        "suppressed new proposal — one pending already open "
                        f"(id={existing_pending.id})"
                    ),
                    output={
                        "source": "memory",
                        "api": "memory_proposal_to_user",
                        "always_write": False,
                        "wrote_to_memory": False,
                        "proposed_to_user": False,
                        "suppressed_second_proposal": True,
                        "pending_proposal": existing_pending.as_dict(),
                        "self_evaluations": evaluations,
                    },
                )
            ],
        }

    kind_hint = None
    if isinstance(proposal, MemoryProposal) and proposal.fact:
        from services.agent.memory.policy import infer_kind

        kind_hint = infer_kind(proposal.fact)
    elif isinstance(proposal, dict) and proposal.get("fact"):
        from services.agent.memory.policy import infer_kind

        kind_hint = infer_kind(str(proposal["fact"]))

    related: list[MemoryRecord] = []
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

    pending_dict: dict[str, Any] | None = None
    proposed_to_user = False
    if decision.remember and decision.proposal and decision.fact:
        pending = new_pending_from_proposal(
            {
                **decision.proposal,
                "action": decision.verdict if decision.verdict in {"add", "change"} else "add",
                "fact": decision.fact,
            },
            originating_message=str(state.get("question") or ""),
            kind=decision.kind,
            replace_id=decision.replace_id,
        )
        pending_store.set(pending)
        pending_dict = pending.as_dict()
        proposed_to_user = True
        log_memory_decision(
            outcome="proposed",
            originating_message=str(state.get("question") or ""),
            proposal=pending_dict,
            intent=None,
            intent_reason="opened_pending_awaiting_user_confirmation",
            detail={"verdict": decision.verdict},
        )

    answer_text = (state.get("answer") or "").casefold()
    proposed_in_answer = (
        "would you like me to remember" in answer_text
        or "would you like me to update what i remember" in answer_text
    )

    return {
        "memory_writes": [],
        "memory_pending_proposal": pending_dict,
        "memory_self_evaluations": evaluations,
        "sources_used": [],
        "route": "done",
        "steps": [
            _step(
                state,
                "write_memory",
                "ok",
                started,
                notes=(
                    f"propose-only verdict={decision.verdict}; "
                    f"wrote=0; pending_open={bool(pending_dict)}"
                ),
                output={
                    "source": "memory",
                    "api": "memory_proposal_to_user",
                    "always_write": False,
                    "wrote_to_memory": False,
                    "proposed_to_user": proposed_to_user or proposed_in_answer,
                    "second_model_call": False,
                    "written_count": 0,
                    "written_ids": [],
                    "self_evaluations": evaluations,
                    "memory_proposal": (
                        proposal.as_dict()
                        if isinstance(proposal, MemoryProposal)
                        else proposal
                    ),
                    "pending_proposal": pending_dict,
                },
            )
        ],
    }


def recalled_records_from_state(state: AgentState) -> list[Any]:
    """Rebuild MemoryRecord-like dicts already loaded by ``recall_memory`` (no re-dump)."""
    return _records_from_hits(state.get("memory_hits") or [], kind=None)[
        :DEFAULT_READ_LIMIT
    ]


def surface_memory_proposal_in_answer(
    answer: str,
    proposal: MemoryProposal | dict[str, Any] | None,
    *,
    existing: list[MemoryRecord] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Policy-gate a proposal and append the user-facing question when allowed.

    Suppresses the question when a pending proposal is already open.
    Returns ``(answer_for_user, proposal_dict)``. Never writes to the store.
    """
    pending_store = get_pending_store()
    abandoned = pending_store.take_expired()
    if abandoned is not None:
        log_memory_decision(
            outcome="discarded_pending_ttl",
            originating_message="",
            proposal=abandoned.as_dict(),
            intent=None,
            intent_reason="pending_ttl_expired_before_surface_proposal",
        )
    if pending_store.has_pending():
        dismissed = MemoryProposal.nothing_to_remember("one_pending_proposal_limit")
        return answer, dismissed.as_dict()

    decision = decide_from_memory_proposal(proposal, existing=existing or [])
    if not decision.remember or not decision.fact:
        dismissed = MemoryProposal.nothing_to_remember(decision.reason)
        return answer, dismissed.as_dict()

    gated = MemoryProposal(
        applicable=True,
        action="change" if decision.verdict == "change" else "add",
        fact=decision.fact,
        previous_fact=(
            proposal.previous_fact
            if isinstance(proposal, MemoryProposal)
            else (proposal or {}).get("previous_fact")
            if isinstance(proposal, dict)
            else None
        ),
        why=decision.reason,
    )
    return attach_proposal_question_to_answer(answer, gated), gated.as_dict()
