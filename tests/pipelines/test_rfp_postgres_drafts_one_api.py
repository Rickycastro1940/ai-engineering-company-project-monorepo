"""Evaluate: Part 2 drafts + evaluation_results persist in PostgreSQL.

Still one backend API under services/ — no second HTTP service.

CONTEXT §2.3: Ticket / DepartmentSection (draft_content, evaluation_results)
live in PostgreSQL via SQLModel. TinyDB / JSON files are not the source of truth.

CONTEXT §2.4: extend the existing backend under services/ — no new API process.
Part 2 HTTP is POST /rfp/tickets/{id}/generate-response on services/rfp.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlmodel import SQLModel, Session, select

from data.pipelines.rfp_intake.constants import (
    STATUS_INTAKE_COMPLETE,
    STATUS_WAITING_FOR_APPROVAL,
)
from services.api.database import database_url, get_engine
from services.rfp import router as rfp_router
from services.rfp.models import RfpDepartmentSection, RfpTicket
from services.rfp.routes import router as rfp_api_router
from services.rfp.store import (
    get_ticket,
    init_db,
    list_sections,
    reset_engine,
    ticket_to_dict,
)

REPO = Path(__file__).resolve().parents[2]
CONTEXT = REPO / "CONTEXT-company.md"
SERVICES_RFP = REPO / "services" / "rfp"
PIPELINE_RESPONSE = REPO / "data" / "pipelines" / "rfp_response"
SEEDS = REPO / "rfp-requests" / "brasaland"

FORBIDDEN_SECOND_RFP_HTTP = (
    "services/rfp_api",
    "services/rfp_service",
    "services/rfp_intake_api",
    "services/rfp_http",
    "services/rfp_server",
    "services/rfp_response",
    "services/rfp_response_api",
    "services/rfp_generation",
    "services/rfp_eval",
)

HTTP_FRAMEWORK_TOKENS = ("fastapi", "uvicorn", "starlette", "APIRouter", "Flask")


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _context_section(heading: str, next_heading: str) -> str:
    text = CONTEXT.read_text(encoding="utf-8")
    return text.split(heading)[1].split(next_heading)[0]


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'p2-persist.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_context_requires_postgres_drafts_evals_and_one_services_api() -> None:
    entities = _context_section("### 2.3", "### 2.4")
    assert "PostgreSQL" in entities
    assert "SQLModel" in entities
    assert "TinyDB" in entities
    assert "JSON files are not the source of truth" in entities
    assert "draft_content" in entities
    assert "evaluation_results" in entities

    layout = _context_section("### 2.4", "## 3.")
    assert "no new API process" in layout
    assert "`services/`" in layout or "services/" in layout


def test_department_section_sqlmodel_columns_include_drafts_and_evals() -> None:
    assert issubclass(RfpTicket, SQLModel)
    assert issubclass(RfpDepartmentSection, SQLModel)
    assert RfpDepartmentSection.__tablename__ == "rfp_department_sections"
    for col in ("draft_content", "evaluation_results_json", "department_id", "ticket_id"):
        assert hasattr(RfpDepartmentSection, col)
    models_src = (SERVICES_RFP / "models.py").read_text(encoding="utf-8")
    assert "PostgreSQL" in models_src or "Postgres" in models_src
    assert "TinyDB" not in models_src


def test_part2_store_writes_via_sqlmodel_session_not_tinydb_or_json_files() -> None:
    store_src = (SERVICES_RFP / "store.py").read_text(encoding="utf-8")
    assert "from sqlmodel import Session" in store_src
    assert "get_engine" in store_src
    assert "from services.api.database import" in store_src
    assert "def save_response_result" in store_src
    assert "draft_content" in store_src
    assert "evaluation_results_json" in store_src
    assert "tinydb" not in store_src.casefold()
    assert "TinyDB" not in store_src
    for banned in ("drafts.json", "evaluation_results.json", "Path.write_text", "tinydb"):
        assert banned not in store_src


def test_production_database_url_is_postgresql(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_engine()
    monkeypatch.delenv("RFP_ALLOW_SQLITE", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:pass@db.example.supabase.co:5432/postgres",
    )
    url = database_url()
    assert url.startswith("postgresql"), url
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        database_url()


def test_no_second_rfp_http_service_for_part2() -> None:
    for rel in FORBIDDEN_SECOND_RFP_HTTP:
        assert not (REPO / rel).exists(), f"Forbidden second API package: {rel}"
    assert not (SERVICES_RFP / "app.py").exists()
    assert not (SERVICES_RFP / "main.py").exists()
    assert not (PIPELINE_RESPONSE / "app.py").exists()
    assert not (PIPELINE_RESPONSE / "main.py").exists()


def test_canonical_host_mounts_same_rfp_router() -> None:
    agent_app = (REPO / "services" / "agent" / "app.py").read_text(encoding="utf-8")
    assert "from services.rfp import router" in agent_app
    assert "include_router(rfp_router)" in agent_app
    assert "same process" in agent_app.casefold() or "same API" in agent_app.casefold()
    reporting = REPO / "services" / "reporting" / "main.py"
    if reporting.is_file():
        src = reporting.read_text(encoding="utf-8")
        if "rfp_router" in src:
            assert "from services.rfp import router" in src


def test_generate_response_lives_on_existing_services_rfp_router() -> None:
    assert rfp_api_router.prefix == "/rfp"
    paths = {getattr(route, "path", "") for route in rfp_api_router.routes}
    assert "/rfp/tickets" in paths
    assert "/rfp/tickets/{ticket_id}" in paths
    assert "/rfp/tickets/{ticket_id}/generate-response" in paths
    routes_src = (SERVICES_RFP / "routes.py").read_text(encoding="utf-8")
    assert "from data.pipelines.rfp_response import" in routes_src
    assert "run_response_for_ticket" in routes_src
    assert "save_response_result" in routes_src
    tree = ast.parse(routes_src)
    defs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    for banned in (
        "run_response_pipeline",
        "generate_department_draft",
        "evaluate_section",
        "run_section_loop",
    ):
        assert banned not in defs


def test_part2_pipeline_package_has_no_http_framework() -> None:
    assert PIPELINE_RESPONSE.is_dir()
    for path in _py_files(PIPELINE_RESPONSE):
        src = path.read_text(encoding="utf-8")
        lower = src.casefold()
        for token in HTTP_FRAMEWORK_TOKENS:
            assert token.casefold() not in lower, (
                f"{path.relative_to(REPO)} must not reference HTTP framework {token!r}"
            )


def test_part2_cli_is_scripts_not_a_second_http_api() -> None:
    cli = REPO / "scripts" / "rfp_response_smoke.py"
    assert cli.is_file()
    src = cli.read_text(encoding="utf-8")
    assert "run_response_pipeline" in src
    assert "FastAPI" not in src
    assert "uvicorn" not in src
    assert "APIRouter" not in src


def test_http_generate_response_persists_drafts_and_evals_in_sqlmodel_tables(
    client: TestClient,
) -> None:
    """POST generate-response on the existing /rfp router; re-read via SQL Session."""
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    assert created["status"] == STATUS_INTAKE_COMPLETE
    ticket_id = created["ticket_id"]

    res = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == STATUS_WAITING_FOR_APPROVAL

    inspector = inspect(get_engine())
    assert "rfp_tickets" in inspector.get_table_names()
    assert "rfp_department_sections" in inspector.get_table_names()
    section_cols = {c["name"] for c in inspector.get_columns("rfp_department_sections")}
    assert "draft_content" in section_cols
    assert "evaluation_results_json" in section_cols

    with Session(get_engine()) as session:
        ticket_row = session.get(RfpTicket, ticket_id)
        assert ticket_row is not None
        assert ticket_row.status == STATUS_WAITING_FOR_APPROVAL
        rows = session.exec(
            select(RfpDepartmentSection).where(
                RfpDepartmentSection.ticket_id == ticket_id
            )
        ).all()
        assert rows
        for row in rows:
            assert (row.draft_content or "").strip(), row.department_id
            assert row.evaluation_results_json, row.department_id
            ev = json.loads(row.evaluation_results_json)
            assert isinstance(ev, dict)
            for dim in ("readability", "relevance", "compliance"):
                assert dim in ev, dim

    # Same backend GET — not a second service — reads the persisted SQL rows.
    detail = client.get(f"/rfp/tickets/{ticket_id}")
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["status"] == STATUS_WAITING_FOR_APPROVAL
    sections = payload["department_sections"]
    assert sections
    assert all(s.get("draft_content") for s in sections)
    assert all(s.get("evaluation_results") for s in sections)

    stored = ticket_to_dict(get_ticket(ticket_id))  # type: ignore[arg-type]
    assert stored["status"] == payload["status"]
    assert list_sections(ticket_id)


def test_persisted_drafts_do_not_leak_into_tinydb_auth_file(client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]
    res = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert res.status_code == 200, res.text

    auth = REPO / "data" / "auth.json"
    if auth.is_file():
        raw = auth.read_text(encoding="utf-8", errors="ignore")
        assert ticket_id not in raw
        for row in list_sections(ticket_id):
            snippet = (row.draft_content or "")[:80]
            if snippet.strip():
                assert snippet not in raw
