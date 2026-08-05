"""Typed contracts for agent tools outside the RAG (Part 2).

Ticket tool I/O mirrors the incident manager API
(``GET /api/incidents``, ``GET /api/incidents/{id}``): the same fields the CSV
/ store exposes — ``incident_id``, ``date``, ``location_id``, ``category``,
``description``, ``status``, ``customer_id``, ``satisfaction_score``,
``reporter_id``, plus ``source`` (data origin).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TicketLookupInput(BaseModel):
    """Input contract for the read-only ticket lookup tool.

    Provide either ``ticket_id`` (exact get-by-id) and/or search filters.
    At least one of ``ticket_id``, ``status``, ``category``, ``location_id``,
    ``date_from``, or ``date_to`` must be set.
    """

    model_config = ConfigDict(extra="forbid")

    ticket_id: str | None = Field(
        default=None,
        description="Exact incident id, e.g. BRS-000002 (maps to GET /api/incidents/{id}).",
    )
    status: str | None = Field(
        default=None,
        description="Filter by status (ABIERTO | CERRADO | DESCARTADO).",
    )
    category: str | None = Field(
        default=None,
        description="Filter by category (e.g. EQUIPAMIENTO, ABASTECIMIENTO).",
    )
    location_id: str | None = Field(
        default=None,
        description="Filter by location id (e.g. COL-02).",
    )
    date_from: str | None = Field(
        default=None,
        description="Inclusive lower bound on incident date (YYYY-MM-DD).",
    )
    date_to: str | None = Field(
        default=None,
        description="Inclusive upper bound on incident date (YYYY-MM-DD).",
    )

    @model_validator(mode="after")
    def _require_id_or_filters(self) -> TicketLookupInput:
        if any(
            [
                self.ticket_id,
                self.status,
                self.category,
                self.location_id,
                self.date_from,
                self.date_to,
            ]
        ):
            return self
        raise ValueError(
            "TicketLookupInput requires ticket_id and/or at least one search filter "
            "(status, category, location_id, date_from, date_to)."
        )


class TicketRecord(BaseModel):
    """One ticket as returned by the incident API (tool output item)."""

    model_config = ConfigDict(extra="forbid")

    incident_id: str
    date: str
    location_id: str | None = None
    category: str
    description: str
    status: str
    customer_id: str | None = None
    satisfaction_score: float | None = None
    reporter_id: str | None = None
    source: str = Field(
        default="incident_manager",
        description="Origin of the live record (incident manager).",
    )


class TicketLookupOutput(BaseModel):
    """Output contract for the ticket lookup tool.

    On success ``ok=True`` and ``tickets`` holds zero or more records.
    On failure (timeout, HTTP error, invalid response) ``ok=False``, ``tickets``
    is empty, and ``error`` explains why — never invent a status.
    """

    model_config = ConfigDict(extra="forbid")

    ok: bool
    tickets: list[TicketRecord] = Field(default_factory=list)
    error: (
        Literal[
            "not_found",
            "timeout",
            "service_error",
            "invalid_input",
            "auth_error",
        ]
        | None
    ) = None
    message: str | None = Field(
        default=None,
        description="Human-readable detail for fallback answers / traces.",
    )
    duration_ms: int = 0
