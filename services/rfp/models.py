"""SQLModel entities for RFP intake (CONTEXT Milestone 9).

Persisted in PostgreSQL (Supabase) via DATABASE_URL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class RfpTicket(SQLModel, table=True):
    """Ticket row — status machine + pointers to raw PDF / markdown."""

    __tablename__ = "rfp_tickets"

    ticket_id: str = Field(primary_key=True, default_factory=lambda: uuid4().hex)
    status: str = Field(default="analyzing", index=True)
    title: Optional[str] = None
    source_pdf_path: Optional[str] = None
    markdown_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    markdown_length: int = 0
    # RFP metadata (CONTEXT §2.3) — JSON object as text for SQLite/Postgres portability
    metadata_json: str = Field(default="{}", sa_column=Column(Text))
    departments_needed_json: str = Field(default="[]", sa_column=Column(Text))
    unmapped_topics_json: str = Field(default="[]", sa_column=Column(Text))
    conflicts_json: str = Field(default="[]", sa_column=Column(Text))
    intake_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    requires_ceo_approval: bool = False
    discard_reason: Optional[str] = None
    discard_rule_id: Optional[str] = None
    error_message: Optional[str] = None
    readability_json: str = Field(default="{}", sa_column=Column(Text))
    trace_json: str = Field(default="[]", sa_column=Column(Text))
    # Part 2 routing — flag + persisted handoff contract (no second API)
    part2_ready: bool = Field(default=False, index=True)
    part2_routed_at: Optional[str] = None
    part2_handoff_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    part3_ready: bool = Field(default=False, index=True)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class RfpDepartmentSection(SQLModel, table=True):
    """Per-department section — Part 1 stores key_aspects only."""

    __tablename__ = "rfp_department_sections"
    __table_args__ = (
        UniqueConstraint("ticket_id", "department_id", name="uq_rfp_ticket_department"),
    )

    id: str = Field(primary_key=True, default_factory=lambda: uuid4().hex)
    ticket_id: str = Field(index=True, foreign_key="rfp_tickets.ticket_id")
    department_id: str = Field(index=True)
    key_aspects_json: str = Field(default="[]", sa_column=Column(Text))
    # Reserved for Parts 2–3
    draft_content: Optional[str] = Field(default=None, sa_column=Column(Text))
    evaluation_results_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    approval_status: Optional[str] = None
    approver: Optional[str] = None
    approved_at: Optional[str] = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class RfpFinalDocument(SQLModel, table=True):
    """CONTEXT §2.3 FinalDocument — generated only after required sign-off."""

    __tablename__ = "rfp_final_documents"

    ticket_id: str = Field(primary_key=True, foreign_key="rfp_tickets.ticket_id")
    sections_json: str = Field(default="[]", sa_column=Column(Text))
    total_estimated_value: Optional[float] = None
    generated_at: str = Field(default_factory=_now)
    markdown: Optional[str] = Field(default=None, sa_column=Column(Text))
    document_json: str = Field(default="{}", sa_column=Column(Text))
