"""SQLModel persistence for RFP tickets (SQLite locally; DATABASE_URL for Postgres)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from sqlmodel import Field, Session, SQLModel, create_engine, select

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE = REPO_ROOT / "data" / "process" / "rfp-intake" / "rfp.sqlite"

_engine = None
_engine_url: str | None = None


def _database_url() -> str:
    env = (os.getenv("DATABASE_URL") or "").strip()
    if env:
        return env
    DEFAULT_SQLITE.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_SQLITE}"


def get_engine():
    global _engine, _engine_url
    url = _database_url()
    if _engine is None or _engine_url != url:
        kwargs = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
        _engine_url = url
    return _engine


def reset_engine() -> None:
    global _engine, _engine_url
    _engine = None
    _engine_url = None


class RfpTicket(SQLModel, table=True):
    __tablename__ = "rfp_tickets"

    ticket_id: str = Field(primary_key=True, default_factory=lambda: uuid4().hex)
    status: str = Field(default="analyzing", index=True)
    title: str | None = None
    source_pdf_path: str | None = None
    markdown_text: str | None = None
    markdown_length: int = 0
    metadata_json: str = Field(default="{}")
    departments_needed_json: str = Field(default="[]")
    sections_json: str = Field(default="{}")
    unmapped_topics_json: str = Field(default="[]")
    conflicts_json: str = Field(default="[]")
    intake_summary: str | None = None
    requires_ceo_approval: bool = False
    discard_reason: str | None = None
    discard_rule_id: str | None = None
    error_message: str | None = None
    readability_json: str = Field(default="{}")
    trace_json: str = Field(default="[]")
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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


def save_intake_result(ticket_id: str, result: Any, *, source_pdf_path: str) -> RfpTicket:
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
        ticket.sections_json = json.dumps(result.sections, ensure_ascii=False)
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
        session.commit()
        session.refresh(ticket)
        return ticket.model_copy(deep=True)


def ticket_to_dict(ticket: RfpTicket) -> dict[str, Any]:
    def _loads(raw: str, default: Any) -> Any:
        try:
            return json.loads(raw or "")
        except json.JSONDecodeError:
            return default

    return {
        "ticket_id": ticket.ticket_id,
        "status": ticket.status,
        "title": ticket.title,
        "source_pdf_path": ticket.source_pdf_path,
        "markdown_length": ticket.markdown_length,
        "metadata": _loads(ticket.metadata_json, {}),
        "departments_needed": _loads(ticket.departments_needed_json, []),
        "sections": _loads(ticket.sections_json, {}),
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
