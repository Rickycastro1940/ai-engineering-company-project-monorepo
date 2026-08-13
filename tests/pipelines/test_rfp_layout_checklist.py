"""Evaluate: RFP monorepo layout + SQLModel persistence checklist.

Non-negotiable:
1. No new API service — extend services/, routers call data/pipelines/
2. Pipeline under data/pipelines/rfp_intake/ (not CX agent graph)
3. Standalone CLIs in scripts/ (not a second HTTP API)
4. Ticket / RFP metadata / DepartmentSection.key_aspects in SQLModel
   (Postgres via DATABASE_URL) — TinyDB not acceptable for RFP data
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from data.pipelines.rfp_intake.constants import STATUS_INTAKE_COMPLETE
from services.agent.graph import REQUIRED_NODES
from services.rfp import router as rfp_router
from services.rfp.models import RfpDepartmentSection, RfpTicket
from services.rfp.store import (
    get_ticket,
    init_db,
    list_sections,
    reset_engine,
    ticket_to_dict,
)

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"


def test_no_new_api_service_router_calls_pipeline() -> None:
    """HTTP lives under services/ and delegates to data/pipelines/rfp_intake."""
    routes_src = (REPO / "services" / "rfp" / "routes.py").read_text(encoding="utf-8")
    assert "from data.pipelines.rfp_intake" in routes_src
    assert "run_intake_from_bytes" in routes_src
    # Mounted on existing agent app — not a separate uvicorn entrypoint package.
    agent_app = (REPO / "services" / "agent" / "app.py").read_text(encoding="utf-8")
    assert "from services.rfp import router" in agent_app
    assert "include_router(rfp_router)" in agent_app
    # No dedicated services/rfp_api app module.
    assert not (REPO / "services" / "rfp_api").exists()


def test_pipeline_lives_under_data_pipelines_rfp_intake_not_cx_graph() -> None:
    assert (REPO / "data" / "pipelines" / "rfp_intake" / "__init__.py").is_file()
    # CX support-agent graph must not register RFP nodes.
    for name in REQUIRED_NODES:
        assert "rfp" not in name.casefold()
    graph_src = (REPO / "services" / "agent" / "graph.py").read_text(encoding="utf-8")
    assert "rfp_intake" not in graph_src
    assert "department_worker" not in graph_src


def test_standalone_cli_in_scripts_not_second_http_api() -> None:
    cli = REPO / "scripts" / "rfp_intake_smoke.py"
    assert cli.is_file()
    src = cli.read_text(encoding="utf-8")
    assert "run_intake_pipeline" in src
    assert "uvicorn" not in src
    assert "FastAPI" not in src


def test_rfp_persistence_uses_sqlmodel_not_tinydb() -> None:
    store_src = (REPO / "services" / "rfp" / "store.py").read_text(encoding="utf-8")
    models_src = (REPO / "services" / "rfp" / "models.py").read_text(encoding="utf-8")
    assert "tinydb" not in store_src.casefold()
    assert "TinyDB" not in store_src
    assert "sqlmodel" in store_src.casefold()
    assert "class RfpTicket" in models_src
    assert "class RfpDepartmentSection" in models_src
    assert "key_aspects" in models_src

    # TinyDB remains only on the shared database module for legacy auth.
    db_src = (REPO / "services" / "api" / "database.py").read_text(encoding="utf-8")
    assert "TinyDB is never the source of truth" in db_src or "not used for RFP" in db_src


def test_department_section_key_aspects_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'layout.sqlite'}")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()

    app = FastAPI()
    app.include_router(rfp_router)
    client = TestClient(app)

    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    with pdf.open("rb") as fh:
        res = client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == STATUS_INTAKE_COMPLETE
    ticket_id = body["ticket_id"]

    # Dedicated DepartmentSection rows with key_aspects
    sections = list_sections(ticket_id)
    assert sections, "expected rfp_department_sections rows"
    assert all(json_loads_aspects(s) for s in sections)
    assert {s.department_id for s in sections} >= {
        "marketing",
        "operaciones",
        "procurement",
        "training",
    }

    detail = ticket_to_dict(get_ticket(ticket_id))  # type: ignore[arg-type]
    assert detail["metadata"].get("client_name")
    assert detail["department_sections"]
    assert detail["department_sections"][0]["key_aspects"]


def json_loads_aspects(section: RfpDepartmentSection) -> list:
    import json

    aspects = json.loads(section.key_aspects_json or "[]")
    assert isinstance(aspects, list) and aspects
    return aspects
