"""Part 1 RFP intake — curriculum PDFs from rfp-requests/brasaland/."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake import run_intake_pipeline
from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
    STATUS_DISCARDED,
    STATUS_INTAKE_COMPLETE,
)
from services.rfp import router as rfp_router

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db = tmp_path / "rfp.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    from services.rfp.store import init_db, reset_engine

    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_pipeline_seed_1_sunset_bay_all_departments() -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    assert pdf.is_file()
    result = run_intake_pipeline(pdf_path=pdf)
    assert result.status == STATUS_INTAKE_COMPLETE
    assert "Sunset Bay" in (result.metadata.get("client_name") or "")
    assert set(result.departments_needed) == {
        DEPARTMENT_MARKETING,
        DEPARTMENT_OPERACIONES,
        DEPARTMENT_PROCUREMENT,
        DEPARTMENT_TRAINING,
    }
    assert result.requires_ceo_approval is True
    assert DEPARTMENT_TRAINING in result.sections


def test_pipeline_seed_2_andes_without_training() -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    result = run_intake_pipeline(pdf_path=pdf)
    assert result.status == STATUS_INTAKE_COMPLETE
    assert "Andes Tech" in (result.metadata.get("client_name") or "")
    assert set(result.departments_needed) == {
        DEPARTMENT_MARKETING,
        DEPARTMENT_OPERACIONES,
        DEPARTMENT_PROCUREMENT,
    }
    assert DEPARTMENT_TRAINING not in result.departments_needed
    assert result.requires_ceo_approval is False


def test_pipeline_seed_3_franchise_discarded() -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-3.pdf"
    result = run_intake_pipeline(pdf_path=pdf)
    assert result.status == STATUS_DISCARDED
    assert result.discard_reason
    assert result.discard_rule_id
    assert result.departments_needed == []
    assert result.intake_summary == result.discard_reason
    assert "department_worker" not in {e["node"] for e in result.trace}


def test_http_ticket_upload_seed_pdfs(client: TestClient) -> None:
    for name, expected in (
        ("CONTEXT-brasaland-request-1.pdf", STATUS_INTAKE_COMPLETE),
        ("CONTEXT-brasaland-request-2.pdf", STATUS_INTAKE_COMPLETE),
        ("CONTEXT-brasaland-request-3.pdf", STATUS_DISCARDED),
    ):
        path = SEEDS / name
        with path.open("rb") as fh:
            res = client.post(
                "/rfp/tickets",
                files={"file": (name, fh, "application/pdf")},
            )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == expected, name
        assert "ticket_id" in body
        detail = client.get(f"/rfp/tickets/{body['ticket_id']}")
        assert detail.status_code == 200
        assert detail.json()["status"] == expected
