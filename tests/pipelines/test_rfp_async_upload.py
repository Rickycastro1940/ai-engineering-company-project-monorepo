"""Evaluate: Upload is async — quick response + background pipeline + pollable status.

Default production path (no RFP_INTAKE_SYNC):
1. POST /rfp/tickets returns quickly with status=analyzing (terminal=false)
2. Pipeline runs via FastAPI BackgroundTasks
3. GET /rfp/tickets/{id} is pollable until intake_complete | discarded

RFP_INTAKE_SYNC is opt-in for tests/smoke only — not the default async contract.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake.constants import (
    P1_TERMINAL,
    STATUS_ANALYZING,
    STATUS_DISCARDED,
    STATUS_INTAKE_COMPLETE,
)
from services.rfp import router as rfp_router
from services.rfp import routes as rfp_routes
from services.rfp.store import get_ticket, init_db, reset_engine

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
UI = REPO / "uis" / "backoffice" / "rfp-upload.html"


@pytest.fixture()
def async_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Default async mode: capture BackgroundTasks instead of running them inline."""
    monkeypatch.delenv("RFP_INTAKE_SYNC", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'async-upload.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    reset_engine()
    init_db()

    scheduled: list[tuple] = []

    def _capture(self, func, *args, **kwargs):  # noqa: ANN001
        scheduled.append((func, args, kwargs))

    monkeypatch.setattr(BackgroundTasks, "add_task", _capture)

    app = FastAPI()
    app.include_router(rfp_router)
    client = TestClient(app)
    client.scheduled_jobs = scheduled  # type: ignore[attr-defined]
    return client


def test_routes_default_async_uses_background_tasks() -> None:
    src = (REPO / "services" / "rfp" / "routes.py").read_text(encoding="utf-8")
    assert "BackgroundTasks" in src
    assert "background_tasks.add_task" in src
    assert "_run_pipeline_job" in src
    assert "STATUS_ANALYZING" in src
    # Sync is gated — not the default return path
    assert "_sync_mode" in src
    assert 'RFP_INTAKE_SYNC' in src


def test_ui_polls_ticket_status_until_terminal() -> None:
    src = UI.read_text(encoding="utf-8")
    assert "async function pollTicket" in src
    assert "/rfp/tickets/${ticketId}" in src or "/rfp/tickets/" in src
    assert "intake_complete" in src
    assert "discarded" in src
    assert "analyzing" in src
    assert "pollTicket(ticketId)" in src


def test_upload_returns_quickly_with_analyzing(async_client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    t0 = time.perf_counter()
    with pdf.open("rb") as fh:
        res = async_client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
        )
    elapsed = time.perf_counter() - t0
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == STATUS_ANALYZING
    assert body.get("terminal") is False
    assert "ticket_id" in body
    # Must not wait for full intake (formal PDF pipeline is >> tens of ms when run)
    assert elapsed < 2.0, f"upload too slow for async contract: {elapsed:.3f}s"
    # Background job scheduled, not executed yet
    assert len(async_client.scheduled_jobs) == 1  # type: ignore[attr-defined]
    ticket = get_ticket(body["ticket_id"])
    assert ticket is not None
    assert ticket.status == STATUS_ANALYZING


def test_status_pollable_while_analyzing_then_terminal(
    async_client: TestClient,
) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        created = async_client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
        ).json()
    ticket_id = created["ticket_id"]

    # Poll while background job has not run
    mid = async_client.get(f"/rfp/tickets/{ticket_id}")
    assert mid.status_code == 200
    mid_body = mid.json()
    assert mid_body["status"] == STATUS_ANALYZING
    assert mid_body.get("terminal") is False

    # Run captured background pipeline
    func, args, kwargs = async_client.scheduled_jobs[0]  # type: ignore[attr-defined]
    assert func is rfp_routes._run_pipeline_job or func.__name__ == "_run_pipeline_job"
    func(*args, **kwargs)

    # Poll again — terminal Part 1 status
    final = async_client.get(f"/rfp/tickets/{ticket_id}")
    assert final.status_code == 200
    body = final.json()
    assert body["status"] == STATUS_INTAKE_COMPLETE
    assert body["terminal"] is True
    assert body["status"] in P1_TERMINAL


def test_async_discard_also_pollable(async_client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-3.pdf"
    with pdf.open("rb") as fh:
        created = async_client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
        ).json()
    assert created["status"] == STATUS_ANALYZING
    func, args, kwargs = async_client.scheduled_jobs[0]  # type: ignore[attr-defined]
    func(*args, **kwargs)
    polled = async_client.get(f"/rfp/tickets/{created['ticket_id']}").json()
    assert polled["status"] == STATUS_DISCARDED
    assert polled["terminal"] is True
    assert polled.get("discard_reason")


def test_sync_mode_is_opt_in_not_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RFP_INTAKE_SYNC", raising=False)
    assert rfp_routes._sync_mode() is False
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    assert rfp_routes._sync_mode() is True


def test_upload_alias_also_async(async_client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    with pdf.open("rb") as fh:
        res = async_client.post(
            "/rfp/upload",
            files={"file": (pdf.name, fh, "application/pdf")},
        )
    assert res.status_code == 200
    assert res.json()["status"] == STATUS_ANALYZING
    assert len(async_client.scheduled_jobs) >= 1  # type: ignore[attr-defined]
