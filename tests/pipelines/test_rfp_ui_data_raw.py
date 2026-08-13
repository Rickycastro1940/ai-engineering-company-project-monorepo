"""Evaluate: Uploaded PDFs land under data/raw as part of intake; UI drives upload.

CONTEXT §2.4 / §4:
- Uploaded PDFs provided via uis/backoffice; stored under data/raw/ as a runtime
  artifact of intake (not pre-seeded inventory in the repo).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake.constants import STATUS_ANALYZING, STATUS_INTAKE_COMPLETE
from services.rfp import routes as rfp_routes
from services.rfp.store import get_ticket, init_db, reset_engine

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
BACKOFFICE = REPO / "uis" / "backoffice"
RAW_RFP = REPO / "data" / "raw" / "rfp"
UI_PAGE = BACKOFFICE / "rfp-upload.html"


@pytest.fixture()
def ui_app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Full agent app: serves rfp-upload.html and /rfp/* (UI-driven intake)."""
    # Keep runtime artifacts under the real data/raw/rfp tree (CONTEXT requirement),
    # but isolate DB to tmp.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'raw-ui.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    from services.agent.app import app

    return TestClient(app)


def test_context_requires_ui_uploads_to_data_raw() -> None:
    context = (REPO / "CONTEXT-company.md").read_text(encoding="utf-8")
    assert "uis/backoffice" in context
    assert "data/raw/" in context
    assert "runtime artifact" in context.casefold() or "stored under `data/raw/`" in context


def test_ui_page_exists_and_posts_to_rfp_tickets() -> None:
    assert UI_PAGE.is_file()
    src = UI_PAGE.read_text(encoding="utf-8")
    assert "fetch('/rfp/tickets'" in src or 'fetch("/rfp/tickets"' in src or "/rfp/tickets" in src
    assert "FormData" in src
    assert "file" in src
    assert "analyzing" in src
    assert "intake_complete" in src
    assert "discarded" in src


def test_agent_app_serves_backoffice_ui() -> None:
    app_src = (REPO / "services" / "agent" / "app.py").read_text(encoding="utf-8")
    assert "uis" in app_src and "backoffice" in app_src
    assert "StaticFiles" in app_src
    assert "rfp_router" in app_src or "services.rfp" in app_src


def test_raw_dir_contract_under_data_raw() -> None:
    assert rfp_routes.RAW_DIR == RAW_RFP
    assert rfp_routes.RAW_DIR.parts[-3:] == ("data", "raw", "rfp")
    assert (RAW_RFP / ".gitkeep").is_file() or RAW_RFP.is_dir()
    # Curriculum seeds are NOT inventory under data/raw
    assert not (RAW_RFP / "CONTEXT-brasaland-request-1.pdf").is_file()
    assert (SEEDS / "CONTEXT-brasaland-request-1.pdf").is_file()


def test_ui_driven_upload_writes_pdf_under_data_raw(ui_app_client: TestClient) -> None:
    """UI path: GET page → POST /rfp/tickets → PDF at data/raw/rfp/<ticket_id>/."""
    page = ui_app_client.get("/rfp-upload.html")
    assert page.status_code == 200
    assert "RFP Intake" in page.text or "rfp" in page.text.casefold()

    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    original = pdf.read_bytes()
    with pdf.open("rb") as fh:
        res = ui_app_client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
            data={"title": "UI-driven raw persist check"},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    ticket_id = body["ticket_id"]
    assert ticket_id

    store_dir = RAW_RFP / ticket_id
    assert store_dir.is_dir(), f"missing {store_dir}"
    pdfs = list(store_dir.glob("*.pdf"))
    assert pdfs, f"expected uploaded PDF under data/raw/rfp/{ticket_id}/"
    saved = pdfs[0]
    assert saved.read_bytes() == original

    # Relative path under data/raw must be recorded on the ticket
    ticket = get_ticket(ticket_id)
    assert ticket is not None
    assert ticket.source_pdf_path
    assert "data/raw" in ticket.source_pdf_path.replace("\\", "/")
    assert ticket_id in ticket.source_pdf_path
    assert body["status"] in {STATUS_INTAKE_COMPLETE, STATUS_ANALYZING}


def test_ui_upload_all_three_seeds_land_under_data_raw(ui_app_client: TestClient) -> None:
    for name in (
        "CONTEXT-brasaland-request-1.pdf",
        "CONTEXT-brasaland-request-2.pdf",
        "CONTEXT-brasaland-request-3.pdf",
    ):
        pdf = SEEDS / name
        with pdf.open("rb") as fh:
            body = ui_app_client.post(
                "/rfp/tickets",
                files={"file": (name, fh, "application/pdf")},
            ).json()
        ticket_id = body["ticket_id"]
        store = RAW_RFP / ticket_id
        assert store.is_dir()
        assert any(store.glob("*.pdf")), name
        # Discarded tickets still keep the raw upload artifact
        ticket = get_ticket(ticket_id)
        assert ticket is not None
        assert ticket.ticket_id == ticket_id
        assert ticket.source_pdf_path
        assert "data/raw" in ticket.source_pdf_path.replace("\\", "/")


def test_routes_persist_upload_before_pipeline() -> None:
    routes = (REPO / "services" / "rfp" / "routes.py").read_text(encoding="utf-8")
    assert "_persist_upload" in routes
    assert 'RAW_DIR = REPO_ROOT / "data" / "raw" / "rfp"' in routes or "data" in routes
    assert "_persist_upload(ticket.ticket_id" in routes
    # Persist happens in create_ticket before background/sync job
    create_idx = routes.index("async def create_ticket")
    persist_idx = routes.index("_persist_upload(ticket.ticket_id", create_idx)
    job_idx = routes.index("_run_pipeline_job", persist_idx)
    assert persist_idx < job_idx
