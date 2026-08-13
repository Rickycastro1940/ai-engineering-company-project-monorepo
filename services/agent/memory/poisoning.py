"""Guards against memory poisoning via fake “corrections” or free-form writes.

Durable facts may only enter memory when:
1. The agent opened a pending proposal from a grounded turn, and
2. The user explicitly approves that proposed text, or
3. The user edits it in a way that still passes CONTEXT policy **and** stays
   related to the agent-proposed fact (not an unrelated substitution).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from services.agent.memory.pending import PendingProposal
from services.agent.memory.policy import evaluate_memory_candidate
from services.agent.memory.self_evaluate import token_jaccard

# Edited text must remain recognizably about the same proposed fact.
EDIT_MIN_JACCARD: Final[float] = 0.45


@dataclass(frozen=True, slots=True)
class PoisoningCheck:
    allowed: bool
    reason: str


def check_approve_write(pending: PendingProposal) -> PoisoningCheck:
    """Approve only persists the agent-proposed fact (re-checked against policy)."""
    decision = evaluate_memory_candidate(
        pending.fact, kind=pending.kind, source="user_confirmed"
    )
    if not decision.allowed:
        return PoisoningCheck(False, f"approve_blocked_by_policy:{decision.reason}")
    if pending.metadata.get("opened_by") not in {None, "agent_grounded_proposal"}:
        # None allowed for older pending files; new ones set opened_by.
        return PoisoningCheck(False, "approve_blocked_unknown_pending_origin")
    return PoisoningCheck(True, "ok")


def check_edit_write(pending: PendingProposal, edited_fact: str) -> PoisoningCheck:
    """Reject edits that invent unrelated or CONTEXT-forbidden content."""
    cleaned = (edited_fact or "").strip()
    if not cleaned:
        return PoisoningCheck(False, "edit_empty")

    decision = evaluate_memory_candidate(
        cleaned, kind=pending.kind, source="user_edited_confirmation"
    )
    if not decision.allowed:
        return PoisoningCheck(False, f"edit_blocked_by_policy:{decision.reason}")

    overlap = token_jaccard(pending.fact, cleaned)
    if overlap < EDIT_MIN_JACCARD:
        return PoisoningCheck(
            False,
            f"edit_blocked_unrelated_substitution jaccard={overlap:.2f}<{EDIT_MIN_JACCARD}",
        )

    # Block absolute allergen safety / currency conversion even if somehow missed.
    lowered = cleaned.casefold()
    if "zero risk" in lowered or "100% safe" in lowered:
        return PoisoningCheck(False, "edit_blocked_forbidden_allergen_claim")
    if "convert" in lowered and ("usd" in lowered or "cop" in lowered):
        return PoisoningCheck(False, "edit_blocked_currency_conversion")

    return PoisoningCheck(True, "ok")
