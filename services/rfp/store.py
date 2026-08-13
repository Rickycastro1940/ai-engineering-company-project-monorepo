"""RFP persistence via SQLModel (Postgres/Supabase)."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from services.api.database import create_db_and_tables, get_engine, reset_engine
from services.rfp.models import RfpDepartmentSection, RfpTicket, _now

# Re-export for tests
__all__ = [
    "RfpDepartmentSection",
    "RfpTicket",
    "create_analyzing_ticket",
    "get_ticket",
    "init_db",
    "list_tickets",
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


def save_intake_result(ticket_id: str, result: Any, *, source_pdf_path: str) -> RfpTicket:
    """Persist Ticket + RFP metadata + DepartmentSection.key_aspects rows."""
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

    sections_rows = list_sections(ticket.ticket_id)
    sections = {
        row.department_id: _loads(row.key_aspects_json, []) for row in sections_rows
    }
    department_sections = [
        {
            "department_id": row.department_id,
            "key_aspects": _loads(row.key_aspects_json, []),
            "approval_status": row.approval_status,
        }
        for row in sections_rows
    ]

    return {
        "ticket_id": ticket.ticket_id,
        "status": ticket.status,
        "title": ticket.title,
        "source_pdf_path": ticket.source_pdf_path,
        "markdown_length": ticket.markdown_length,
        "metadata": _loads(ticket.metadata_json, {}),
        "departments_needed": _loads(ticket.departments_needed_json, []),
        "sections": sections,
        "department_sections": department_sections,
        "unmapped_topics": _loads(ticket.unmapped_topics_json, []),
        "conflicts": _loads(ticket.conflicts_json, []),
        "intake_summary": ticket.intake_summary,
        "requires_ceo_approval": ticket.requires_ceo_approval,
        "discard_reason": ticket.discard_reason,
        "discard_rule_id": ticket.discard_rule_id,
        "error_message": ticket.error_message,
        "readability_scores": _loads(ticket.readability_json, {}),
        "trace": _loads(ticket.trace_json, []),
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }
