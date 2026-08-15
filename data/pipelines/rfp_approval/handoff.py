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


class Part2HandoffNotReady(ValueError):
    """Ticket is not ready for Part 3 approval."""


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
    return {
        "ticket_id": ticket_id,
        "status": STATUS_WAITING_FOR_APPROVAL,
        "entry_status": status,
        "sections": payload_sections,
        "part3_handoff": dict(part3_handoff or {}),
        "reparse_pdf_required": False,
    }
