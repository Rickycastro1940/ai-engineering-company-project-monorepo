"""Evaluate: Ticket, RFP metadata, and key_aspects persist via SQLModel → PostgreSQL (Supabase).

CONTEXT §2.3: TinyDB / JSON files are not the source of truth for these entities.
Production path: DATABASE_URL (postgresql…) / Supabase. Sqlite only for pytest / allowlist.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from data.pipelines.rfp_intake.constants import RFP_METADATA_FIELDS, STATUS_INTAKE_COMPLETE
from services.api import database as db_layer
from services.rfp.models import RfpDepartmentSection, RfpTicket
from services.rfp.store import (
    get_ticket,
    init_db,
    list_sections,
    reset_engine,
    ticket_to_dict,
)
from services.rfp import router as rfp_router

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
CONTEXT_META_KEYS = (
    "client_name",
    "location",
    "service_type",
    "scope",
    "deadline",
    "budget_range",
)


def test_models_are_sqlmodel_tables_not_tinydb() -> None:
    assert issubclass(RfpTicket, SQLModel)
    assert issubclass(RfpDepartmentSection, SQLModel)
    assert getattr(RfpTicket, "__tablename__") == "rfp_tickets"
    assert getattr(RfpDepartmentSection, "__tablename__") == "rfp_department_sections"
    # Ticket fields (CONTEXT §2.3)
    for col in ("ticket_id", "status", "source_pdf_path", "created_at", "updated_at"):
        assert hasattr(RfpTicket, col)
    assert hasattr(RfpTicket, "metadata_json")
    # DepartmentSection.key_aspects
    assert hasattr(RfpDepartmentSection, "department_id")
    assert hasattr(RfpDepartmentSection, "key_aspects_json")


def test_store_and_models_never_import_tinydb_for_rfp() -> None:
    store_src = (REPO / "services" / "rfp" / "store.py").read_text(encoding="utf-8")
    models_src = (REPO / "services" / "rfp" / "models.py").read_text(encoding="utf-8")
    assert "tinydb" not in store_src.casefold()
    assert "tinydb" not in models_src.casefold()
    assert "from sqlmodel import" in store_src
    assert "Session" in store_src
    assert "PostgreSQL" in models_src or "Postgres" in models_src or "DATABASE_URL" in models_src


def test_database_url_prefers_postgres_supabase_over_default_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_engine()
    monkeypatch.delenv("RFP_ALLOW_SQLITE", raising=False)
    # Simulate production: DATABASE_URL set to Supabase-style Postgres
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:pass@db.example.supabase.co:5432/postgres",
    )
    # Clear pytest marker so sqlite fallback is not chosen when URL is set
    url = db_layer.database_url()
    assert url.startswith("postgresql"), url
    assert "supabase" in url or "postgresql" in url

    # Without DATABASE_URL and without allowlist outside pytest → hard error
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        db_layer.database_url()


def test_database_module_documents_tinydb_not_rfp_source_of_truth() -> None:
    src = (REPO / "services" / "api" / "database.py").read_text(encoding="utf-8")
    assert "SQLModel" in src
    assert "DATABASE_URL" in src
    assert "TinyDB is never the source of truth" in src or "not used for RFP" in src
    assert "PostgreSQL" in src or "Supabase" in src


@pytest.fixture()
def sql_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """SQLModel engine (sqlite stand-in for Postgres dialect in CI)."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'persist.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_ticket_rfp_metadata_and_key_aspects_roundtrip_sqlmodel(
    sql_client: TestClient,
) -> None:
    """Persist Ticket + CONTEXT metadata + DepartmentSection.key_aspects via SQLModel."""
    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    with pdf.open("rb") as fh:
        res = sql_client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == STATUS_INTAKE_COMPLETE
    ticket_id = body["ticket_id"]

    # --- Ticket row ---
    ticket = get_ticket(ticket_id)
    assert ticket is not None
    assert isinstance(ticket, RfpTicket)
    assert ticket.ticket_id == ticket_id
    assert ticket.status == STATUS_INTAKE_COMPLETE
    assert ticket.source_pdf_path  # raw PDF pointer
    assert ticket.created_at and ticket.updated_at
    assert ticket.metadata_json
    assert "tinydb" not in (ticket.source_pdf_path or "").casefold()

    # --- RFP metadata (CONTEXT §2.3) ---
    meta = json.loads(ticket.metadata_json)
    for key in CONTEXT_META_KEYS:
        assert key in meta or key in RFP_METADATA_FIELDS
    assert meta.get("client_name")
    assert "Sunset Bay" in (meta.get("client_name") or "")
    assert meta.get("location")
    assert meta.get("service_type") or meta.get("scope")
    assert meta.get("deadline")
    # departments_needed on ticket
    depts = json.loads(ticket.departments_needed_json or "[]")
    assert set(depts) >= {"marketing", "operaciones", "procurement", "training"}

    # Reload via Session to prove SQLModel table read (not an in-memory dict store)
    from services.api.database import get_engine

    with Session(get_engine()) as session:
        row = session.get(RfpTicket, ticket_id)
        assert row is not None
        assert row.metadata_json == ticket.metadata_json
        section_rows = session.exec(
            select(RfpDepartmentSection).where(
                RfpDepartmentSection.ticket_id == ticket_id
            )
        ).all()
        assert section_rows
        for sec in section_rows:
            aspects = json.loads(sec.key_aspects_json or "[]")
            assert isinstance(aspects, list) and aspects, sec.department_id
            assert sec.department_id in {
                "marketing",
                "operaciones",
                "procurement",
                "training",
            }

    # --- API surface exposes persisted entities ---
    detail = ticket_to_dict(ticket)
    assert detail["metadata"]["client_name"]
    assert detail["department_sections"]
    assert all(s["key_aspects"] for s in detail["department_sections"])
    assert detail["sections"]


def test_key_aspects_not_stored_in_legacy_tinydb_auth_file(sql_client: TestClient) -> None:
    """RFP Ticket / key_aspects must not leak into TinyDB auth.json."""
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        body = sql_client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
        ).json()
    ticket_id = body["ticket_id"]
    sections = list_sections(ticket_id)
    assert sections
    assert "training" not in {s.department_id for s in sections}

    auth = REPO / "data" / "auth.json"
    if auth.is_file():
        raw = auth.read_text(encoding="utf-8", errors="ignore")
        assert ticket_id not in raw
        assert "Andes Tech" not in raw
        assert "key_aspects" not in raw or ticket_id not in raw


def test_production_engine_url_env_contract() -> None:
    """Documented contract: DATABASE_URL drives SQLModel engine for Supabase."""
    src = (REPO / "services" / "api" / "database.py").read_text(encoding="utf-8")
    assert "def database_url" in src
    assert "def get_engine" in src
    assert "create_engine" in src
    # RFP create_db_and_tables registers models
    assert "services.rfp" in src or "rfp" in src.casefold()
