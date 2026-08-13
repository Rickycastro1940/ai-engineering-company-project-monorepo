"""Evaluate: Part 2 routing handoff carries ticket_id + synthesizer / key_aspects.

Acceptance (any of these mechanisms — we require all three for Brasaland Part 1):
1. **Documented contract** — ``PART2_HANDOFF.md``
2. **DB flag** — ``rfp_tickets.part2_ready``
3. **DB field** — ``rfp_tickets.part2_handoff_json`` (+ queue of ready tickets)

Guarantee: Part 2 starts from ``ticket_id`` + ``work_streams[].key_aspects``
(synthesizer payload). Re-parsing the PDF is not required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake import run_intake_pipeline, route_intake_to_part2
from data.pipelines.rfp_intake.constants import (
    HANDOFF_SCHEMA_VERSION,
    STATUS_DISCARDED,
    STATUS_INTAKE_COMPLETE,
)
from data.pipelines.rfp_intake.routing import (
    build_part2_handoff,
    validate_part2_handoff,
)
from services.rfp import router as rfp_router
from services.rfp.models import RfpTicket
from services.rfp.store import (
    get_ticket,
    init_db,
    list_part2_queue,
    list_sections,
    load_part2_handoff,
    reset_engine,
    ticket_to_dict,
)

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
DOC = REPO / "data" / "pipelines" / "rfp_intake" / "PART2_HANDOFF.md"
MODELS = REPO / "services" / "rfp" / "models.py"
STORE = REPO / "services" / "rfp" / "store.py"
ROUTING = REPO / "data" / "pipelines" / "rfp_intake" / "routing.py"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'handoff.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Mechanism 1 — documented contract
# ---------------------------------------------------------------------------


def test_documented_contract_requires_ticket_id_and_key_aspects() -> None:
    assert DOC.is_file()
    text = DOC.read_text(encoding="utf-8")
    for required in (
        "ticket_id",
        "work_streams",
        "key_aspects",
        "part2_ready",
        "part2_handoff_json",
        "reparse_pdf_required",
        "synthesizer",
        "queue",
    ):
        assert required in text, f"PART2_HANDOFF.md missing {required!r}"
    assert "must not re-parse" in text.casefold() or "without re-parsing" in text.casefold()


def test_routing_module_documents_three_mechanisms() -> None:
    src = ROUTING.read_text(encoding="utf-8")
    assert "part2_ready" in src
    assert "part2_handoff_json" in src
    assert "ticket_id" in src
    assert "key_aspects" in src
    assert "queue" in src.casefold()


# ---------------------------------------------------------------------------
# Mechanism 2 + 3 — DB flag / DB field / queue
# ---------------------------------------------------------------------------


def test_models_expose_part2_ready_flag_and_handoff_json_field() -> None:
    assert hasattr(RfpTicket, "part2_ready")
    assert hasattr(RfpTicket, "part2_handoff_json")
    assert hasattr(RfpTicket, "part2_routed_at")
    models_src = MODELS.read_text(encoding="utf-8")
    assert "part2_ready" in models_src
    assert "part2_handoff_json" in models_src
    store_src = STORE.read_text(encoding="utf-8")
    assert "list_part2_queue" in store_src
    assert "load_part2_handoff" in store_src
    assert "route_intake_to_part2" in store_src


def test_persist_sets_flag_db_field_and_queue_with_ticket_id(
    client: TestClient,
) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    with pdf.open("rb") as fh:
        body = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()

    ticket_id = body["ticket_id"]
    assert body["status"] == STATUS_INTAKE_COMPLETE

    # Response surfaces the contract
    assert body["part2_ready"] is True
    handoff = body["part2_handoff"]
    assert handoff["ticket_id"] == ticket_id
    assert handoff["schema_version"] == HANDOFF_SCHEMA_VERSION
    assert handoff["part2_ready"] is True
    assert handoff["reparse_pdf_required"] is False
    assert handoff["work_streams"]
    assert handoff["synthesizer"]["departments_for_drafting"]

    # DB flag + DB field
    ticket = get_ticket(ticket_id)
    assert ticket is not None
    assert ticket.part2_ready is True
    assert ticket.part2_handoff_json
    persisted = json.loads(ticket.part2_handoff_json)
    assert persisted["ticket_id"] == ticket_id
    assert all(ws["key_aspects"] for ws in persisted["work_streams"])

    # Queue view (tickets with flag + intake_complete)
    queue = list_part2_queue()
    match = next(q for q in queue if q["ticket_id"] == ticket_id)
    assert match["part2_ready"] is True
    assert match["status"] == STATUS_INTAKE_COMPLETE
    assert match["work_stream_count"] == len(persisted["work_streams"])


def test_loaded_handoff_matches_department_section_key_aspects(
    client: TestClient,
) -> None:
    """Synthesizer payload key_aspects align with persisted DepartmentSection rows."""
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        body = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    ticket_id = body["ticket_id"]

    handoff = load_part2_handoff(ticket_id)
    sections = {s.department_id: json.loads(s.key_aspects_json) for s in list_sections(ticket_id)}

    assert handoff["ticket_id"] == ticket_id
    assert set(ws["department_id"] for ws in handoff["work_streams"]) == set(sections)
    for stream in handoff["work_streams"]:
        dept = stream["department_id"]
        assert stream["key_aspects"] == sections[dept]
        assert stream["owner"]
        assert stream["next_action"] == "draft_section"

    # Synthesizer block is present for Part 2 consumers
    synth = handoff["synthesizer"]
    assert set(synth["departments_for_drafting"]) == set(sections)
    assert set(synth["owners"]) == set(sections)


def test_http_queue_and_handoff_endpoints_same_api(client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    with pdf.open("rb") as fh:
        ticket_id = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()["ticket_id"]

    queue = client.get("/rfp/part2/queue").json()
    assert any(q["ticket_id"] == ticket_id for q in queue["queue"])

    handoff = client.get(f"/rfp/tickets/{ticket_id}/part2-handoff").json()
    assert handoff["ticket_id"] == ticket_id
    assert handoff["work_streams"]
    assert all(ws["key_aspects"] for ws in handoff["work_streams"])
    # Part 2 drafting inputs are fully present without PDF bytes
    drafting = [
        {
            "department_id": ws["department_id"],
            "owner": ws["owner"],
            "key_aspects": ws["key_aspects"],
        }
        for ws in handoff["work_streams"]
    ]
    assert drafting
    assert handoff["reparse_pdf_required"] is False


# ---------------------------------------------------------------------------
# Builder / validator contract
# ---------------------------------------------------------------------------


def test_route_intake_embeds_ticket_id_into_synthesizer_handoff() -> None:
    result = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-1.pdf")
    assert result.status == STATUS_INTAKE_COMPLETE
    # Pipeline synthesizer payload alone is not the routed contract (no ticket yet)
    assert result.sections

    contract = route_intake_to_part2(
        ticket_id="eval-ticket-abc",
        intake_result=result,
        source_pdf_path="data/raw/rfp/eval/file.pdf",
    )
    assert contract is not None
    validate_part2_handoff(contract)
    assert contract["ticket_id"] == "eval-ticket-abc"
    assert contract["part2_ready"] is True
    assert contract["reparse_pdf_required"] is False
    assert contract["schema_version"] == HANDOFF_SCHEMA_VERSION
    assert set(s["department_id"] for s in contract["work_streams"]) == set(
        result.departments_needed
    )
    for stream in contract["work_streams"]:
        assert stream["key_aspects"] == result.sections[stream["department_id"]]
    assert contract["synthesizer"]["departments_for_drafting"] == list(
        result.departments_needed
    ) or set(contract["synthesizer"]["departments_for_drafting"]) == set(
        result.departments_needed
    )


def test_validate_rejects_missing_ticket_id_or_empty_key_aspects() -> None:
    base = build_part2_handoff(
        ticket_id="ok",
        status=STATUS_INTAKE_COMPLETE,
        metadata={"client_name": "X"},
        departments_needed=["marketing"],
        sections={"marketing": ["brand exclusivity window"]},
        intake_summary="summary",
        ask_whom=[{"department_id": "marketing", "owner": "Camila Ospina", "ask": "x"}],
        open_questions=[],
        requires_ceo_approval=False,
    )
    validate_part2_handoff(base)

    bad_id = dict(base, ticket_id="")
    with pytest.raises(ValueError, match="ticket_id"):
        validate_part2_handoff(bad_id)

    bad_streams = dict(base, work_streams=[])
    with pytest.raises(ValueError, match="work_streams"):
        validate_part2_handoff(bad_streams)

    empty_aspects = dict(
        base,
        work_streams=[
            {
                "department_id": "marketing",
                "owner": "Camila Ospina",
                "key_aspects": [],
                "next_action": "draft_section",
            }
        ],
    )
    with pytest.raises(ValueError, match="key_aspects"):
        validate_part2_handoff(empty_aspects)


def test_discarded_not_routed_no_flag_no_queue(client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-3.pdf"
    with pdf.open("rb") as fh:
        body = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    assert body["status"] == STATUS_DISCARDED
    assert body.get("part2_ready") is False
    ticket = get_ticket(body["ticket_id"])
    assert ticket is not None
    assert ticket.part2_ready is False
    assert not ticket.part2_handoff_json
    assert not any(q["ticket_id"] == body["ticket_id"] for q in list_part2_queue())
    assert client.get(f"/rfp/tickets/{body['ticket_id']}/part2-handoff").status_code == 409

    # Pipeline-level route also returns None
    result = run_intake_pipeline(pdf_path=pdf)
    assert route_intake_to_part2(ticket_id="x", intake_result=result) is None


def test_ticket_detail_exposes_handoff_for_ui(client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        body = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    detail = ticket_to_dict(get_ticket(body["ticket_id"]))  # type: ignore[arg-type]
    assert detail["part2_ready"] is True
    assert detail["part2_handoff"]["ticket_id"] == body["ticket_id"]
    assert detail["work_streams"]
    assert all(ws["key_aspects"] for ws in detail["work_streams"])
