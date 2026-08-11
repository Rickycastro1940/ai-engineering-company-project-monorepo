"""Resolve a pending memory proposal via explicit confirmation intent."""

from __future__ import annotations

import time
from typing import Any

from services.agent.memory.audit import log_memory_decision
from services.agent.memory.intent import ConfirmationIntent, classify_confirmation_intent
from services.agent.memory.interface import get_agent_memory
from services.agent.memory.pending import PendingProposal, get_pending_store
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


def _proposal_payload(pending: PendingProposal) -> dict[str, Any]:
    return {
        "id": pending.id,
        "fact": pending.fact,
        "action": pending.action,
        "why": pending.why,
        "previous_fact": pending.previous_fact,
        "kind": pending.kind,
        "originating_message": pending.originating_message,
        "created_at": pending.created_at,
    }


def resolve_memory_confirmation_node(state: AgentState) -> dict[str, Any]:
    """Classify the user message against the single pending proposal (if any).

    - APPROVE / EDIT → durable write, clear pending, audit
    - REJECT / TOPIC_CHANGE / AMBIGUOUS → discard pending (never assume yes), audit
    - Residual question (same message) → continue the graph with that question
    - Confirmation-only → short ack and ``confirmation_done``
    """
    started = time.perf_counter()
    store = get_pending_store()
    pending = store.get()
    message = (state.get("question") or "").strip()

    if pending is None:
        return {
            "memory_confirmation": {
                "had_pending": False,
                "intent": None,
                "outcome": None,
            },
            "steps": [
                _step(
                    state,
                    "resolve_memory_confirmation",
                    "ok",
                    started,
                    notes="no pending proposal",
                    output={"had_pending": False},
                )
            ],
        }

    classification = classify_confirmation_intent(message, pending)
    intent = classification.intent
    proposal_payload = _proposal_payload(pending)
    written: list[dict[str, Any]] = []
    ack: str | None = None
    outcome: str

    memory = get_agent_memory()

    if intent == ConfirmationIntent.APPROVE:
        result = memory.write(
            pending.fact,
            kind=pending.kind,
            source="user_confirmed",
            metadata={
                "pending_id": pending.id,
                "why": pending.why,
                "confirmation_intent": intent.value,
            },
            replace_id=pending.replace_id if pending.action == "change" else None,
        )
        store.clear()
        outcome = "approved"
        ack = f'Saved to memory: "{pending.fact}"'
        if result.ok and result.record is not None:
            written.append(result.record.as_dict())
        log_memory_decision(
            outcome=outcome,
            originating_message=message,
            proposal=proposal_payload,
            intent=intent.value,
            intent_reason=classification.reason,
            residual_question=classification.residual_question,
        )

    elif intent == ConfirmationIntent.EDIT:
        fact = (classification.edited_fact or "").strip()
        result = memory.write(
            fact,
            kind=pending.kind,
            source="user_edited_confirmation",
            metadata={
                "pending_id": pending.id,
                "original_fact": pending.fact,
                "confirmation_intent": intent.value,
            },
            replace_id=pending.replace_id if pending.action == "change" else None,
        )
        store.clear()
        outcome = "edited"
        ack = f'Updated memory proposal and saved: "{fact}"'
        if result.ok and result.record is not None:
            written.append(result.record.as_dict())
        log_memory_decision(
            outcome=outcome,
            originating_message=message,
            proposal=proposal_payload,
            intent=intent.value,
            intent_reason=classification.reason,
            edited_fact=fact,
        )

    elif intent == ConfirmationIntent.REJECT:
        store.clear()
        outcome = "rejected"
        ack = "Okay — I won't remember that."
        log_memory_decision(
            outcome=outcome,
            originating_message=message,
            proposal=proposal_payload,
            intent=intent.value,
            intent_reason=classification.reason,
            residual_question=classification.residual_question,
        )

    elif intent == ConfirmationIntent.TOPIC_CHANGE:
        store.clear()
        outcome = "discarded_topic_change"
        ack = None
        log_memory_decision(
            outcome=outcome,
            originating_message=message,
            proposal=proposal_payload,
            intent=intent.value,
            intent_reason=classification.reason,
            residual_question=classification.residual_question or message,
        )

    else:
        # AMBIGUOUS — default discard; never assume approval.
        store.clear()
        outcome = "discarded_ambiguous"
        ack = None
        log_memory_decision(
            outcome=outcome,
            originating_message=message,
            proposal=proposal_payload,
            intent=intent.value,
            intent_reason=classification.reason,
        )

    residual = classification.residual_question
    confirmation_meta = {
        "had_pending": True,
        "intent": intent.value,
        "intent_reason": classification.reason,
        "outcome": outcome,
        "residual_question": residual,
        "edited_fact": classification.edited_fact,
        "proposal": proposal_payload,
    }

    # Resume normal conversation when there is a residual / topic-change question.
    if residual:
        return {
            "question": residual,
            "answer": None,
            "route": "decide",
            "memory_pending_proposal": None,
            "memory_writes": written,
            "memory_confirmation": confirmation_meta,
            "steps": [
                _step(
                    state,
                    "resolve_memory_confirmation",
                    "ok",
                    started,
                    notes=(
                        f"intent={intent.value} outcome={outcome}; "
                        f"resume with residual question"
                    ),
                    output=confirmation_meta,
                )
            ],
        }

    # Confirmation-only turn (approve/reject/edit without a follow-up question).
    if intent in {
        ConfirmationIntent.APPROVE,
        ConfirmationIntent.REJECT,
        ConfirmationIntent.EDIT,
    }:
        return {
            "answer": ack,
            "route": "confirmation_done",
            "memory_pending_proposal": None,
            "memory_writes": written,
            "memory_confirmation": confirmation_meta,
            "steps": [
                _step(
                    state,
                    "resolve_memory_confirmation",
                    "ok",
                    started,
                    notes=f"intent={intent.value} outcome={outcome}; confirmation_done",
                    output={**confirmation_meta, "ack": ack, "wrote": len(written)},
                )
            ],
        }

    # Ambiguous discard with no residual — continue original message as a normal turn.
    return {
        "route": "decide",
        "memory_pending_proposal": None,
        "memory_writes": written,
        "memory_confirmation": confirmation_meta,
        "steps": [
            _step(
                state,
                "resolve_memory_confirmation",
                "ok",
                started,
                notes=f"intent={intent.value} outcome={outcome}; continue normally",
                output=confirmation_meta,
            )
        ],
    }
