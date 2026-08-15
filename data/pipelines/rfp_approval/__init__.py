"""RFP approval + completion pipeline (Milestone 9 Part 3).

Builds on Part 2 drafts/evals. Human-in-the-loop: each active department's
named owner (CONTEXT §2.1) signs off independently. Mariana Restrepo (CEO)
is the only extra approver, and only when estimated value exceeds $50,000
USD/year. Conflict arbitration is a dedicated graph node with fixed trigger
ids — not LLM consensus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data.pipelines.rfp_intake.constants import STATUS_WAITING_FOR_APPROVAL
from data.pipelines.rfp_approval.approvers import (
    CEO_NAME,
    UnknownApproverError,
    requires_ceo_approval,
    signoffs_for_ticket,
)
from data.pipelines.rfp_approval.arbitration import apply_fixed_arbitration
from data.pipelines.rfp_approval.checkpointer import (
    checkpoint_backend,
    get_approval_checkpointer,
    reset_approval_checkpointer,
)
from data.pipelines.rfp_approval.conflicts import conflict_surface_agent
from data.pipelines.rfp_approval.graph import (
    REQUIRED_APPROVAL_NODES,
    build_rfp_approval_graph,
    get_compiled_rfp_approval_graph,
    invoke_rfp_approval_graph,
)
from data.pipelines.rfp_approval.handoff import (
    Part2HandoffNotReady,
    assert_part2_ready_for_approval,
)
from data.pipelines.rfp_approval.synthesizer import build_final_document

__all__ = [
    "CEO_NAME",
    "Part2HandoffNotReady",
    "REQUIRED_APPROVAL_NODES",
    "UnknownApproverError",
    "ApprovalPipelineResult",
    "apply_fixed_arbitration",
    "assert_part2_ready_for_approval",
    "build_final_document",
    "build_rfp_approval_graph",
    "checkpoint_backend",
    "conflict_surface_agent",
    "get_approval_checkpointer",
    "get_compiled_rfp_approval_graph",
    "reset_approval_checkpointer",
    "invoke_rfp_approval_graph",
    "requires_ceo_approval",
    "run_approval_for_ticket",
    "run_approval_pipeline",
    "signoffs_for_ticket",
]


@dataclass
class ApprovalPipelineResult:
    ticket_id: str
    status: str
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    approvals: dict[str, dict[str, Any]] = field(default_factory=dict)
    ceo_approval: dict[str, Any] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    arbitration: list[dict[str, Any]] = field(default_factory=list)
    final_document: dict[str, Any] = field(default_factory=dict)
    synthesizer_blocked: bool = False
    block_reason: str = ""
    error_message: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)
    paused: bool = False
    requires_ceo_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "status": self.status,
            "pending_approvals": list(self.pending_approvals),
            "approvals": dict(self.approvals),
            "ceo_approval": dict(self.ceo_approval),
            "conflicts": list(self.conflicts),
            "arbitration": list(self.arbitration),
            "final_document": dict(self.final_document),
            "synthesizer_blocked": self.synthesizer_blocked,
            "block_reason": self.block_reason,
            "error_message": self.error_message,
            "trace": list(self.trace),
            "paused": self.paused,
            "requires_ceo_approval": self.requires_ceo_approval,
        }


def _result_from_state(final: dict[str, Any], ticket_id: str) -> ApprovalPipelineResult:
    return ApprovalPipelineResult(
        ticket_id=str(final.get("ticket_id") or ticket_id),
        status=str(final.get("status") or STATUS_WAITING_FOR_APPROVAL),
        pending_approvals=list(final.get("pending_approvals") or []),
        approvals=dict(final.get("approvals") or {}),
        ceo_approval=dict(final.get("ceo_approval") or {}),
        conflicts=list(final.get("conflicts") or []),
        arbitration=list(final.get("arbitration") or []),
        final_document=dict(final.get("final_document") or {}),
        synthesizer_blocked=bool(final.get("synthesizer_blocked")),
        block_reason=str(final.get("block_reason") or ""),
        error_message=final.get("error_message"),
        trace=list(final.get("trace") or []),
        paused=bool(final.get("paused")),
        requires_ceo_approval=bool(final.get("requires_ceo_approval")),
    )


def run_approval_pipeline(
    *,
    ticket_id: str,
    status: str = STATUS_WAITING_FOR_APPROVAL,
    sections: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    departments_needed: list[str] | None = None,
    part3_handoff: dict[str, Any] | None = None,
    requires_ceo_approval: bool = False,
    approvals: dict[str, dict[str, Any]] | None = None,
    ceo_approval: dict[str, Any] | None = None,
    queued_decisions: list[dict[str, Any]] | None = None,
    use_interrupt: bool = False,
    thread_id: str | None = None,
    resume: Any | None = None,
) -> ApprovalPipelineResult:
    final = invoke_rfp_approval_graph(
        ticket_id=ticket_id,
        status=status,
        sections=sections,
        metadata=metadata,
        departments_needed=departments_needed,
        part3_handoff=part3_handoff,
        requires_ceo_approval=requires_ceo_approval,
        approvals=approvals,
        ceo_approval=ceo_approval,
        queued_decisions=queued_decisions,
        use_interrupt=use_interrupt,
        thread_id=thread_id,
        resume=resume,
    )
    return _result_from_state(final, ticket_id)


def run_approval_for_ticket(
    ticket_id: str,
    *,
    queued_decisions: list[dict[str, Any]] | None = None,
) -> ApprovalPipelineResult:
    """Canonical Part 3 entry: load Part 2 drafts from the same ticket row."""
    from services.rfp.store import load_part3_ticket_state

    payload = load_part3_ticket_state(ticket_id)
    return run_approval_pipeline(
        ticket_id=ticket_id,
        status=payload["status"],
        sections=payload["sections"],
        metadata=payload["metadata"],
        departments_needed=payload["departments_needed"],
        part3_handoff=payload.get("part3_handoff"),
        requires_ceo_approval=payload["requires_ceo_approval"],
        approvals=payload.get("approvals"),
        ceo_approval=payload.get("ceo_approval"),
        queued_decisions=queued_decisions,
    )
