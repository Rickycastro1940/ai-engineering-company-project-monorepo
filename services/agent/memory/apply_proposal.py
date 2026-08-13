"""Apply the model's ``memory_proposal`` from the same generate call.

Self-evaluation is the structured ``memory_proposal`` field — not a second
LLM call and not a Jaccard heuristic. CONTEXT-company.md policy remains a
hard gate before any write.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from services.agent.memory.policy import evaluate_memory_candidate
from services.agent.memory.proposal import MemoryProposal
from services.agent.memory.self_evaluate import (
    normalize_memory_text,
    self_evaluate_worth_remembering,
)
from services.agent.memory.store import MemoryRecord

ProposalVerdict = Literal[
    "add",
    "change",
    "skip_not_applicable",
    "skip_policy",
    "skip_duplicate",
    "skip_no_proposal",
]


@dataclass(frozen=True, slots=True)
class ProposalDecision:
    remember: bool
    verdict: ProposalVerdict
    reason: str
    fact: str | None = None
    kind: str | None = None
    replace_id: str | None = None
    proposal: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "remember": self.remember,
            "verdict": self.verdict,
            "reason": self.reason,
            "fact": self.fact,
            "kind": self.kind,
            "replace_id": self.replace_id,
            "proposal": self.proposal,
        }


def decide_from_memory_proposal(
    proposal: MemoryProposal | dict[str, Any] | None,
    *,
    existing: list[MemoryRecord],
) -> ProposalDecision:
    """Turn a structured proposal into a propose/skip decision (policy-gated).

``remember=True`` means the fact is worth **proposing to the user** — not that
this step may call ``MemoryInterface.write``.
"""
    if proposal is None:
        return ProposalDecision(
            remember=False,
            verdict="skip_no_proposal",
            reason="no_memory_proposal_on_state",
        )
    if isinstance(proposal, dict):
        try:
            proposal = MemoryProposal.model_validate(proposal)
        except Exception as exc:  # noqa: BLE001
            return ProposalDecision(
                remember=False,
                verdict="skip_no_proposal",
                reason=f"invalid_proposal:{type(exc).__name__}",
            )

    if not proposal.applicable or proposal.action is None or not (proposal.fact or "").strip():
        return ProposalDecision(
            remember=False,
            verdict="skip_not_applicable",
            reason=proposal.why or "model_set_applicable_false",
            proposal=proposal.as_dict(),
        )

    fact = proposal.fact.strip()
    policy = evaluate_memory_candidate(fact, source="memory_proposal")
    if not policy.allowed or not policy.kind:
        return ProposalDecision(
            remember=False,
            verdict="skip_policy",
            reason=policy.reason,
            fact=fact,
            proposal=proposal.as_dict(),
        )

    # Safety: never re-write an exact duplicate even if the model proposed add.
    for rec in existing:
        if rec.kind == policy.kind and normalize_memory_text(rec.text) == normalize_memory_text(
            fact
        ):
            return ProposalDecision(
                remember=False,
                verdict="skip_duplicate",
                reason="exact_fact_already_stored",
                fact=fact,
                kind=policy.kind,
                replace_id=rec.id,
                proposal=proposal.as_dict(),
            )

    replace_id: str | None = None
    if proposal.action == "change":
        # Prefer matching previous_fact text from the model.
        prev = (proposal.previous_fact or "").strip()
        if prev:
            prev_norm = normalize_memory_text(prev)
            for rec in existing:
                if normalize_memory_text(rec.text) == prev_norm:
                    replace_id = rec.id
                    break
        if replace_id is None:
            # Fall back to heuristic related-fact pick for same kind.
            related = self_evaluate_worth_remembering(
                fact, kind=policy.kind, existing=existing
            )
            if related.related_id:
                replace_id = related.related_id

    return ProposalDecision(
        remember=True,
        verdict="add" if proposal.action == "add" else "change",
        reason=proposal.why or f"model_proposal_{proposal.action}",
        fact=fact,
        kind=policy.kind,
        replace_id=replace_id,
        proposal=proposal.as_dict(),
    )
