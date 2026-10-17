"""SQLite store for the Brasaland incident manager.

Uses the same data directory as the staff user database. Seed idempotency
keeps the legacy CSV incident_id in source_incident_id; the public id is a
new UUID and the CSV key is not part of the API model.
"""
from __future__ import annotations

import csv
import os
import sqlite3
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from packages.shared.incident_rules import (  # noqa: E402
    BRANCH_VALUES,
    MODEL_CATEGORIES,
    MODEL_ORIGINS,
    MODEL_STATUSES,
    empty_summary,
    transform_csv_row,
    transition_error,
    validate_record,
)

PUBLIC_FIELDS = (
    "id",
    "title",
    "description",
    "category",
    "status",
    "origin",
    "branch",
    "created_at",
    "updated_at",
)


def database_path() -> Path:
    override = os.environ.get("INCIDENTS_DATABASE_PATH")
    if override:
        return Path(override)
    return _REPO_ROOT / "data" / "company_api.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS incidents (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL,
            origin TEXT NOT NULL,
            branch TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source_incident_id TEXT UNIQUE,
            CHECK (category IN (
                'equipment_failure', 'supply_issue', 'customer_complaint', 'staff_issue',
                'facility_issue', 'pos_system', 'delivery_issue', 'other'
            )),
            CHECK (status IN ('open', 'in_progress', 'resolved', 'discarded')),
            CHECK (origin IN ('customer', 'branch', 'internal')),
            CHECK (branch IN (
                'central', 'medellin_centro', 'medellin_laureles', 'medellin_envigado',
                'medellin_bello', 'medellin_itagui', 'bogota_chapinero', 'bogota_usaquen',
                'cali_granada', 'barranquilla_norte', 'miami_doral', 'miami_hialeah',
                'miami_kendall', 'orlando_international', 'fort_lauderdale'
            ))
        )
        """
    )
    connection.commit()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def to_public(row: sqlite3.Row) -> dict[str, str]:
    return {key: row[key] for key in PUBLIC_FIELDS}


def list_incidents(
    *,
    status: str | None = None,
    origin: str | None = None,
    branch: str | None = None,
    category: str | None = None,
    connection: sqlite3.Connection | None = None,
) -> list[dict[str, str]]:
    own = connection is None
    conn = connection or connect()
    try:
        init_db(conn)
        clauses: list[str] = []
        params: list[str] = []
        for column, value in (
            ("status", status),
            ("origin", origin),
            ("branch", branch),
            ("category", category),
        ):
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"""
            SELECT {", ".join(PUBLIC_FIELDS)}
            FROM incidents
            {where}
            ORDER BY created_at DESC, id DESC
            """,
            params,
        ).fetchall()
        return [to_public(row) for row in rows]
    finally:
        if own:
            conn.close()


def get_incident(incident_id: str, connection: sqlite3.Connection | None = None) -> dict[str, str] | None:
    own = connection is None
    conn = connection or connect()
    try:
        init_db(conn)
        row = conn.execute(
            f"SELECT {', '.join(PUBLIC_FIELDS)} FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()
        return to_public(row) if row else None
    finally:
        if own:
            conn.close()


def insert_incident(fields: dict[str, str], connection: sqlite3.Connection | None = None) -> dict[str, str]:
    own = connection is None
    conn = connection or connect()
    try:
        init_db(conn)
        incident_id = fields.get("id") or str(uuid.uuid4())
        created_at = fields.get("created_at") or _now()
        updated_at = fields.get("updated_at") or created_at
        conn.execute(
            """
            INSERT INTO incidents (
                id, title, description, category, status, origin, branch,
                created_at, updated_at, source_incident_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id,
                fields["title"].strip(),
                fields["description"],
                fields["category"],
                fields["status"],
                fields["origin"],
                fields["branch"],
                created_at,
                updated_at,
                fields.get("source_incident_id"),
            ),
        )
        conn.commit()
        stored = get_incident(incident_id, connection=conn)
        if stored is None:
            raise RuntimeError("incident insert did not persist")
        return stored
    finally:
        if own:
            conn.close()


def update_status(
    incident_id: str, status: str, connection: sqlite3.Connection | None = None
) -> dict[str, str] | None:
    own = connection is None
    conn = connection or connect()
    try:
        init_db(conn)
        current = conn.execute(
            "SELECT status FROM incidents WHERE id = ?",
            (incident_id,),
        ).fetchone()
        if current is None:
            return None
        error = transition_error(current["status"], status)
        if error is not None:
            raise ValueError(error.message)
        if status != current["status"]:
            conn.execute(
                "UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), incident_id),
            )
            conn.commit()
        stored = get_incident(incident_id, connection=conn)
        return stored
    finally:
        if own:
            conn.close()


def summary(connection: sqlite3.Connection | None = None) -> dict:
    own = connection is None
    conn = connection or connect()
    try:
        init_db(conn)
        totals = empty_summary()
        rows = conn.execute(
            "SELECT status, category, origin, branch FROM incidents"
        ).fetchall()
        totals["total"] = len(rows)
        for row in rows:
            if row["status"] in MODEL_STATUSES:
                totals["by_status"][row["status"]] += 1
            if row["category"] in MODEL_CATEGORIES:
                totals["by_category"][row["category"]] += 1
            if row["origin"] in MODEL_ORIGINS:
                totals["by_origin"][row["origin"]] += 1
            if row["branch"] in BRANCH_VALUES:
                totals["by_branch"][row["branch"]] += 1
        return totals
    finally:
        if own:
            conn.close()


@dataclass
class SeedReport:
    inserted: int = 0
    already_present: int = 0
    invalid: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            "Brasaland incident seed",
            f"Inserted: {self.inserted}",
            f"Already present: {self.already_present}",
            f"Invalid CSV rows (not inserted): {len(self.invalid)}",
        ]
        if self.invalid:
            lines.append("Invalid records:")
            lines.extend(f"  - {item}" for item in self.invalid)
        return "\n".join(lines)


def seed_csv(csv_path: Path, database: Path | None = None) -> SeedReport:
    report = SeedReport()
    conn = connect(database)
    try:
        init_db(conn)
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for record in reader:
                validation = validate_record(record)
                incident_key = (record.get("incident_id") or "").strip() or "unknown"
                if not validation.is_valid:
                    report.invalid.append(f"{incident_key}: {', '.join(validation.reasons)}")
                    continue
                transformed = transform_csv_row(record)
                if transformed is None:
                    report.invalid.append(f"{incident_key}: could not map row")
                    continue
                existing = conn.execute(
                    "SELECT id FROM incidents WHERE source_incident_id = ?",
                    (transformed["source_incident_id"],),
                ).fetchone()
                if existing is not None:
                    report.already_present += 1
                    continue
                insert_incident(transformed, connection=conn)
                report.inserted += 1
        return report
    finally:
        conn.close()
