"""RFP persistence via SQLModel (Postgres/Supabase)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import or_
from sqlmodel import Session, select

from data.pipelines.rfp_intake.constants import (
    P1_TERMINAL,
    PART1_STATUSES,
    PART2_PLUS_STATUSES,
    STATUS_DISCARDED,
    STATUS_DONE,
    STATUS_DRAFTING,
    STATUS_FAILED,
    STATUS_INTAKE_COMPLETE,
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_UNDER_EVALUATION,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_intake.routing import route_intake_to_part2, validate_part2_handoff
from services.api.database import create_db_and_tables, get_engine, reset_engine
from services.rfp.models import RfpDepartmentSection, RfpFinalDocument, RfpTicket, _now

# Re-export for tests
__all__ = [
    "RfpDepartmentSection",
    "RfpFinalDocument",
    "RfpTicket",
    "create_analyzing_ticket",
    "get_final_document",
    "get_ticket",
    "init_db",
    "list_part2_queue",
    "list_part3_queue",
    "list_tickets",
    "load_part2_handoff",
    "load_part3_ticket_state",
    "load_ready_part2_handoff",
    "persist_part2_progress",
    "persist_part3_progress",
    "record_approval_decision",
    "reset_engine",
    "save_intake_result",
    "save_response_result",
    "ticket_to_dict",
]

PART2_ALLOWED_STATUSES = frozenset(
    {
        STATUS_DRAFTING,
        STATUS_UNDER_EVALUATION,
        STATUS_NEEDS_HUMAN_REVIEW,
        STATUS_WAITING_FOR_APPROVAL,
    }
)
PART3_ALLOWED_STATUSES = frozenset(
    {
        STATUS_NEEDS_HUMAN_REVIEW,
        STATUS_WAITING_FOR_APPROVAL,
        STATUS_DONE,
    }
)


def init_db() -> None:
    create_db_and_tables()


def create_analyzing_ticket(*, title: str | None = None) -> RfpTicket:
    init_db()
    ticket = RfpTicket(title=title, status="analyzing")
    with Session(get_engine()) as session:
        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        return ticket.model_copy(deep=True)


def get_ticket(ticket_id: str) -> RfpTicket | None:
    init_db()
    with Session(get_engine()) as session:
        row = session.get(RfpTicket, ticket_id)
        return row.model_copy(deep=True) if row else None


def list_tickets(*, limit: int = 50) -> list[RfpTicket]:
    init_db()
    with Session(get_engine()) as session:
        rows = session.exec(
            select(RfpTicket).order_by(RfpTicket.created_at.desc()).limit(limit)
        ).all()
        return [r.model_copy(deep=True) for r in rows]


def list_sections(ticket_id: str) -> list[RfpDepartmentSection]:
    init_db()
    with Session(get_engine()) as session:
        rows = session.exec(
            select(RfpDepartmentSection).where(
                RfpDepartmentSection.ticket_id == ticket_id
            )
        ).all()
        return [r.model_copy(deep=True) for r in rows]


def list_part2_queue(*, limit: int = 50) -> list[dict[str, Any]]:
    """Queue of tickets routed to Part 2 (DB flag + intake_complete)."""
    init_db()
    with Session(get_engine()) as session:
        rows = session.exec(
            select(RfpTicket)
            .where(RfpTicket.part2_ready == True)  # noqa: E712
            .where(RfpTicket.status == STATUS_INTAKE_COMPLETE)
            .order_by(RfpTicket.part2_routed_at.desc())
            .limit(limit)
        ).all()
        out: list[dict[str, Any]] = []
        for row in rows:
            handoff = {}
            if row.part2_handoff_json:
                try:
                    handoff = json.loads(row.part2_handoff_json)
                except json.JSONDecodeError:
                    handoff = {}
            out.append(
                {
                    "ticket_id": row.ticket_id,
                    "status": row.status,
                    "part2_ready": row.part2_ready,
                    "part2_routed_at": row.part2_routed_at,
                    "departments_needed": json.loads(
                        row.departments_needed_json or "[]"
                    ),
                    "work_stream_count": len(handoff.get("work_streams") or []),
                    "requires_ceo_approval": row.requires_ceo_approval,
                }
            )
        return out


def load_part2_handoff(ticket_id: str) -> dict[str, Any]:
    """Load Part 2 contract by ticket_id — no PDF reparse."""
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)
    if not ticket.part2_handoff_json:
        raise ValueError(f"Ticket {ticket_id} has no Part 2 handoff payload")
    try:
        contract = json.loads(ticket.part2_handoff_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Corrupt part2_handoff_json for {ticket_id}") from exc
    validate_part2_handoff(contract)
    if contract.get("ticket_id") != ticket_id:
        raise ValueError("Handoff ticket_id mismatch")
    if contract.get("reparse_pdf_required") is True:
        raise ValueError("Handoff incorrectly requires PDF reparse")
    return contract


def load_ready_part2_handoff(ticket_id: str) -> tuple[dict[str, Any], str, bool]:
    """Load handoff only when Part 1 marked the ticket ready for Part 2.

    Returns ``(handoff, ticket.status, ticket.part2_ready)``.
    Raises ``ValueError`` when status/flag/contract are not Part-1-ready.
    """
    from data.pipelines.rfp_response.handoff_consume import (
        Part1HandoffNotReady,
        assert_part1_routing_ready,
    )

    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)

    handoff: dict[str, Any] | None = None
    if ticket.part2_handoff_json:
        try:
            handoff = json.loads(ticket.part2_handoff_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupt part2_handoff_json for {ticket_id}") from exc

    try:
        contract = assert_part1_routing_ready(
            ticket_id=ticket_id,
            status=ticket.status,
            part2_ready=bool(ticket.part2_ready),
            handoff=handoff,
        )
    except Part1HandoffNotReady as exc:
        raise ValueError(str(exc)) from exc
    return contract, ticket.status, bool(ticket.part2_ready)


def _upsert_section_drafts(
    session: Session,
    ticket_id: str,
    section_results: list[dict[str, Any]],
) -> None:
    """Persist draft_content + evaluation_results on DepartmentSection rows."""
    for section in section_results:
        dept = section.get("department_id")
        if not dept:
            continue
        row = session.exec(
            select(RfpDepartmentSection).where(
                RfpDepartmentSection.ticket_id == ticket_id,
                RfpDepartmentSection.department_id == dept,
            )
        ).first()
        if row is None:
            row = RfpDepartmentSection(ticket_id=ticket_id, department_id=dept)
            session.add(row)
        if "draft_content" in section:
            row.draft_content = section.get("draft_content") or ""
        if section.get("evaluation_results") is not None:
            row.evaluation_results_json = json.dumps(
                section.get("evaluation_results") or {},
                ensure_ascii=False,
            )
        # CONTEXT §2.3: section approval_status is pending|approved|rejected.
        # Exhausted Part 2 drafts still need named-owner HITL → pending (never
        # ticket-level needs_human_review, which would skip Part 3 interrupts).
        if section.get("passed"):
            row.approval_status = row.approval_status or "pending"
        elif section.get("exhausted") or section.get("section_status") == STATUS_NEEDS_HUMAN_REVIEW:
            # Ticket may be needs_human_review; section stays pending for Part 3 HITL.
            if row.approval_status not in {"approved", "rejected", "request_changes"}:
                row.approval_status = "pending"
        row.updated_at = _now()


def persist_part2_progress(
    ticket_id: str,
    *,
    status: str,
    section_results: list[dict[str, Any]] | None = None,
) -> bool:
    """Write Part 2 ticket status (+ optional drafts/evals) to Postgres.

    The Part 1 ticket starts at ``intake_complete`` and is updated in place:
    ``drafting`` → ``under_evaluation`` → ``needs_human_review`` /
    ``waiting_for_approval``. Missing tickets (in-memory pipeline runs) are
    ignored so unit tests without a DB row still work.
    """
    if not (ticket_id or "").strip():
        return False
    if status not in PART2_ALLOWED_STATUSES:
        return False
    init_db()
    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None:
            return False
        if ticket.status not in {
            STATUS_INTAKE_COMPLETE,
            STATUS_DRAFTING,
            STATUS_UNDER_EVALUATION,
            STATUS_NEEDS_HUMAN_REVIEW,
            STATUS_WAITING_FOR_APPROVAL,
        }:
            return False

        try:
            meta = json.loads(ticket.metadata_json or "{}")
        except json.JSONDecodeError:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        history = list(meta.get("part2_status_history") or [])
        if not history:
            history.append(ticket.status)
        if not history or history[-1] != status:
            history.append(status)
        meta["part2_status_history"] = history
        ticket.metadata_json = json.dumps(meta, ensure_ascii=False)
        ticket.status = status
        ticket.updated_at = _now()
        if section_results:
            _upsert_section_drafts(session, ticket_id, section_results)
        if status == STATUS_NEEDS_HUMAN_REVIEW:
            ticket.discard_reason = None
            ticket.discard_rule_id = None
        session.add(ticket)
        session.commit()
        return True


def _section_public(row: RfpDepartmentSection) -> dict[str, Any]:
    def _loads(raw: str | None, default: Any) -> Any:
        try:
            return json.loads(raw or "")
        except json.JSONDecodeError:
            return default

    from data.pipelines.rfp_approval.handoff import normalize_section_approval_status
    from data.pipelines.rfp_intake.constants import DEPARTMENT_OWNERS

    return {
        "department_id": row.department_id,
        "owner": DEPARTMENT_OWNERS.get(row.department_id, row.department_id),
        "key_aspects": _loads(row.key_aspects_json, []),
        "draft_content": row.draft_content or "",
        "evaluation_results": _loads(row.evaluation_results_json, {}),
        "approval_status": normalize_section_approval_status(row.approval_status),
        "approver": row.approver,
        "approved_at": row.approved_at,
    }


def load_part3_ticket_state(ticket_id: str) -> dict[str, Any]:
    """Load Part 2 drafts + current approvals for the Part 3 graph (no PDF)."""
    from data.pipelines.rfp_approval.approvers import requires_ceo_approval
    from data.pipelines.rfp_approval.handoff import (
        assert_part2_ready_for_approval,
        normalize_section_approval_status,
    )

    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise KeyError(ticket_id)
    meta: dict[str, Any]
    try:
        meta = json.loads(ticket.metadata_json or "{}")
    except json.JSONDecodeError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    sections = [_section_public(row) for row in list_sections(ticket_id)]
    try:
        depts = json.loads(ticket.departments_needed_json or "[]")
    except json.JSONDecodeError:
        depts = []
    assert_part2_ready_for_approval(
        ticket_id=ticket_id,
        status=ticket.status,
        sections=sections,
        part3_handoff=meta.get("part3_handoff") or {},
    )
    approvals = {
        row["department_id"]: {
            "department_id": row["department_id"],
            "approval_status": normalize_section_approval_status(
                row.get("approval_status")
            ),
            "approver": row.get("approver"),
            "approved_at": row.get("approved_at"),
        }
        for row in sections
        if row.get("department_id")
    }
    ceo_needed = requires_ceo_approval(
        requires_ceo_flag=bool(ticket.requires_ceo_approval),
        metadata=meta,
    )
    return {
        "ticket_id": ticket_id,
        "status": ticket.status,
        "sections": sections,
        "metadata": meta,
        "departments_needed": list(depts),
        "part3_handoff": meta.get("part3_handoff") or {},
        "requires_ceo_approval": ceo_needed,
        "approvals": approvals,
        "ceo_approval": meta.get("ceo_approval") or {},
        "approval_iterations": {
            str(k): int(v)
            for k, v in dict(meta.get("approval_iterations") or {}).items()
        },
        "reparse_pdf_required": False,
    }


def list_part3_queue(*, limit: int = 50) -> list[dict[str, Any]]:
    """Tickets waiting on department (or CEO) sign-off."""
    init_db()
    with Session(get_engine()) as session:
        rows = session.exec(
            select(RfpTicket)
            .where(
                or_(
                    RfpTicket.status == STATUS_WAITING_FOR_APPROVAL,
                    RfpTicket.status == STATUS_NEEDS_HUMAN_REVIEW,
                )
            )
            .order_by(RfpTicket.updated_at.desc())
            .limit(limit)
        ).all()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                depts = json.loads(row.departments_needed_json or "[]")
            except json.JSONDecodeError:
                depts = []
            out.append(
                {
                    "ticket_id": row.ticket_id,
                    "status": row.status,
                    "part3_ready": bool(row.part3_ready),
                    "departments_needed": depts,
                    "requires_ceo_approval": row.requires_ceo_approval,
                }
            )
        return out


def get_final_document(
    ticket_id: str, *, require_done: bool = False
) -> dict[str, Any] | None:
    """Return the stored FinalDocument, or None if missing.

    When ``require_done`` is True, the document is accessible only if the
    ticket status is ``done`` (completion rule).
    """
    from data.pipelines.rfp_approval.synthesizer import assert_final_document_context_shape

    init_db()
    with Session(get_engine()) as session:
        if require_done:
            ticket = session.get(RfpTicket, ticket_id)
            if ticket is None or ticket.status != STATUS_DONE:
                return None
        row = session.get(RfpFinalDocument, ticket_id)
        if row is None:
            return None
        try:
            payload = json.loads(row.document_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        if not payload:
            payload = {
                "ticket_id": row.ticket_id,
                "sections": json.loads(row.sections_json or "[]"),
                "total_estimated_value": row.total_estimated_value,
                "generated_at": row.generated_at,
                "markdown": row.markdown,
            }
        # Always surface CONTEXT §2.3 fields even if older rows omitted them.
        payload.setdefault("ticket_id", row.ticket_id)
        payload.setdefault(
            "sections", json.loads(row.sections_json or "[]") if row.sections_json else []
        )
        if "total_estimated_value" not in payload:
            payload["total_estimated_value"] = row.total_estimated_value
        payload.setdefault("generated_at", row.generated_at)
        try:
            return assert_final_document_context_shape(payload)
        except ValueError:
            return None


def persist_part3_progress(
    ticket_id: str,
    *,
    status: str | None = None,
    approvals: dict[str, dict[str, Any]] | None = None,
    ceo_approval: dict[str, Any] | None = None,
    arbitration: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    final_document: dict[str, Any] | None = None,
    requires_ceo_approval: bool | None = None,
    synthesizer_blocked: bool | None = None,
    approval_iterations: dict[str, int] | None = None,
) -> bool:
    """Write Part 3 approvals / FinalDocument onto the same Part 1 ticket.

    Status rules (completion):
    - While any department approval is still open, callers pass
      ``waiting_for_approval``.
    - Storing a FinalDocument always sets the ticket to ``done`` so the
      document becomes accessible via ``GET .../final-document``.
    """
    if not (ticket_id or "").strip():
        return False
    # Completing with a FinalDocument forces ``done`` — never leave a
    # stored document on a still-waiting ticket.
    if final_document:
        status = STATUS_DONE
    if status is not None and status not in PART3_ALLOWED_STATUSES:
        return False
    init_db()
    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None:
            return False
        if ticket.status not in {
            STATUS_NEEDS_HUMAN_REVIEW,
            STATUS_WAITING_FOR_APPROVAL,
            STATUS_DONE,
        }:
            return False
        try:
            meta = json.loads(ticket.metadata_json or "{}")
        except json.JSONDecodeError:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        history = list(meta.get("part3_status_history") or [])
        if status and (not history or history[-1] != status):
            history.append(status)
            meta["part3_status_history"] = history
        if ceo_approval is not None:
            meta["ceo_approval"] = ceo_approval
        if arbitration is not None:
            meta["part3_arbitration"] = arbitration
        if synthesizer_blocked is not None:
            meta["synthesizer_blocked"] = synthesizer_blocked
        if approval_iterations is not None:
            meta["approval_iterations"] = {
                str(k): int(v) for k, v in approval_iterations.items()
            }
        if requires_ceo_approval is not None:
            ticket.requires_ceo_approval = bool(requires_ceo_approval)
        if conflicts is not None:
            ticket.conflicts_json = json.dumps(conflicts, ensure_ascii=False)
        if status:
            ticket.status = status
        ticket.part3_ready = True
        ticket.updated_at = _now()
        if approvals:
            for dept, payload in approvals.items():
                row = session.exec(
                    select(RfpDepartmentSection).where(
                        RfpDepartmentSection.ticket_id == ticket_id,
                        RfpDepartmentSection.department_id == dept,
                    )
                ).first()
                if row is None:
                    continue
                row.approval_status = payload.get("approval_status") or row.approval_status
                if payload.get("approver"):
                    row.approver = payload.get("approver")
                row.approved_at = payload.get("approved_at")
                row.updated_at = _now()
                session.add(row)
        if final_document:
            meta["final_document"] = {
                "ticket_id": final_document.get("ticket_id"),
                "total_estimated_value": final_document.get("total_estimated_value"),
                "generated_at": final_document.get("generated_at"),
            }
            existing = session.get(RfpFinalDocument, ticket_id)
            if existing is None:
                existing = RfpFinalDocument(ticket_id=ticket_id)
                session.add(existing)
            existing.sections_json = json.dumps(
                final_document.get("sections") or [], ensure_ascii=False
            )
            existing.total_estimated_value = final_document.get("total_estimated_value")
            existing.generated_at = str(final_document.get("generated_at") or _now())
            existing.markdown = final_document.get("markdown")
            existing.document_json = json.dumps(final_document, ensure_ascii=False)
        ticket.metadata_json = json.dumps(meta, ensure_ascii=False)
        session.add(ticket)
        session.commit()
        return True


def record_approval_decision(
    ticket_id: str,
    *,
    department_id: str,
    decision: str,
    approver: str,
    comment: str | None = None,
) -> dict[str, Any]:
    """Persist one named-owner (or CEO) decision, then continue the Part 3 graph."""
    from data.pipelines.rfp_approval import run_approval_for_ticket
    from data.pipelines.rfp_approval.approvers import (
        UnknownApproverError,
        validate_human_resume,
    )

    try:
        resume = validate_human_resume(
            {
                "department_id": department_id,
                "decision": decision,
                "approver": approver,
                "comment": comment,
            }
        )
    except UnknownApproverError:
        raise
    result = run_approval_for_ticket(ticket_id, resume=resume)
    if result.error_message:
        raise ValueError(result.error_message)
    saved = get_ticket(ticket_id)
    payload = ticket_to_dict(saved) if saved else {}
    payload["part3_pipeline"] = result.to_dict()
    return payload


def save_response_result(ticket_id: str, result: Any) -> RfpTicket:
    """Persist Part 2 drafts + evaluation_results; advance ticket status."""
    init_db()
    status = getattr(result, "status", None) or (
        result.get("status") if isinstance(result, dict) else None
    )
    section_results = getattr(result, "section_results", None)
    if section_results is None and isinstance(result, dict):
        section_results = result.get("section_results")
    section_results = list(section_results or [])
    trace = getattr(result, "trace", None)
    if trace is None and isinstance(result, dict):
        trace = result.get("trace")
    trace = list(trace or [])
    avg = getattr(result, "average_iterations", None)
    if avg is None and isinstance(result, dict):
        avg = result.get("average_iterations")
    all_passed = getattr(result, "all_passed", None)
    if all_passed is None and isinstance(result, dict):
        all_passed = result.get("all_passed")

    if status not in PART2_ALLOWED_STATUSES:
        raise ValueError(
            f"Refusing to persist non-Part-2 ticket status {status!r} "
            f"for {ticket_id} (expected one of {sorted(PART2_ALLOWED_STATUSES)})"
        )

    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None:
            raise KeyError(ticket_id)
        if ticket.status not in {
            STATUS_INTAKE_COMPLETE,
            STATUS_DRAFTING,
            STATUS_UNDER_EVALUATION,
            STATUS_NEEDS_HUMAN_REVIEW,
            STATUS_WAITING_FOR_APPROVAL,
        }:
            raise ValueError(
                f"Ticket {ticket_id} status {ticket.status!r} cannot enter Part 2 response"
            )

        try:
            meta = json.loads(ticket.metadata_json or "{}")
        except json.JSONDecodeError:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        meta["part2_response"] = {
            "average_iterations": avg,
            "all_passed": bool(all_passed),
            "section_count": len(section_results),
            "discarded": False,
        }
        history = list(meta.get("part2_status_history") or [])
        if not history:
            history.append(ticket.status)
        if not history or history[-1] != status:
            history.append(status)
        meta["part2_status_history"] = history
        ticket.status = status
        ticket.updated_at = _now()

        try:
            existing_trace = json.loads(ticket.trace_json or "[]")
        except json.JSONDecodeError:
            existing_trace = []
        if not isinstance(existing_trace, list):
            existing_trace = []
        existing_trace.extend(trace)
        ticket.trace_json = json.dumps(existing_trace, ensure_ascii=False)

        _upsert_section_drafts(session, ticket_id, section_results)

        meta["part3_handoff"] = getattr(result, "part3_handoff", None) or (
            result.get("part3_handoff") if isinstance(result, dict) else None
        ) or {}
        ticket.metadata_json = json.dumps(meta, ensure_ascii=False)
        ticket.part3_ready = True
        # Exhausted tickets stay in the flow for Part 3 — never discarded
        if status == STATUS_NEEDS_HUMAN_REVIEW:
            ticket.discard_reason = None
            ticket.discard_rule_id = None

        session.add(ticket)
        session.commit()
        session.refresh(ticket)
        return ticket.model_copy(deep=True)


def save_intake_result(ticket_id: str, result: Any, *, source_pdf_path: str) -> RfpTicket:
    """Persist Ticket + RFP metadata + DepartmentSection.key_aspects + Part 2 route."""
    init_db()
    with Session(get_engine()) as session:
        ticket = session.get(RfpTicket, ticket_id)
        if ticket is None:
            raise KeyError(ticket_id)

        ticket.status = result.status
        ticket.source_pdf_path = source_pdf_path
        ticket.markdown_text = result.markdown_text
        ticket.markdown_length = len(result.markdown_text or "")
        ticket.metadata_json = json.dumps(result.metadata, ensure_ascii=False)
        ticket.departments_needed_json = json.dumps(result.departments_needed)
        ticket.unmapped_topics_json = json.dumps(result.unmapped_topics)
        ticket.conflicts_json = json.dumps(result.conflicts)
        ticket.intake_summary = result.intake_summary
        ticket.requires_ceo_approval = bool(result.requires_ceo_approval)
        ticket.discard_reason = result.discard_reason
        ticket.discard_rule_id = result.discard_rule_id
        ticket.error_message = result.error_message
        ticket.readability_json = json.dumps(result.readability_scores)
        ticket.trace_json = json.dumps(result.trace, ensure_ascii=False)
        ticket.updated_at = _now()

        # Part 1 statuses only — never persist waiting_for_approval / drafting / etc.
        if ticket.status not in PART1_STATUSES:
            raise ValueError(
                f"Refusing to persist non-Part-1 ticket status {ticket.status!r} "
                f"for {ticket_id} (expected one of {sorted(PART1_STATUSES)})"
            )

        # Discarded tickets must surface why — never persist a silent reject.
        if ticket.status == "discarded" and not (ticket.discard_reason or "").strip():
            raise ValueError(
                f"Refusing to persist discarded ticket {ticket_id} without discard_reason"
            )

        # Route to Part 2 when intake succeeded (flag + DB handoff contract).
        handoff = route_intake_to_part2(
            ticket_id=ticket_id,
            intake_result=result,
            source_pdf_path=source_pdf_path,
        )
        if handoff is not None:
            ticket.part2_ready = True
            ticket.part2_routed_at = handoff.get("routed_at")
            ticket.part2_handoff_json = json.dumps(handoff, ensure_ascii=False)
            # Keep metadata mirror for UI / older readers
            meta = dict(result.metadata or {})
            meta["part2_handoff"] = handoff
            meta["ask_whom"] = handoff.get("ask_whom", [])
            meta["open_questions"] = handoff.get("open_questions", [])
            ticket.metadata_json = json.dumps(meta, ensure_ascii=False)
        else:
            ticket.part2_ready = False
            ticket.part2_routed_at = None
            ticket.part2_handoff_json = None

        session.add(ticket)

        # Replace department sections (Part 1: key_aspects only)
        existing = session.exec(
            select(RfpDepartmentSection).where(
                RfpDepartmentSection.ticket_id == ticket_id
            )
        ).all()
        for row in existing:
            session.delete(row)

        for department_id, aspects in (result.sections or {}).items():
            session.add(
                RfpDepartmentSection(
                    ticket_id=ticket_id,
                    department_id=department_id,
                    key_aspects_json=json.dumps(list(aspects or []), ensure_ascii=False),
                )
            )

        session.commit()
        session.refresh(ticket)
        return ticket.model_copy(deep=True)


def ticket_to_dict(ticket: RfpTicket) -> dict[str, Any]:
    def _loads(raw: str | None, default: Any) -> Any:
        try:
            return json.loads(raw or "")
        except json.JSONDecodeError:
            return default

    from data.pipelines.rfp_approval.handoff import normalize_section_approval_status
    from data.pipelines.rfp_intake.constants import DEPARTMENT_OWNERS
    from data.pipelines.rfp_intake.orchestration import build_final_department_results

    sections_rows = list_sections(ticket.ticket_id)
    sections = {
        row.department_id: _loads(row.key_aspects_json, []) for row in sections_rows
    }
    department_sections = [
        {
            "department_id": row.department_id,
            "contact": DEPARTMENT_OWNERS.get(row.department_id, row.department_id),
            "owner": DEPARTMENT_OWNERS.get(row.department_id, row.department_id),
            "key_aspects": _loads(row.key_aspects_json, []),
            "draft_content": row.draft_content,
            "evaluation_results": _loads(row.evaluation_results_json, {}),
            "approval_status": normalize_section_approval_status(row.approval_status),
            "approver": row.approver,
            "approved_at": row.approved_at,
        }
        for row in sections_rows
    ]
    meta = _loads(ticket.metadata_json, {}) or {}
    handoff = _loads(ticket.part2_handoff_json, {}) or meta.get("part2_handoff", {})
    ask_whom = handoff.get("ask_whom") or meta.get("ask_whom", [])
    final_results = meta.get("final_department_results") or build_final_department_results(
        sections=sections,
        ask_whom=ask_whom,
        departments_needed=_loads(ticket.departments_needed_json, []),
        requires_ceo_approval=bool(ticket.requires_ceo_approval),
    )

    return {
        "ticket_id": ticket.ticket_id,
        "status": ticket.status,
        "title": ticket.title,
        "source_pdf_path": ticket.source_pdf_path,
        "markdown_length": ticket.markdown_length,
        "metadata": meta,
        "departments_needed": _loads(ticket.departments_needed_json, []),
        "sections": sections,
        "department_sections": department_sections,
        "final_department_results": final_results,
        "unmapped_topics": _loads(ticket.unmapped_topics_json, []),
        "conflicts": _loads(ticket.conflicts_json, []),
        "intake_summary": ticket.intake_summary,
        "requires_ceo_approval": ticket.requires_ceo_approval,
        "discard_reason": ticket.discard_reason,
        "discard_rule_id": ticket.discard_rule_id,
        "error_message": ticket.error_message,
        "readability_scores": _loads(ticket.readability_json, {}),
        "trace": _loads(ticket.trace_json, []),
        "part2_ready": bool(ticket.part2_ready),
        "part2_routed_at": ticket.part2_routed_at,
        "part2_handoff": handoff,
        "part2_response": meta.get("part2_response"),
        "part2_status_history": meta.get("part2_status_history") or [],
        "part3_handoff": meta.get("part3_handoff") or {},
        "part3_ready": bool(ticket.part3_ready),
        "part3_status_history": meta.get("part3_status_history") or [],
        "part3_arbitration": meta.get("part3_arbitration") or [],
        "ceo_approval": meta.get("ceo_approval") or {},
        # FinalDocument is accessible on the ticket only after status is done.
        "final_document": (
            get_final_document(ticket.ticket_id, require_done=True) or {}
            if ticket.status == STATUS_DONE
            else {}
        ),
        "synthesizer_blocked": bool(meta.get("synthesizer_blocked")),
        "ask_whom": ask_whom,
        "open_questions": handoff.get("open_questions") or meta.get("open_questions", []),
        "work_streams": handoff.get("work_streams", []),
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        # Same flags on every ticket payload (GET / POST) — avoid UI/API jumps.
        "part1_terminal": ticket.status in P1_TERMINAL,
        "terminal": ticket.status in P1_TERMINAL,
        "pipeline_complete": ticket.status
        in {STATUS_DONE, STATUS_DISCARDED, STATUS_FAILED},
    }
