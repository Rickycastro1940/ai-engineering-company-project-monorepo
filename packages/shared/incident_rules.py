"""Brasaland incident rules shared by the CSV analyzer, the seed script, and the API.

CSV rules follow the incidents-file-analyzer contract (OPEN/CLOSED/DISCARDED and
CUSTOMER_COMPLAINT/EQUIPMENT/SUPPLY/FOOD_QUALITY/STAFF). The live manager uses
the centralized incident model (open/in_progress/resolved/discarded, branch
slugs, and the eight manager categories). Seed transforms one into the other.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

CSV_CATEGORIES = frozenset(
    {"CUSTOMER_COMPLAINT", "EQUIPMENT", "SUPPLY", "FOOD_QUALITY", "STAFF"}
)
CSV_STATUSES = frozenset({"OPEN", "CLOSED", "DISCARDED"})
CSV_LOCATIONS = frozenset(
    {f"COL-{index:02d}" for index in range(1, 11)}
    | {f"FLA-{index:02d}" for index in range(1, 5)}
)
REQUIRED_COLUMNS = [
    "incident_id",
    "date",
    "location_id",
    "category",
    "description",
    "status",
    "customer_id",
    "satisfaction_score",
    "reporter_id",
]
MIN_DESCRIPTION_LENGTH = 5

# Names kept for the existing analyzer imports.
VALID_CATEGORIES = CSV_CATEGORIES
VALID_STATUSES = CSV_STATUSES

MODEL_CATEGORIES = (
    "equipment_failure",
    "supply_issue",
    "customer_complaint",
    "staff_issue",
    "facility_issue",
    "pos_system",
    "delivery_issue",
    "other",
)
MODEL_STATUSES = ("open", "in_progress", "resolved", "discarded")
MODEL_ORIGINS = ("customer", "branch", "internal")
BRANCHES: tuple[tuple[str, str], ...] = (
    ("central", "Central (Medellín / Miami)"),
    ("medellin_centro", "Medellín Centro"),
    ("medellin_laureles", "Medellín Laureles"),
    ("medellin_envigado", "Medellín Envigado"),
    ("medellin_bello", "Medellín Bello"),
    ("medellin_itagui", "Medellín Itagüí"),
    ("bogota_chapinero", "Bogotá Chapinero"),
    ("bogota_usaquen", "Bogotá Usaquén"),
    ("cali_granada", "Cali Granada"),
    ("barranquilla_norte", "Barranquilla Norte"),
    ("miami_doral", "Miami Doral"),
    ("miami_hialeah", "Miami Hialeah"),
    ("miami_kendall", "Miami Kendall"),
    ("orlando_international", "Orlando International Drive"),
    ("fort_lauderdale", "Fort Lauderdale"),
)
BRANCH_VALUES = frozenset(value for value, _label in BRANCHES)
BRANCH_LABELS = dict(BRANCHES)

CATEGORY_LABELS = {
    "equipment_failure": "Equipment failure",
    "supply_issue": "Supply issue",
    "customer_complaint": "Customer complaint",
    "staff_issue": "Staff issue",
    "facility_issue": "Facility issue",
    "pos_system": "POS system",
    "delivery_issue": "Delivery issue",
    "other": "Other",
}
STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In progress",
    "resolved": "Resolved",
    "discarded": "Discarded",
}
ORIGIN_LABELS = {
    "customer": "Customer",
    "branch": "Branch",
    "internal": "Internal",
}

CATEGORY_MAP = {
    "CUSTOMER_COMPLAINT": "customer_complaint",
    "EQUIPMENT": "equipment_failure",
    "SUPPLY": "supply_issue",
    "FOOD_QUALITY": "customer_complaint",
    "STAFF": "staff_issue",
}
STATUS_MAP = {
    "OPEN": "open",
    "CLOSED": "resolved",
    "DISCARDED": "discarded",
}
BRANCH_MAP = {
    "COL-01": "medellin_centro",
    "COL-02": "medellin_laureles",
    "COL-03": "medellin_envigado",
    "COL-04": "medellin_bello",
    "COL-05": "medellin_itagui",
    "COL-06": "bogota_chapinero",
    "COL-07": "bogota_usaquen",
    "COL-08": "cali_granada",
    "COL-09": "barranquilla_norte",
    "COL-10": "central",
    "FLA-01": "miami_doral",
    "FLA-02": "miami_hialeah",
    "FLA-03": "miami_kendall",
    "FLA-04": "orlando_international",
}

TRANSITIONS = {
    "open": frozenset({"in_progress", "discarded"}),
    "in_progress": frozenset({"resolved", "discarded"}),
    "resolved": frozenset(),
    "discarded": frozenset(),
}

TITLE_MAX_LENGTH = 120


@dataclass(frozen=True)
class FieldError:
    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    reasons: list[str]


def _text(record: dict[str, str], key: str) -> str:
    return (record.get(key) or "").strip()


def _parse_score(raw_value: str) -> int | None:
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        score = int(value)
    except ValueError:
        return None
    return score if 1 <= score <= 5 else None


def validate_record(record: dict[str, str]) -> ValidationResult:
    """Validate one analyzer CSV row. Invalid rows must not be seeded."""
    reasons: list[str] = []
    if not _text(record, "incident_id"):
        reasons.append("missing incident_id")
    raw_date = _text(record, "date")
    if not raw_date:
        reasons.append("missing date")
    else:
        try:
            date.fromisoformat(raw_date)
        except ValueError:
            reasons.append("invalid date")
    location = _text(record, "location_id").upper()
    if not location or location not in CSV_LOCATIONS:
        reasons.append("missing location_id")
    if _text(record, "category").upper() not in CSV_CATEGORIES:
        reasons.append("invalid category")
    if len(_text(record, "description")) < MIN_DESCRIPTION_LENGTH:
        reasons.append("description too short")
    if not _text(record, "reporter_id"):
        reasons.append("missing reporter_id")
    status = _text(record, "status").upper()
    if status not in CSV_STATUSES:
        reasons.append("invalid status")
    raw_score = (record.get("satisfaction_score") or "").strip()
    if raw_score and _parse_score(raw_score) is None:
        reasons.append("satisfaction_score out of range")
    if status == "CLOSED" and _parse_score(raw_score) is None:
        reasons.append("closed incident missing satisfaction_score")
    return ValidationResult(is_valid=not reasons, reasons=reasons)


def transform_csv_row(record: dict[str, str]) -> dict[str, str] | None:
    """Map one valid CSV row onto the incident manager model.

    Returns None when the row fails analyzer validation or the title is empty.
    """
    validation = validate_record(record)
    if not validation.is_valid:
        return None
    description = record.get("description") or ""
    title = description.strip()[:TITLE_MAX_LENGTH]
    if not title:
        return None
    location = _text(record, "location_id").upper()
    created_at = (
        datetime.combine(date.fromisoformat(_text(record, "date")), datetime.min.time(), tzinfo=timezone.utc)
        .isoformat()
    )
    return {
        "source_incident_id": _text(record, "incident_id"),
        "title": title,
        "description": description,
        "category": CATEGORY_MAP[_text(record, "category").upper()],
        "status": STATUS_MAP[_text(record, "status").upper()],
        "origin": "customer",
        "branch": BRANCH_MAP.get(location, "central"),
        "created_at": created_at,
        "updated_at": created_at,
    }


def validate_incident_payload(payload: dict) -> list[FieldError]:
    """Validate a live incident create body. Every problem names its field."""
    errors: list[FieldError] = []
    if not isinstance(payload, dict):
        return [FieldError("body", "Send the incident as JSON.")]

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(FieldError("title", "Enter a short title."))
    elif len(title.strip()) > TITLE_MAX_LENGTH:
        errors.append(FieldError("title", "Keep the title to 120 characters or fewer."))

    description = payload.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(FieldError("description", "Describe what happened."))

    category = payload.get("category")
    if category not in MODEL_CATEGORIES:
        errors.append(FieldError("category", "Choose a category from the list."))

    status = payload.get("status")
    if status not in MODEL_STATUSES:
        errors.append(FieldError("status", "Choose a valid status."))

    origin = payload.get("origin")
    if origin not in MODEL_ORIGINS:
        errors.append(FieldError("origin", "Choose where this report came from."))

    branch = payload.get("branch")
    if branch not in BRANCH_VALUES:
        errors.append(FieldError("branch", "Choose the branch for this incident."))

    return errors


def transition_error(current: str, nxt: str) -> FieldError | None:
    if nxt not in MODEL_STATUSES:
        return FieldError("status", "Choose a valid status.")
    if nxt == current:
        return None
    allowed = TRANSITIONS.get(current, frozenset())
    if nxt not in allowed:
        return FieldError(
            "status",
            "That status change is not allowed from the current state.",
        )
    return None


def empty_summary() -> dict:
    return {
        "total": 0,
        "by_status": {status: 0 for status in MODEL_STATUSES},
        "by_category": {category: 0 for category in MODEL_CATEGORIES},
        "by_origin": {origin: 0 for origin in MODEL_ORIGINS},
        "by_branch": {branch: 0 for branch, _label in BRANCHES},
    }
