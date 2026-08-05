"""Read-only incident store backed by the company CSV seed.

Used by ``GET /api/incidents`` / ``GET /api/incidents/{id}`` and (optionally)
in-process callers. This is the same operational data the incident manager
already owns — not a parallel fake dataset.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INCIDENTS_CSV = REPO_ROOT / "scripts" / "incidents-COMPANY.csv"


class IncidentRecord(BaseModel):
    """One incident ticket — fields match the incident manager CSV / API."""

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
        description="Data origin for tool/API consumers (live incident system).",
    )


class IncidentSearchFilters(BaseModel):
    """Optional list filters for ``GET /api/incidents``."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    category: str | None = None
    location_id: str | None = None
    date_from: str | None = None
    date_to: str | None = None


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_score(raw: str | None) -> float | None:
    text = _empty_to_none(raw)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _row_to_record(row: dict[str, str]) -> IncidentRecord:
    return IncidentRecord(
        incident_id=(row.get("incident_id") or "").strip(),
        date=(row.get("date") or "").strip(),
        location_id=_empty_to_none(row.get("location_id")),
        category=(row.get("category") or "").strip(),
        description=(row.get("description") or "").strip(),
        status=(row.get("status") or "").strip(),
        customer_id=_empty_to_none(row.get("customer_id")),
        satisfaction_score=_parse_score(row.get("satisfaction_score")),
        reporter_id=_empty_to_none(row.get("reporter_id")),
        source="incident_manager",
    )


def load_incidents(*, csv_path: Path | None = None) -> list[IncidentRecord]:
    """Load all incidents from the company CSV (read-only)."""
    path = csv_path or DEFAULT_INCIDENTS_CSV
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [_row_to_record(row) for row in reader if (row.get("incident_id") or "").strip()]


def get_incident(incident_id: str, *, csv_path: Path | None = None) -> IncidentRecord | None:
    """Return one incident by id, or ``None`` if missing."""
    needle = incident_id.strip().casefold()
    for record in load_incidents(csv_path=csv_path):
        if record.incident_id.casefold() == needle:
            return record
    return None


def search_incidents(
    filters: IncidentSearchFilters | None = None,
    *,
    csv_path: Path | None = None,
) -> list[IncidentRecord]:
    """Filter incidents by optional status / category / location / date range."""
    records = load_incidents(csv_path=csv_path)
    if filters is None:
        return records

    out: list[IncidentRecord] = []
    for record in records:
        if filters.status and record.status.casefold() != filters.status.casefold():
            continue
        if filters.category and record.category.casefold() != filters.category.casefold():
            continue
        if filters.location_id and (record.location_id or "").casefold() != filters.location_id.casefold():
            continue
        if filters.date_from and record.date < filters.date_from:
            continue
        if filters.date_to and record.date > filters.date_to:
            continue
        out.append(record)
    return out


def incident_to_dict(record: IncidentRecord) -> dict[str, Any]:
    return record.model_dump()
