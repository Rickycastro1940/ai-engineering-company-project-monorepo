"""UI verification: upload CONTEXT sample PDFs through the backoffice page path.

Uses the real ``services.agent.app`` (StaticFiles + /rfp API) the same way
``uis/backoffice/rfp-upload.html`` does: POST /rfp/tickets then GET /rfp/tickets/{id}.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_TRAINING,
    STATUS_DISCARDED,
    STATUS_INTAKE_COMPLETE,
)
from data.pipelines.rfp_intake.context_rules import CONTEXT_SEED_EXPECTATIONS

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
UI_PAGE = REPO / "uis" / "backoffice" / "rfp-upload.html"


@pytest.fixture()
def ui_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ui-seeds.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    from services.rfp.store import init_db, reset_engine

    reset_engine()
    init_db()
    # Full agent app — serves /rfp-upload.html and /rfp/* like production UI
    from services.agent.app import app

    return TestClient(app)


def test_backoffice_rfp_upload_page_is_served(ui_client: TestClient) -> None:
    assert UI_PAGE.is_file()
    res = ui_client.get("/rfp-upload.html")
    assert res.status_code == 200
    body = res.text
    assert "/rfp/tickets" in body
    assert "intake_complete" in body
    assert "discarded" in body
    assert "analyzing" in body
    assert "Approve" in body
    assert "Reject" in body
    assert "/approvals" in body


@pytest.mark.parametrize(
    "filename",
    [
        "CONTEXT-brasaland-request-1.pdf",
        "CONTEXT-brasaland-request-2.pdf",
        "CONTEXT-brasaland-request-3.pdf",
    ],
)
def test_ui_upload_context_seed_pdfs(ui_client: TestClient, filename: str) -> None:
    """Upload each CONTEXT sample through the same endpoint the UI uses."""
    pdf = SEEDS / filename
    expected = CONTEXT_SEED_EXPECTATIONS[filename]

    # Mimic rfp-upload.html FormData POST
    with pdf.open("rb") as fh:
        post = ui_client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
            data={"title": f"UI upload {filename}"},
        )
    assert post.status_code == 200, post.text
    created = post.json()
    ticket_id = created["ticket_id"]
    assert ticket_id

    # Mimic UI poll
    detail = ui_client.get(f"/rfp/tickets/{ticket_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["ticket_id"] == ticket_id

    if expected.get("accept"):
        assert body["status"] == STATUS_INTAKE_COMPLETE
        assert body.get("part2_ready") is True
        assert expected["client_substr"] in (
            (body.get("metadata") or {}).get("client_name") or ""
        )
        assert set(body["departments_needed"]) == set(expected["departments"])
        assert body["requires_ceo_approval"] is expected["requires_ceo_approval"]
        for excluded in expected.get("exclude_departments") or set():
            assert excluded not in body["departments_needed"]
        assert body["sections"]
        assert body["intake_summary"]
        assert "What to ask whom" in (body["intake_summary"] or "")
    else:
        assert body["status"] == STATUS_DISCARDED
        assert body.get("discard_reason")
        assert body.get("part2_ready") is False
        assert body.get("departments_needed") == []


def test_ui_upload_formal_then_informal_then_invalid(ui_client: TestClient) -> None:
    """End-to-end UI sequence matching Camila's three sample uploads."""
    outcomes: list[tuple[str, str]] = []
    for filename in (
        "CONTEXT-brasaland-request-1.pdf",
        "CONTEXT-brasaland-request-2.pdf",
        "CONTEXT-brasaland-request-3.pdf",
    ):
        pdf = SEEDS / filename
        with pdf.open("rb") as fh:
            res = ui_client.post(
                "/rfp/tickets",
                files={"file": (filename, fh, "application/pdf")},
            )
        assert res.status_code == 200
        ticket_id = res.json()["ticket_id"]
        polled = ui_client.get(f"/rfp/tickets/{ticket_id}").json()
        outcomes.append((filename, polled["status"]))

    assert outcomes == [
        ("CONTEXT-brasaland-request-1.pdf", STATUS_INTAKE_COMPLETE),
        ("CONTEXT-brasaland-request-2.pdf", STATUS_INTAKE_COMPLETE),
        ("CONTEXT-brasaland-request-3.pdf", STATUS_DISCARDED),
    ]

    # Formal has training; informal does not — verify via last accepted tickets list
    listed = ui_client.get("/rfp/tickets").json()["tickets"]
    by_client = {
        (t.get("metadata") or {}).get("client_name", ""): t for t in listed
    }
    sunset = next(t for t in listed if "Sunset" in str(t.get("metadata")))
    andes = next(t for t in listed if "Andes" in str(t.get("metadata")))
    assert DEPARTMENT_TRAINING in sunset["departments_needed"]
    assert DEPARTMENT_TRAINING not in andes["departments_needed"]
    assert by_client or True  # silence unused if structure differs
