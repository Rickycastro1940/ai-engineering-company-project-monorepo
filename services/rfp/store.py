"""RFP persistence via SQLModel (Postgres/Supabase)."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from data.pipelines.rfp_intake.constants import PART1_STATUSES, STATUS_INTAKE_COMPLETE
from data.pipelines.rfp_intake.routing import route_intake_to_part2, validate_part2_handoff
from services.api.database import create_db_and_tables, get_engine, reset_engine
from services.rfp.models import RfpDepartmentSection, RfpTicket, _now

# Re-export for tests
__all__ = [
    "RfpDepartmentSection",
    "RfpTicket",
    "create_analyzing_ticket",
    "get_ticket",
    "init_db",
    "list_part2_queue",
    "list_tickets",
    "load_part2_handoff",
    "reset_engine",
    "save_intake_result",
    "ticket_to_dict",
]


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
            "approval_status": row.approval_status,
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
        "ask_whom": ask_whom,
        "open_questions": handoff.get("open_questions") or meta.get("open_questions", []),
        "work_streams": handoff.get("work_streams", []),
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }
