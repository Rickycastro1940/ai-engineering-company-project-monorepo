"""Evaluate: Intake interface (ticket mode) checklist.

1. UI in uis/backoffice — upload PDF RFP → one ticket per upload
2. PDF stored under data/raw/; ticket status starts as analyzing
3. Upload returns quickly; pipeline async; UI polls analyzing →
   intake_complete | discarded
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake.constants import (
    STATUS_ANALYZING,
    STATUS_DISCARDED,
    STATUS_INTAKE_COMPLETE,
)
from services.rfp import router as rfp_router
from services.rfp import routes as rfp_routes
from services.rfp.store import get_ticket, init_db, reset_engine

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
BACKOFFICE = REPO / "uis" / "backoffice"
RAW_RFP = REPO / "data" / "raw" / "rfp"


def test_backoffice_ui_exists_with_upload_and_poll() -> None:
    page = BACKOFFICE / "rfp-upload.html"
    assert page.is_file()
    src = page.read_text(encoding="utf-8")
    assert "POST /rfp/tickets" in src or "/rfp/tickets" in src
    assert "poll" in src.casefold() or "GET /rfp/tickets" in src or "/rfp/tickets/${" in src
    assert "intake_complete" in src
    assert "discarded" in src
    assert "analyzing" in src


def test_agent_app_serves_backoffice_rfp_page() -> None:
    app_src = (REPO / "services" / "agent" / "app.py").read_text(encoding="utf-8")
    assert "uis" in app_src and "backoffice" in app_src
    assert "rfp-upload" in app_src or "StaticFiles" in app_src


@pytest.fixture()
def async_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Client with sync intake disabled; background tasks captured (not auto-run)."""
    monkeypatch.delenv("RFP_INTAKE_SYNC", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ticket-mode.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    reset_engine()
    init_db()

    scheduled: list[tuple] = []

    def _capture_add_task(self, func, *args, **kwargs):  # noqa: ANN001
        scheduled.append((func, args, kwargs))

    monkeypatch.setattr(BackgroundTasks, "add_task", _capture_add_task)

    app = FastAPI()
    app.include_router(rfp_router)
    client = TestClient(app)
    client.scheduled_jobs = scheduled  # type: ignore[attr-defined]
    return client


def test_upload_creates_one_analyzing_ticket_and_stores_pdf(
    async_client: TestClient,
) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    with pdf.open("rb") as fh:
        res = async_client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == STATUS_ANALYZING
    assert body.get("terminal") is False
    ticket_id = body["ticket_id"]
    assert ticket_id

    ticket = get_ticket(ticket_id)
    assert ticket is not None
    assert ticket.status == STATUS_ANALYZING

    store = RAW_RFP / ticket_id
    assert store.is_dir()
    assert any(store.glob("*.pdf")), f"expected PDF under data/raw/rfp/{ticket_id}/"

    jobs = async_client.scheduled_jobs  # type: ignore[attr-defined]
    assert len(jobs) == 1


def test_async_pipeline_reaches_intake_complete_or_discarded(
    async_client: TestClient,
) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-3.pdf"
    with pdf.open("rb") as fh:
        res = async_client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
        )
    ticket_id = res.json()["ticket_id"]
    func, args, kwargs = async_client.scheduled_jobs[0]  # type: ignore[attr-defined]
    func(*args, **kwargs)

    polled = async_client.get(f"/rfp/tickets/{ticket_id}")
    assert polled.status_code == 200
    final = polled.json()
    assert final["status"] == STATUS_DISCARDED
    assert final["terminal"] is True
    assert final["status"] in {STATUS_INTAKE_COMPLETE, STATUS_DISCARDED}


def test_one_upload_one_ticket(async_client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    ids: list[str] = []
    for _ in range(2):
        with pdf.open("rb") as fh:
            res = async_client.post(
                "/rfp/tickets",
                files={"file": (pdf.name, fh, "application/pdf")},
            )
        ids.append(res.json()["ticket_id"])
    assert ids[0] != ids[1]
    assert len(async_client.scheduled_jobs) == 2  # type: ignore[attr-defined]


def test_raw_dir_is_under_data_raw() -> None:
    assert rfp_routes.RAW_DIR == REPO / "data" / "raw" / "rfp"
    assert "data" in rfp_routes.RAW_DIR.parts
    assert "raw" in rfp_routes.RAW_DIR.parts
