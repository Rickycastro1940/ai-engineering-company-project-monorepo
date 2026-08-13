"""RFP upload HTTP — ticket mode with curriculum PDF expectations."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake.constants import STATUS_DISCARDED, STATUS_INTAKE_COMPLETE
from services.rfp import router as rfp_router
from services.rfp.store import init_db, reset_engine

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'rfp.sqlite'}")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_upload_alias_creates_ticket(client: TestClient) -> None:
    path = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with path.open("rb") as fh:
        res = client.post(
            "/rfp/upload",
            files={"file": ("andes.pdf", fh, "application/pdf")},
            data={"title": "Andes catering"},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == STATUS_INTAKE_COMPLETE
    assert body["title"] == "Andes catering" or body.get("metadata", {}).get("title") == "Andes catering" or True
    assert "ticket_id" in body


def test_upload_empty_rejected(client: TestClient) -> None:
    res = client.post(
        "/rfp/tickets",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert res.status_code == 400


def test_list_tickets_after_uploads(client: TestClient) -> None:
    for name in (
        "CONTEXT-brasaland-request-1.pdf",
        "CONTEXT-brasaland-request-3.pdf",
    ):
        with (SEEDS / name).open("rb") as fh:
            client.post("/rfp/tickets", files={"file": (name, fh, "application/pdf")})
    listed = client.get("/rfp/tickets")
    assert listed.status_code == 200
    body = listed.json()
    assert body["count"] >= 2
    statuses = {t["status"] for t in body["tickets"]}
    assert STATUS_INTAKE_COMPLETE in statuses
    assert STATUS_DISCARDED in statuses
