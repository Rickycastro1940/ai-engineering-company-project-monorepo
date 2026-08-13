"""Part 2 routing — handoff contract after intake synthesizer.

Routes accepted tickets toward the rest of the agentic flow **without** a
second HTTP API process. Persistence uses DB fields on ``rfp_tickets``
(``part2_ready`` flag + ``part2_handoff_json``) and an optional in-process
queue listing.

Contract guarantee: Part 2 starts from ``ticket_id`` + synthesizer payload
(``work_streams`` with ``key_aspects``). Re-parsing the PDF is not required.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_LABELS,
    DEPARTMENT_OWNERS,
    HANDOFF_SCHEMA_VERSION,
    STATUS_INTAKE_COMPLETE,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_work_streams(
    *,
    sections: dict[str, list[str]],
    ask_whom: list[dict[str, str]] | None = None,
    open_questions: list[str] | None = None,
    owners: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Synthesizer payload structure Part 2 generators consume."""
    ask_by_dept = {
        (a.get("department_id") or ""): a for a in (ask_whom or []) if a.get("department_id")
    }
    open_qs = list(open_questions or [])
    streams: list[dict[str, Any]] = []
    for department_id, key_aspects in (sections or {}).items():
        owner = (owners or {}).get(department_id) or DEPARTMENT_OWNERS.get(
            department_id, department_id
        )
        ask = ask_by_dept.get(department_id) or {}
        streams.append(
            {
                "department_id": department_id,
                "owner": owner,
                "label": DEPARTMENT_LABELS.get(department_id, department_id),
                "key_aspects": list(key_aspects or []),
                "open_questions": [
                    q for q in open_qs if owner in q or department_id in q.casefold()
                ]
                or ([ask["ask"]] if ask.get("ask") else []),
                "next_action": "draft_section",
                "draft_content": None,
                "evaluation_results": None,
            }
        )
    return streams


def build_part2_handoff(
    *,
    ticket_id: str,
    status: str,
    metadata: dict[str, Any] | None,
    departments_needed: list[str],
    sections: dict[str, list[str]],
    intake_summary: str | None,
    ask_whom: list[dict[str, str]] | None,
    open_questions: list[str] | None,
    requires_ceo_approval: bool,
    source_pdf_path: str | None = None,
    markdown_chars: int = 0,
    synthesizer_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the documented handoff contract (ticket_id + synthesizer payload)."""
    synth = dict(synthesizer_payload or {})
    owners = synth.get("owners") or {
        d: DEPARTMENT_OWNERS.get(d, d) for d in departments_needed
    }
    work_streams = build_work_streams(
        sections=sections,
        ask_whom=ask_whom or synth.get("ask_whom"),
        open_questions=open_questions or synth.get("open_questions"),
        owners=owners,
    )
    routed_at = _now()
    contract = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "ticket_id": ticket_id,
        "status": status,
        "part2_ready": status == STATUS_INTAKE_COMPLETE,
        "routed_at": routed_at,
        "next_part": 2 if status == STATUS_INTAKE_COMPLETE else None,
        "reparse_pdf_required": False,
        "message": (
            "Part 1 intake complete. Part 2 may draft from work_streams.key_aspects "
            "without re-parsing the PDF."
            if status == STATUS_INTAKE_COMPLETE
            else "Ticket not ready for Part 2."
        ),
        "metadata": dict(metadata or {}),
        "departments_needed": list(departments_needed or []),
        "intake_summary": intake_summary or "",
        "ask_whom": list(ask_whom or synth.get("ask_whom") or []),
        "open_questions": list(open_questions or synth.get("open_questions") or []),
        "requires_ceo_approval": bool(requires_ceo_approval),
        "ceo_approver": synth.get("ceo_approver"),
        "work_streams": work_streams,
        "source_pdf_path": source_pdf_path,
        "markdown_available_in_db": markdown_chars > 0,
        "synthesizer": {
            "departments_for_drafting": list(departments_needed or []),
            "owners": owners,
            "ask_whom": list(ask_whom or synth.get("ask_whom") or []),
            "open_questions": list(open_questions or synth.get("open_questions") or []),
            "requires_ceo_approval": bool(requires_ceo_approval),
        },
    }
    validate_part2_handoff(contract)
    return contract


def validate_part2_handoff(contract: dict[str, Any]) -> None:
    """Refuse incomplete handoffs — Part 2 must not start blind."""
    if not (contract.get("ticket_id") or "").strip():
        raise ValueError("Part 2 handoff missing ticket_id")
    if contract.get("part2_ready") and contract.get("status") != STATUS_INTAKE_COMPLETE:
        raise ValueError("part2_ready requires status=intake_complete")
    if contract.get("reparse_pdf_required") is True:
        raise ValueError("Handoff must not require PDF reparse")
    streams = contract.get("work_streams") or []
    if contract.get("part2_ready") and not streams:
        raise ValueError("Part 2 handoff missing work_streams / key_aspects payload")
    for stream in streams:
        if not stream.get("department_id"):
            raise ValueError("work_stream missing department_id")
        if not isinstance(stream.get("key_aspects"), list) or not stream["key_aspects"]:
            raise ValueError(
                f"work_stream {stream.get('department_id')} missing key_aspects"
            )


def route_intake_to_part2(
    *,
    ticket_id: str,
    intake_result: Any,
    source_pdf_path: str = "",
) -> dict[str, Any] | None:
    """If intake succeeded, build routing handoff; discarded tickets are not routed."""
    if getattr(intake_result, "status", None) != STATUS_INTAKE_COMPLETE:
        logger.info(
            "routing skip ticket_id=%s status=%s (not intake_complete)",
            ticket_id,
            getattr(intake_result, "status", None),
        )
        return None

    synth = getattr(intake_result, "part2_handoff", None) or {}
    contract = build_part2_handoff(
        ticket_id=ticket_id,
        status=intake_result.status,
        metadata=getattr(intake_result, "metadata", None) or {},
        departments_needed=list(getattr(intake_result, "departments_needed", None) or []),
        sections=dict(getattr(intake_result, "sections", None) or {}),
        intake_summary=getattr(intake_result, "intake_summary", None),
        ask_whom=list(getattr(intake_result, "ask_whom", None) or []),
        open_questions=list(getattr(intake_result, "open_questions", None) or []),
        requires_ceo_approval=bool(
            getattr(intake_result, "requires_ceo_approval", False)
        ),
        source_pdf_path=source_pdf_path or None,
        markdown_chars=len(getattr(intake_result, "markdown_text", "") or ""),
        synthesizer_payload=synth,
    )
    logger.info(
        "routed ticket_id=%s to Part 2 with %d work_streams (reparse_pdf_required=False)",
        ticket_id,
        len(contract["work_streams"]),
    )
    return contract
