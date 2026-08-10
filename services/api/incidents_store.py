"""Incident store backed by the company CSV seed, with runtime create/status.

Used by ``GET /api/incidents``, ``POST /api/incidents``,
``GET /api/incidents/{id}``, ``PATCH /api/incidents/{id}/status``, and
(optionally) in-process callers. This is the same operational data the
incident manager already owns — not a parallel fake dataset.
"""

from __future__ import annotations

import csv
import threading
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INCIDENTS_CSV = REPO_ROOT / "scripts" / "incidents-COMPANY.csv"

# Brasaland lifecycle statuses (uppercase Spanish labels from the CSV).
VALID_STATUSES = frozenset({"ABIERTO", "CERRADO", "DESCARTADO"})
# Allowed transitions for PATCH /api/incidents/{id}/status.
STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "ABIERTO": frozenset({"CERRADO", "DESCARTADO"}),
    "CERRADO": frozenset({"ABIERTO"}),
    "DESCARTADO": frozenset({"ABIERTO"}),
}

_LOCK = threading.RLock()
_RUNTIME: dict[str, "IncidentRecord"] | None = None


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


class IncidentCreateInput(BaseModel):
    """Body for ``POST /api/incidents``."""

    model_config = ConfigDict(extra="forbid")

    category: str
    description: str
    status: str = "ABIERTO"
    date: str | None = None
    location_id: str | None = None
    customer_id: str | None = None
    satisfaction_score: float | None = None
    reporter_id: str | None = None


class IncidentStatusUpdate(BaseModel):
    """Body for ``PATCH /api/incidents/{id}/status`` — status only."""

    model_config = ConfigDict(extra="forbid")

    status: str


class IncidentLifecycleError(ValueError):
    """Raised when a status transition is not allowed."""


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


def _normalize_status(status: str) -> str:
    return status.strip().upper()


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


def _load_csv(*, csv_path: Path | None = None) -> dict[str, IncidentRecord]:
    path = csv_path or DEFAULT_INCIDENTS_CSV
    records: dict[str, IncidentRecord] = {}
    if not path.exists():
        return records
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not (row.get("incident_id") or "").strip():
                continue
            record = _row_to_record(row)
            records[record.incident_id] = record
    return records


def _ensure_runtime(*, csv_path: Path | None = None) -> dict[str, IncidentRecord]:
    global _RUNTIME
    with _LOCK:
        if _RUNTIME is None:
            _RUNTIME = _load_csv(csv_path=csv_path)
        return _RUNTIME


def reset_runtime(*, csv_path: Path | None = None) -> None:
    """Reload the in-memory store from CSV (tests / local resets)."""
    global _RUNTIME
    with _LOCK:
        _RUNTIME = _load_csv(csv_path=csv_path)


def load_incidents(*, csv_path: Path | None = None) -> list[IncidentRecord]:
    """Load all incidents (CSV seed + runtime creates/updates)."""
    store = _ensure_runtime(csv_path=csv_path)
    with _LOCK:
        return list(store.values())


def get_incident(incident_id: str, *, csv_path: Path | None = None) -> IncidentRecord | None:
    """Return one incident by id, or ``None`` if missing."""
    needle = incident_id.strip().casefold()
    store = _ensure_runtime(csv_path=csv_path)
    with _LOCK:
        for record in store.values():
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


def _next_incident_id(store: dict[str, IncidentRecord]) -> str:
    max_num = 0
    for incident_id in store:
        if not incident_id.upper().startswith("BRS-"):
            continue
        suffix = incident_id.split("-", 1)[-1]
        try:
            max_num = max(max_num, int(suffix))
        except ValueError:
            continue
    return f"BRS-{max_num + 1:06d}"


def create_incident(
    payload: IncidentCreateInput | dict[str, Any],
    *,
    csv_path: Path | None = None,
) -> IncidentRecord:
    """Create a new incident ticket in the runtime store."""
    if isinstance(payload, dict):
        data = IncidentCreateInput.model_validate(payload)
    else:
        data = payload

    status = _normalize_status(data.status)
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{data.status}'. Expected one of: {sorted(VALID_STATUSES)}")

    store = _ensure_runtime(csv_path=csv_path)
    with _LOCK:
        incident_id = _next_incident_id(store)
        record = IncidentRecord(
            incident_id=incident_id,
            date=(data.date or date.today().isoformat()),
            location_id=_empty_to_none(data.location_id),
            category=data.category.strip(),
            description=data.description.strip(),
            status=status,
            customer_id=_empty_to_none(data.customer_id),
            satisfaction_score=data.satisfaction_score,
            reporter_id=_empty_to_none(data.reporter_id),
            source="incident_manager",
        )
        if not record.category or not record.description:
            raise ValueError("category and description are required")
        store[incident_id] = record
        return record


def update_incident_status(
    incident_id: str,
    new_status: str,
    *,
    csv_path: Path | None = None,
) -> IncidentRecord:
    """Apply a lifecycle status change (``PATCH .../status``)."""
    status = _normalize_status(new_status)
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{new_status}'. Expected one of: {sorted(VALID_STATUSES)}")

    store = _ensure_runtime(csv_path=csv_path)
    with _LOCK:
        current = None
        key = None
        needle = incident_id.strip().casefold()
        for existing_id, record in store.items():
            if existing_id.casefold() == needle:
                current = record
                key = existing_id
                break
        if current is None or key is None:
            raise KeyError(incident_id)

        current_status = _normalize_status(current.status)
        allowed = STATUS_TRANSITIONS.get(current_status, frozenset())
        if status == current_status:
            return current
        if status not in allowed:
            raise IncidentLifecycleError(
                f"Cannot transition status from {current_status} to {status}. "
                f"Allowed: {sorted(allowed) if allowed else 'none'}"
            )
        updated = current.model_copy(update={"status": status})
        store[key] = updated
        return updated


def incident_to_dict(record: IncidentRecord) -> dict[str, Any]:
    return record.model_dump()
