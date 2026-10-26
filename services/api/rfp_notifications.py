"""Brasaland corporate RFP registration and the SSE fan-out for that moment.

Marketing (Camila Ospina) opens a ticket when a catering, concession, or
co-branding request arrives. The ticket starts at ``analyzing``. Connected
staff hear ``rfp_ticket_created`` with the RFP fields from the Milestone 9
briefing: client, location, service, scope, deadline, optional budget in COP
or USD as written, and the departments the proposal needs.

This module does not publish emergency-order or waste events.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = REPO_ROOT / "data" / "uploads" / "rfp_tickets.sqlite3"
UPLOAD_ROOT = REPO_ROOT / "data" / "uploads" / "rfp"

COMPANY_SLUG = "brasaland"
TICKET_OWNER = "Camila Ospina"
STATUS_ANALYZING = "analyzing"
EVENT_RFP_TICKET_CREATED = "rfp_ticket_created"
DEPARTMENT_IDS = ("marketing", "operaciones", "procurement", "training")
DEPARTMENT_SET = frozenset(DEPARTMENT_IDS)
KEEPALIVE_SECONDS = 15
_FILENAME = re.compile(r"[^\w.\-]+")
_LOCK = threading.Lock()


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rfp_tickets (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL UNIQUE,
            rfp_id TEXT NOT NULL,
            status TEXT NOT NULL,
            client_name TEXT NOT NULL,
            location TEXT NOT NULL,
            country TEXT NOT NULL,
            currency TEXT NOT NULL,
            locations_json TEXT NOT NULL,
            service_type TEXT NOT NULL,
            scope TEXT NOT NULL,
            deadline TEXT NOT NULL,
            budget_range TEXT,
            departments_needed_json TEXT NOT NULL,
            raw_pdf_path TEXT NOT NULL,
            title TEXT,
            company TEXT NOT NULL,
            owner TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            terminal INTEGER NOT NULL
        )
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(rfp_tickets)")}
    if "country" not in columns:
        connection.execute("ALTER TABLE rfp_tickets ADD COLUMN country TEXT NOT NULL DEFAULT ''")
    if "currency" not in columns:
        connection.execute("ALTER TABLE rfp_tickets ADD COLUMN currency TEXT NOT NULL DEFAULT ''")
    if "locations_json" not in columns:
        connection.execute(
            "ALTER TABLE rfp_tickets ADD COLUMN locations_json TEXT NOT NULL DEFAULT '[]'"
        )
    return connection


def _row_to_ticket(row: sqlite3.Row) -> dict[str, Any]:
    departments = json.loads(row["departments_needed_json"] or "[]")
    return {
        "event_id": int(row["event_id"]),
        "ticket_id": row["ticket_id"],
        "rfp_id": row["rfp_id"],
        "status": row["status"],
        "client_name": row["client_name"],
        "location": row["location"],
        "country": row["country"],
        "currency": row["currency"],
        "locations": json.loads(row["locations_json"] or "[]"),
        "service_type": row["service_type"],
        "scope": row["scope"],
        "deadline": row["deadline"],
        "budget_range": row["budget_range"],
        "departments_needed": departments,
        "raw_pdf_path": row["raw_pdf_path"],
        "title": row["title"],
        "company": row["company"],
        "owner": row["owner"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "terminal": bool(row["terminal"]),
    }


def sse_payload(ticket: dict[str, Any]) -> dict[str, Any]:
    """Named-event body. ``ticket_id`` and ``status`` lead; RFP fields follow."""
    payload = {
        "ticket_id": ticket["ticket_id"],
        "status": ticket["status"],
        "rfp_id": ticket["rfp_id"],
        "company": ticket["company"],
        "client_name": ticket["client_name"],
        "location": ticket["location"],
        "country": ticket["country"],
        "currency": ticket["currency"],
        "locations": list(ticket["locations"]),
        "service_type": ticket["service_type"],
        "scope": ticket["scope"],
        "deadline": ticket["deadline"],
        "budget_range": ticket["budget_range"],
        "departments_needed": list(ticket["departments_needed"]),
        "raw_pdf_path": ticket["raw_pdf_path"],
        "owner": ticket["owner"],
        "created_at": ticket["created_at"],
        "updated_at": ticket["updated_at"],
        "terminal": bool(ticket["terminal"]),
        "event_id": int(ticket["event_id"]),
    }
    if ticket.get("title"):
        payload["title"] = ticket["title"]
    return payload


def encode_ticket_event(ticket: dict[str, Any]) -> str:
    body = json.dumps(sse_payload(ticket), separators=(",", ":"), ensure_ascii=False)
    return f"id: {ticket['event_id']}\nevent: {EVENT_RFP_TICKET_CREATED}\ndata: {body}\n\n"


def _clean_text(value: str, field: str, *, limit: int) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"{field} is required.")
    if len(text) > limit:
        raise ValueError(f"{field} must be {limit} characters or fewer.")
    return text


def _clean_budget(value: str | None, *, currency: str) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > 160:
        raise ValueError("budget_range must be 160 characters or fewer.")
    upper = text.upper()
    if re.search(r"\b(EUR|GBP|BRL)\b", upper):
        raise ValueError("budget_range uses COP or USD only.")
    other = "USD" if currency == "COP" else "COP"
    if currency not in upper or other in upper:
        raise ValueError(
            f"budget_range for this ticket must keep the amount in {currency} as written."
        )
    return text


def _clean_locations(values: list[str] | None) -> tuple[str, str, list[dict[str, str]]]:
    """One ticket serves one market. Colombia stays COP; Florida stays USD."""
    from locations import get_location

    chosen: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in values or []:
        for piece in str(raw).split(","):
            location_id = piece.strip()
            if not location_id or location_id in seen:
                continue
            site = get_location(location_id)
            if site is None:
                raise ValueError(
                    "locations must be Brasaland restaurant ids from the 14-location roster."
                )
            seen.add(location_id)
            chosen.append(
                {
                    "id": site.id,
                    "name": site.name,
                    "city": site.city,
                    "country": site.country,
                    "currency": site.currency,
                }
            )
    if not chosen:
        raise ValueError("Select at least one Brasaland location.")
    countries = {site["country"] for site in chosen}
    if len(countries) != 1:
        raise ValueError(
            "Keep Colombia and Florida locations on separate RFP tickets. COP and USD are not converted."
        )
    return chosen[0]["country"], chosen[0]["currency"], chosen


def _clean_departments(values: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        for piece in str(raw).split(","):
            department = piece.strip()
            if not department or department in seen:
                continue
            if department not in DEPARTMENT_SET:
                allowed = ", ".join(DEPARTMENT_IDS)
                raise ValueError(
                    f"departments_needed must use Brasaland ids ({allowed})."
                )
            seen.add(department)
            cleaned.append(department)
    return cleaned


def safe_filename(filename: str) -> str:
    name = Path(filename or "").name
    cleaned = _FILENAME.sub("_", name).strip("._")[:180]
    return cleaned or "rfp.pdf"


def list_tickets(*, limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM rfp_tickets
            ORDER BY event_id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 200)),),
        ).fetchall()
    return [_row_to_ticket(row) for row in rows]


def get_ticket(ticket_id: str) -> dict[str, Any] | None:
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM rfp_tickets WHERE ticket_id = ?",
            (ticket_id,),
        ).fetchone()
    return _row_to_ticket(row) if row else None


def tickets_after(last_event_id: str | None) -> list[dict[str, Any]]:
    """Tickets strictly after a Last-Event-ID. A missing or unusable cursor replays all."""
    cursor: int | None = None
    if last_event_id:
        try:
            cursor = int(last_event_id)
        except ValueError:
            cursor = None
    with _LOCK, _connect() as connection:
        if cursor is None:
            rows = connection.execute(
                "SELECT * FROM rfp_tickets ORDER BY event_id ASC"
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM rfp_tickets
                WHERE event_id > ?
                ORDER BY event_id ASC
                """,
                (cursor,),
            ).fetchall()
    return [_row_to_ticket(row) for row in rows]


def register_rfp(
    *,
    client_name: str,
    location: str,
    locations: list[str] | None,
    service_type: str,
    scope: str,
    deadline: str,
    budget_range: str | None,
    departments_needed: list[str] | None,
    original_filename: str,
    file_bytes: bytes,
    title: str | None = None,
) -> dict[str, Any]:
    """Persist one analyzing ticket and return it. Caller publishes the SSE event."""
    if not file_bytes:
        raise ValueError("The RFP file is empty.")
    if len(file_bytes) > 8_000_000:
        raise ValueError("The RFP file must be 8 MB or smaller.")

    client = _clean_text(client_name, "client_name", limit=160)
    place = _clean_text(location, "location", limit=160)
    country, currency, sites = _clean_locations(locations)
    service = _clean_text(service_type, "service_type", limit=160)
    work_scope = _clean_text(scope, "scope", limit=800)
    due = _clean_text(deadline, "deadline", limit=80)
    budget = _clean_budget(budget_range, currency=currency)
    departments = _clean_departments(departments_needed)
    cleaned_title = (title or "").strip() or None
    if cleaned_title and len(cleaned_title) > 180:
        raise ValueError("title must be 180 characters or fewer.")

    ticket_id = uuid4().hex
    rfp_id = f"rfp_{ticket_id}"
    now = _utcnow()
    filename = safe_filename(original_filename)
    folder = UPLOAD_ROOT / ticket_id
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / filename
    destination.write_bytes(file_bytes)
    try:
        relative = destination.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        relative = f"data/uploads/rfp/{ticket_id}/{filename}"

    with _LOCK, _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO rfp_tickets (
                ticket_id, rfp_id, status, client_name, location, country, currency,
                locations_json, service_type,
                scope, deadline, budget_range, departments_needed_json,
                raw_pdf_path, title, company, owner, created_at, updated_at, terminal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                rfp_id,
                STATUS_ANALYZING,
                client,
                place,
                country,
                currency,
                json.dumps(sites),
                service,
                work_scope,
                due,
                budget,
                json.dumps(departments),
                relative,
                cleaned_title,
                COMPANY_SLUG,
                TICKET_OWNER,
                now,
                now,
                0,
            ),
        )
        event_id = int(cursor.lastrowid)
        connection.commit()
        row = connection.execute(
            "SELECT * FROM rfp_tickets WHERE event_id = ?",
            (event_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("RFP ticket was not stored.")
    return _row_to_ticket(row)


def reset_rfp_state() -> None:
    """Drop tickets and subscribers. Tests call this between cases."""
    hub.reset()
    with _LOCK:
        if DATABASE_PATH.exists():
            DATABASE_PATH.unlink()
        parent = UPLOAD_ROOT
        if parent.exists():
            for child in parent.iterdir():
                if child.is_dir():
                    for item in child.iterdir():
                        item.unlink(missing_ok=True)
                    child.rmdir()


class RfpHub:
    """In-process fan-out. Replay itself is read from the ticket table."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def reset(self) -> None:
        self._subscribers.clear()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, ticket: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            self._deliver(queue, ticket)

    def _deliver(self, queue: asyncio.Queue[dict[str, Any]], ticket: dict[str, Any]) -> None:
        loop = self._loop

        def _put() -> None:
            try:
                queue.put_nowait(ticket)
            except asyncio.QueueFull:
                return

        if loop is None or not loop.is_running():
            _put()
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            _put()
            return
        loop.call_soon_threadsafe(_put)


hub = RfpHub()
