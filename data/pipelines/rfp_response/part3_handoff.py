"""Part 3 handoff from Part 2 — last drafts + EvaluationResult, never discarded.

Exhausted sections stay in this payload at ``needs_human_review`` so Part 3
can still review them. Tickets are not discarded when the iteration limit hits.
"""

from __future__ import annotations

from typing import Any

from data.pipelines.rfp_intake.constants import (
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_WAITING_FOR_APPROVAL,
)

HANDOFF_SCHEMA_VERSION = "1.0"


def section_status_for_loop(*, passed: bool, exhausted: bool) -> str:
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
        sections.append(
            {
                "department_id": row.get("department_id"),
                "owner": row.get("owner"),
                "generator_agent": row.get("generator_agent"),
                "draft_content": row.get("draft_content") or "",
                "evaluation_results": ev,
                "feedback_for_generator": feedback,
                "status": row.get("section_status")
                or section_status_for_loop(passed=passed, exhausted=exhausted),
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
            "for every section, including needs_human_review."
        ),
    }
