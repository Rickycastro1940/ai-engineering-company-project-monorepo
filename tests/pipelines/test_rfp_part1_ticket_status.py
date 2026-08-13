"""Evaluate: Part 1 ticket status reflects reality.

Allowed: analyzing → intake_complete | discarded (failed only on convert errors).
Forbidden in Part 1: waiting_for_approval (Part 3), drafting, under_evaluation, done.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake import run_intake_pipeline
from data.pipelines.rfp_intake.constants import (
    PART1_STATUSES,
    PART2_PLUS_STATUSES,
    STATUS_ANALYZING,
    STATUS_DISCARDED,
    STATUS_INTAKE_COMPLETE,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_intake.context_rules import CONTEXT_SEED_EXPECTATIONS
from services.rfp import router as rfp_router
from services.rfp.store import (
    create_analyzing_ticket,
    get_ticket,
    init_db,
    list_tickets,
    reset_engine,
    save_intake_result,
)

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
CONTEXT = REPO / "CONTEXT-company.md"


def test_context_maps_part1_vs_waiting_for_approval() -> None:
    text = CONTEXT.read_text(encoding="utf-8")
    assert "`analyzing`" in text
    assert "`intake_complete`" in text
    assert "`discarded`" in text
    assert "`waiting_for_approval`" in text
    # waiting_for_approval is Part 3 in the status table
    assert "waiting_for_approval" in text
    row = next(
        ln for ln in text.splitlines() if "`waiting_for_approval`" in ln and "|" in ln
    )
    assert "3" in row


def test_part1_constants_exclude_waiting_for_approval() -> None:
    assert STATUS_WAITING_FOR_APPROVAL not in PART1_STATUSES
    assert STATUS_WAITING_FOR_APPROVAL in PART2_PLUS_STATUSES
    assert PART1_STATUSES.isdisjoint(PART2_PLUS_STATUSES)
    assert {STATUS_ANALYZING, STATUS_INTAKE_COMPLETE, STATUS_DISCARDED} <= PART1_STATUSES


def test_pipeline_code_never_assigns_waiting_for_approval() -> None:
    root = REPO / "data" / "pipelines" / "rfp_intake"
    for path in root.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        # Allow the constant definition / documentation of the forbidden status
        if path.name == "constants.py":
            assert 'STATUS_WAITING_FOR_APPROVAL: Final = "waiting_for_approval"' in src
            continue
        assert "waiting_for_approval" not in src, path.name


def test_new_ticket_starts_analyzing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'status.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    reset_engine()
    init_db()
    ticket = create_analyzing_ticket(title="status check")
    assert ticket.status == STATUS_ANALYZING
    assert ticket.status in PART1_STATUSES
    assert ticket.status != STATUS_WAITING_FOR_APPROVAL


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'p1-status.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


@pytest.mark.parametrize(
    "filename",
    [
        "CONTEXT-brasaland-request-1.pdf",
        "CONTEXT-brasaland-request-2.pdf",
        "CONTEXT-brasaland-request-3.pdf",
    ],
)
def test_seed_upload_status_is_part1_reality(client: TestClient, filename: str) -> None:
    expected = CONTEXT_SEED_EXPECTATIONS[filename]
    pdf = SEEDS / filename
    with pdf.open("rb") as fh:
        body = client.post(
            "/rfp/tickets",
            files={"file": (filename, fh, "application/pdf")},
        ).json()
    status = body["status"]
    assert status in PART1_STATUSES
    assert status != STATUS_WAITING_FOR_APPROVAL
    assert status not in PART2_PLUS_STATUSES
    if expected.get("accept"):
        assert status == STATUS_INTAKE_COMPLETE
    else:
        assert status == STATUS_DISCARDED
        assert body.get("discard_reason")

    ticket = get_ticket(body["ticket_id"])
    assert ticket is not None
    assert ticket.status == status
    assert ticket.status != STATUS_WAITING_FOR_APPROVAL


def test_async_upload_returns_analyzing_not_waiting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("RFP_INTAKE_SYNC", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'async-status.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    reset_engine()
    init_db()

    scheduled: list = []

    def _capture(self, func, *args, **kwargs):  # noqa: ANN001
        scheduled.append((func, args, kwargs))

    monkeypatch.setattr(BackgroundTasks, "add_task", _capture)
    app = FastAPI()
    app.include_router(rfp_router)
    client = TestClient(app)
    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    with pdf.open("rb") as fh:
        body = client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
        ).json()
    assert body["status"] == STATUS_ANALYZING
    assert body["status"] != STATUS_WAITING_FOR_APPROVAL
    ticket = get_ticket(body["ticket_id"])
    assert ticket is not None
    assert ticket.status == STATUS_ANALYZING


def test_direct_pipeline_statuses_match_part1() -> None:
    for filename, expected in CONTEXT_SEED_EXPECTATIONS.items():
        result = run_intake_pipeline(pdf_path=SEEDS / filename)
        assert result.status in PART1_STATUSES
        assert result.status != STATUS_WAITING_FOR_APPROVAL
        if expected.get("accept"):
            assert result.status == STATUS_INTAKE_COMPLETE
        else:
            assert result.status == STATUS_DISCARDED


def test_store_rejects_waiting_for_approval_on_part1_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'reject.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    reset_engine()
    init_db()
    ticket = create_analyzing_ticket(title="bad status")
    fake = SimpleNamespace(
        status=STATUS_WAITING_FOR_APPROVAL,
        markdown_text="",
        metadata={},
        departments_needed=[],
        unmapped_topics=[],
        conflicts=[],
        intake_summary="",
        requires_ceo_approval=False,
        discard_reason=None,
        discard_rule_id=None,
        error_message=None,
        readability_scores={},
        trace=[],
        sections={},
        part2_handoff={},
        ask_whom=[],
        open_questions=[],
    )
    with pytest.raises(ValueError, match="non-Part-1"):
        save_intake_result(ticket.ticket_id, fake, source_pdf_path="")


def test_list_tickets_after_seeds_never_waiting(client: TestClient) -> None:
    for name in CONTEXT_SEED_EXPECTATIONS:
        with (SEEDS / name).open("rb") as fh:
            client.post("/rfp/tickets", files={"file": (name, fh, "application/pdf")})
    statuses = {t.status for t in list_tickets()}
    assert statuses <= PART1_STATUSES
    assert STATUS_WAITING_FOR_APPROVAL not in statuses
    assert STATUS_INTAKE_COMPLETE in statuses
    assert STATUS_DISCARDED in statuses
