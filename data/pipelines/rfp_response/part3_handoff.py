"""Part 3 handoff from Part 2 — last drafts + EvaluationResult, never discarded.

Exhausted sections stay in this payload. Ticket status may be
``needs_human_review``, but each section carries ``approval_status=pending``
so Part 3 HITL is not skipped (CONTEXT §2.3).
"""

from __future__ import annotations

from typing import Any

from data.pipelines.rfp_intake.constants import (
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_WAITING_FOR_APPROVAL,
)

HANDOFF_SCHEMA_VERSION = "1.0"


def section_status_for_loop(*, passed: bool, exhausted: bool) -> str:
    """Part 2 loop outcome (not DepartmentSection.approval_status)."""
    if passed and not exhausted:
        return "pending"
    return STATUS_NEEDS_HUMAN_REVIEW


def build_part3_handoff(
    *,
    ticket_id: str,
    ticket_status: str,
    section_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Documented Part 3 contract: every Part 2 section is included."""
    sections: list[dict[str, Any]] = []
    for row in section_results:
        exhausted = bool(row.get("exhausted"))
        passed = bool(row.get("passed"))
        ev = row.get("evaluation_results") or {}
        feedback = list(
            row.get("feedback_for_generator")
            or ev.get("feedback_for_generator")
            or ev.get("feedback")
            or []
        )
        loop_status = row.get("section_status") or section_status_for_loop(
            passed=passed, exhausted=exhausted
        )
        sections.append(
            {
                "department_id": row.get("department_id"),
                "owner": row.get("owner"),
                "generator_agent": row.get("generator_agent"),
                "draft_content": row.get("draft_content") or "",
                "evaluation_results": ev,
                "feedback_for_generator": feedback,
                # Part 2 loop outcome (may be needs_human_review when exhausted).
                "status": loop_status,
                "section_loop_status": loop_status,
                # CONTEXT §2.3 HITL field — always pending at Part 3 entry.
                "approval_status": "pending",
                "iterations": row.get("iterations"),
                "exhausted": exhausted,
                "passed": passed,
                "include_in_part3": True,
            }
        )
    if ticket_status not in {STATUS_WAITING_FOR_APPROVAL, STATUS_NEEDS_HUMAN_REVIEW}:
        ticket_status = (
            STATUS_WAITING_FOR_APPROVAL
            if sections and all(s["passed"] for s in sections)
            else STATUS_NEEDS_HUMAN_REVIEW
        )
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "ticket_id": ticket_id,
        "status": ticket_status,
        "next_part": 3,
        "discarded": False,
        "sections": sections,
        "section_count": len(sections),
        "message": (
            "Part 2 complete. Part 3 reviews last drafts + EvaluationResult "
            "for every section; section approval_status starts pending for "
            "named-owner HITL (ticket may be needs_human_review)."
        ),
    }
