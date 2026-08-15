"""Consume Part 2 → Part 3 handoff (same ticket; never re-parse the PDF)."""

from __future__ import annotations

from typing import Any

from data.pipelines.rfp_intake.constants import (
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_WAITING_FOR_APPROVAL,
)

PART3_ENTRY_STATUSES = frozenset(
    {STATUS_WAITING_FOR_APPROVAL, STATUS_NEEDS_HUMAN_REVIEW}
)

# CONTEXT §2.3 DepartmentSection.approval_status (+ HITL request_changes).
# Ticket-level ``needs_human_review`` must never leak onto this field.
SECTION_APPROVAL_STATUSES = frozenset(
    {"pending", "approved", "rejected", "request_changes"}
)


class Part2HandoffNotReady(ValueError):
    """Ticket is not ready for Part 3 approval."""


def normalize_section_approval_status(status: str | None) -> str:
    """Map Part 2 exhaustion / unknown values onto CONTEXT section statuses.

    Exhausted drafts hand off for named-owner review as ``pending`` — never as
    the ticket status ``needs_human_review``, which would skip HITL and strand
    the ticket between Part 2 and Part 3.
    """
    raw = str(status or "pending").strip() or "pending"
    if raw in SECTION_APPROVAL_STATUSES:
        return raw
    return "pending"


def assert_part2_ready_for_approval(
    *,
    ticket_id: str,
    status: str,
    sections: list[dict[str, Any]] | None = None,
    part3_handoff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not (ticket_id or "").strip():
        raise Part2HandoffNotReady("ticket_id is required")
    if status not in PART3_ENTRY_STATUSES:
        raise Part2HandoffNotReady(
            f"Ticket {ticket_id} status {status!r} is not ready for Part 3 "
            f"(expected {sorted(PART3_ENTRY_STATUSES)})"
        )
    payload_sections = list(sections or [])
    if part3_handoff and not payload_sections:
        payload_sections = list(part3_handoff.get("sections") or [])
    if not payload_sections:
        raise Part2HandoffNotReady(
            f"Ticket {ticket_id} has no Part 2 sections to approve"
        )
    # Normalize section approval_status so Part 2 ticket statuses never block HITL.
    normalized: list[dict[str, Any]] = []
    for row in payload_sections:
        item = dict(row)
        if "approval_status" in item or item.get("status") == STATUS_NEEDS_HUMAN_REVIEW:
            item["approval_status"] = normalize_section_approval_status(
                item.get("approval_status")
            )
        normalized.append(item)
    return {
        "ticket_id": ticket_id,
        "status": STATUS_WAITING_FOR_APPROVAL,
        "entry_status": status,
        "sections": normalized,
        "part3_handoff": dict(part3_handoff or {}),
        "reparse_pdf_required": False,
    }
