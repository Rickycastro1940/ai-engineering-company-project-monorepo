"""Evaluate: final results list per-department key_aspects + contacts.

Verifiable against CONTEXT-company.md §2.1 owners and §4 sample PDFs under
``rfp-requests/brasaland/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake import (
    build_final_department_results,
    convert_document_to_markdown,
    run_intake_pipeline,
)
from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_OWNERS,
    STATUS_DISCARDED,
    STATUS_INTAKE_COMPLETE,
)
from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_CEO_NAME,
    CONTEXT_DEPARTMENT_OWNERS,
    CONTEXT_SEED_EXPECTATIONS,
)
from services.rfp import router as rfp_router
from services.rfp.store import get_ticket, init_db, reset_engine, ticket_to_dict

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
CONTEXT = REPO / "CONTEXT-company.md"
UI = REPO / "uis" / "backoffice" / "rfp-upload.html"

ACCEPTED_SEEDS = (
    "CONTEXT-brasaland-request-1.pdf",
    "CONTEXT-brasaland-request-2.pdf",
)
ALL_SEEDS = ACCEPTED_SEEDS + ("CONTEXT-brasaland-request-3.pdf",)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'final.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_context_seed_pdfs_exist_and_are_referenced() -> None:
    text = CONTEXT.read_text(encoding="utf-8")
    for name in ALL_SEEDS:
        assert (SEEDS / name).is_file(), name
        assert name in text


def test_context_owners_match_constants() -> None:
    text = CONTEXT.read_text(encoding="utf-8")
    for dept_id, owner in CONTEXT_DEPARTMENT_OWNERS.items():
        assert owner in text
        assert DEPARTMENT_OWNERS[dept_id] == owner
    assert CONTEXT_CEO_NAME in text


@pytest.mark.parametrize("filename", ACCEPTED_SEEDS)
def test_final_results_list_key_aspects_and_contacts_per_department(
    filename: str,
) -> None:
    expected = CONTEXT_SEED_EXPECTATIONS[filename]
    result = run_intake_pipeline(pdf_path=SEEDS / filename)
    assert result.status == STATUS_INTAKE_COMPLETE

    finals = result.final_department_results
    assert finals, "final_department_results must list per-department rows"
    dept_rows = [r for r in finals if r["department_id"] != "ceo"]
    assert {r["department_id"] for r in dept_rows} == set(expected["departments"])

    for row in dept_rows:
        dept = row["department_id"]
        assert row["contact"] == expected["contacts"][dept]
        assert row["owner"] == CONTEXT_DEPARTMENT_OWNERS[dept]
        assert row["key_aspects"], f"{dept} missing key_aspects"
        joined = "\n".join(row["key_aspects"]).casefold()
        for signal in expected["aspect_signals"][dept]:
            assert signal.casefold() in joined, (
                f"{filename} / {dept}: expected aspect signal {signal!r} in {row['key_aspects']}"
            )

    # Contacts also appear in ask_whom (Sales-facing)
    owners = {a["owner"] for a in result.ask_whom}
    for dept in expected["departments"]:
        assert expected["contacts"][dept] in owners

    if expected.get("requires_ceo_approval"):
        ceo_rows = [r for r in finals if r["department_id"] == "ceo"]
        assert ceo_rows
        assert ceo_rows[0]["contact"] == CONTEXT_CEO_NAME
        assert any(a["owner"] == CONTEXT_CEO_NAME for a in result.ask_whom)
    else:
        assert all(r["department_id"] != "ceo" for r in finals)


@pytest.mark.parametrize("filename", ACCEPTED_SEEDS)
def test_aspect_signals_are_grounded_in_sample_pdf_text(filename: str) -> None:
    """Document-derived aspect signals must appear in the PDF extract (or CONTEXT rules)."""
    expected = CONTEXT_SEED_EXPECTATIONS[filename]
    markdown = convert_document_to_markdown(SEEDS / filename).casefold()
    assert expected["client_substr"].casefold() in markdown
    if expected.get("location_substr"):
        assert expected["location_substr"].casefold() in markdown

    result = run_intake_pipeline(pdf_path=SEEDS / filename)
    # Marketing / operaciones rows always name the client from the PDF
    for row in result.final_department_results:
        if row["department_id"] not in {"marketing", "operaciones"}:
            continue
        joined = "\n".join(row["key_aspects"]).casefold()
        assert expected["client_substr"].casefold() in joined

    # PDF-grounded numeric/name signals (skip pure CONTEXT-rule phrases)
    pdf_grounded = {
        "Sunset Bay",
        "Florida",
        "exclusiv",
        "60,000",
        "75,000",
        "signature",
        "Andes Tech",
        "Medellín",
        "220",
    }
    for dept, signals in expected["aspect_signals"].items():
        for signal in signals:
            if signal not in pdf_grounded:
                continue
            assert signal.casefold() in markdown, (
                f"{filename}: aspect signal {signal!r} for {dept} not found in PDF text"
            )


def test_franchise_seed_has_no_department_key_aspects_or_contacts() -> None:
    filename = "CONTEXT-brasaland-request-3.pdf"
    result = run_intake_pipeline(pdf_path=SEEDS / filename)
    assert result.status == STATUS_DISCARDED
    assert result.final_department_results == []
    assert result.sections == {}
    assert result.ask_whom == []
    assert result.departments_needed == []


def test_http_ticket_exposes_final_department_results(client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    expected = CONTEXT_SEED_EXPECTATIONS[pdf.name]
    with pdf.open("rb") as fh:
        body = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    assert body["status"] == STATUS_INTAKE_COMPLETE

    detail = client.get(f"/rfp/tickets/{body['ticket_id']}").json()
    finals = detail["final_department_results"]
    assert {r["department_id"] for r in finals if r["department_id"] != "ceo"} == set(
        expected["departments"]
    )
    for row in finals:
        assert row["contact"]
        assert row["key_aspects"]

    # department_sections also carry contact + key_aspects
    for sec in detail["department_sections"]:
        assert sec["contact"] == CONTEXT_DEPARTMENT_OWNERS[sec["department_id"]]
        assert sec["key_aspects"]

    ticket = get_ticket(body["ticket_id"])
    assert ticket_to_dict(ticket)["final_department_results"]  # type: ignore[arg-type]


def test_andes_excludes_training_contact_and_aspects() -> None:
    result = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-2.pdf")
    ids = {r["department_id"] for r in result.final_department_results}
    assert "training" not in ids
    assert "Jake Morrison" not in {r["contact"] for r in result.final_department_results}
    assert "training" not in result.sections


def test_ui_formats_per_department_key_aspects_and_contacts() -> None:
    src = UI.read_text(encoding="utf-8")
    assert "final_department_results" in src
    assert "per-department key aspects + contacts" in src


def test_build_final_department_results_helper_shape() -> None:
    rows = build_final_department_results(
        sections={
            "marketing": ["Brand exclusivity for Acme"],
            "operaciones": ["Staff capacity for Acme"],
        },
        ask_whom=[
            {
                "department_id": "marketing",
                "owner": "Camila Ospina",
                "ask": "Brand exclusivity for Acme",
            }
        ],
        departments_needed=["marketing", "operaciones"],
        requires_ceo_approval=True,
    )
    assert [r["department_id"] for r in rows] == [
        "marketing",
        "operaciones",
        "ceo",
    ]
    assert rows[0]["contact"] == "Camila Ospina"
    assert rows[-1]["contact"] == CONTEXT_CEO_NAME
    assert rows[0]["key_aspects"]
