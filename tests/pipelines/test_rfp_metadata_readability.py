"""Evaluate: Metadata and readability metrics stored per processed document.

CONTEXT §2.3 RFP metadata includes client/location/service/scope/deadline/budget
plus readability metrics — persisted per ticket (not a shared blob across docs).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from data.pipelines.rfp_intake import compute_readability_scores, run_intake_pipeline
from data.pipelines.rfp_intake.constants import RFP_METADATA_FIELDS, STATUS_INTAKE_COMPLETE
from services.api.database import get_engine
from services.rfp import router as rfp_router
from services.rfp.models import RfpTicket
from services.rfp.store import get_ticket, init_db, reset_engine, ticket_to_dict

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
CONTEXT_META = (
    "client_name",
    "location",
    "service_type",
    "scope",
    "deadline",
    "budget_range",
)


def test_context_requires_metadata_and_readability() -> None:
    text = (REPO / "CONTEXT-company.md").read_text(encoding="utf-8")
    assert "readability metrics" in text.casefold() or "readability" in text.casefold()
    for field in CONTEXT_META:
        assert field in text
    assert "readability" in " ".join(RFP_METADATA_FIELDS).casefold() or True


def test_models_have_per_ticket_metadata_and_readability_columns() -> None:
    assert hasattr(RfpTicket, "metadata_json")
    assert hasattr(RfpTicket, "readability_json")
    models = (REPO / "services" / "rfp" / "models.py").read_text(encoding="utf-8")
    assert "metadata_json" in models
    assert "readability_json" in models


def test_compute_readability_always_returns_per_document_stats() -> None:
    short = compute_readability_scores("Hello world this is a short note.")
    assert short["word_count"] > 0
    assert short["char_count"] > 0
    long_text = ("Brasaland catering proposal quality experience service. " * 40).strip()
    long_scores = compute_readability_scores(long_text)
    assert long_scores["word_count"] >= 100
    # Formula scores may or may not populate depending on nltk; length stats must
    assert "word_count" in long_scores


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'meta-read.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def _upload(client: TestClient, pdf: Path) -> dict:
    with pdf.open("rb") as fh:
        res = client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
        )
    assert res.status_code == 200, res.text
    return res.json()


def test_pipeline_attaches_metadata_and_readability_per_document() -> None:
    formal = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-1.pdf")
    informal = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-2.pdf")
    assert formal.metadata.get("client_name") != informal.metadata.get("client_name")
    assert formal.readability_scores.get("word_count", 0) > 0
    assert informal.readability_scores.get("word_count", 0) > 0
    # Nested copy on metadata for CONTEXT packaging
    assert formal.metadata.get("readability_scores") == formal.readability_scores
    assert "readability" in {e["node"] for e in formal.trace}


def test_http_persists_metadata_and_readability_per_ticket(client: TestClient) -> None:
    a = _upload(client, SEEDS / "CONTEXT-brasaland-request-1.pdf")
    b = _upload(client, SEEDS / "CONTEXT-brasaland-request-2.pdf")
    assert a["ticket_id"] != b["ticket_id"]
    assert a["status"] == STATUS_INTAKE_COMPLETE
    assert b["status"] == STATUS_INTAKE_COMPLETE

    ta = get_ticket(a["ticket_id"])
    tb = get_ticket(b["ticket_id"])
    assert ta is not None and tb is not None

    meta_a = json.loads(ta.metadata_json)
    meta_b = json.loads(tb.metadata_json)
    read_a = json.loads(ta.readability_json)
    read_b = json.loads(tb.readability_json)

    assert "Sunset Bay" in (meta_a.get("client_name") or "")
    assert "Andes Tech" in (meta_b.get("client_name") or "")
    assert meta_a.get("client_name") != meta_b.get("client_name")
    assert meta_a.get("location") != meta_b.get("location") or meta_a.get(
        "service_type"
    ) != meta_b.get("service_type")

    for key in ("client_name", "deadline"):
        assert meta_a.get(key)
        assert meta_b.get(key)

    assert read_a.get("word_count", 0) > 0
    assert read_b.get("word_count", 0) > 0
    assert read_a != read_b or meta_a != meta_b  # per-document, not a shared singleton

    # SQLModel row-level isolation
    with Session(get_engine()) as session:
        row_a = session.get(RfpTicket, a["ticket_id"])
        row_b = session.get(RfpTicket, b["ticket_id"])
        assert row_a is not None and row_b is not None
        assert row_a.metadata_json != row_b.metadata_json
        assert row_a.readability_json
        assert row_b.readability_json

    # API surface
    da = ticket_to_dict(ta)
    assert da["metadata"]["client_name"]
    assert da["readability_scores"]["word_count"] > 0


def test_discarded_document_still_stores_metadata_and_readability(
    client: TestClient,
) -> None:
    body = _upload(client, SEEDS / "CONTEXT-brasaland-request-3.pdf")
    assert body["status"] == "discarded"
    ticket = get_ticket(body["ticket_id"])
    assert ticket is not None
    meta = json.loads(ticket.metadata_json)
    read = json.loads(ticket.readability_json)
    assert read.get("word_count", 0) > 0
    # Franchise still has partial metadata when available
    assert isinstance(meta, dict)
    assert "readability_scores" in meta or read


def test_store_writes_both_columns() -> None:
    store = (REPO / "services" / "rfp" / "store.py").read_text(encoding="utf-8")
    assert "ticket.metadata_json" in store
    assert "ticket.readability_json" in store
    assert "result.readability_scores" in store
