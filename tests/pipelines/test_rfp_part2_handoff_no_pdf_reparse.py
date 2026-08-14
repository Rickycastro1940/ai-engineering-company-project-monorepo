"""Evaluate: Part 2 consumes Part 1's routing handoff — not a PDF reparse.

Primary generator input is ``ticket_id`` + synthesizer ``work_streams[].key_aspects``.
Re-parsing the RFP PDF is forbidden as generator input.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

from data.pipelines.rfp_intake import run_intake_pipeline
from data.pipelines.rfp_intake.constants import STATUS_INTAKE_COMPLETE
from data.pipelines.rfp_intake.routing import route_intake_to_part2
from data.pipelines.rfp_response import (
    PRIMARY_GENERATOR_INPUT,
    Part1HandoffNotReady,
    assert_part1_routing_ready,
    run_response_for_ticket,
    run_response_pipeline,
    synthesizer_payload_from_handoff,
)
from data.pipelines.rfp_response.agents import (
    Part1DepartmentSummary,
    get_generator_agent,
)
from data.pipelines.rfp_response.generator import generate_department_draft

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
RESPONSE = REPO / "data" / "pipelines" / "rfp_response"
HANDOFF_DOC = REPO / "data" / "pipelines" / "rfp_intake" / "PART2_HANDOFF.md"


def test_primary_generator_input_is_ticket_id_plus_synthesizer_key_aspects() -> None:
    assert "ticket_id" in PRIMARY_GENERATOR_INPUT
    assert "key_aspects" in PRIMARY_GENERATOR_INPUT
    assert "pdf" not in PRIMARY_GENERATOR_INPUT.casefold()
    doc = HANDOFF_DOC.read_text(encoding="utf-8")
    assert "must not re-parse the PDF" in doc
    assert "ticket_id" in doc
    assert "key_aspects" in doc
    assert "work_streams" in doc
    assert "synthesizer" in doc


def test_canonical_part2_entry_takes_ticket_id_not_a_pdf() -> None:
    sig = inspect.signature(run_response_for_ticket)
    assert "ticket_id" in sig.parameters
    assert "pdf_path" not in sig.parameters
    assert "source_pdf_path" not in sig.parameters
    assert "markdown_text" not in sig.parameters
    src = inspect.getsource(run_response_for_ticket)
    assert "load_ready_part2_handoff" in src
    assert "pdf_path" not in src


def test_part2_package_never_imports_pdf_converter() -> None:
    forbidden_imports = {
        "markitdown",
        "convert_document_to_markdown",
        "convert_pdf_to_markdown",
        "run_intake_pipeline",
    }
    for path in RESPONSE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_imports, path.name
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = {a.name for a in node.names}
                assert "markitdown" not in module
                assert not names.intersection(forbidden_imports), path.name


def test_handoff_ready_requires_ticket_id_and_key_aspects_payload() -> None:
    streams = [
        {
            "department_id": "marketing",
            "owner": "Camila Ospina",
            "key_aspects": ["Brand exclusivity for Synthetic Co"],
        }
    ]
    with pytest.raises(Part1HandoffNotReady, match="ticket_id"):
        assert_part1_routing_ready(
            ticket_id="",
            status=STATUS_INTAKE_COMPLETE,
            part2_ready=True,
            handoff={
                "ticket_id": "",
                "status": STATUS_INTAKE_COMPLETE,
                "part2_ready": True,
                "reparse_pdf_required": False,
                "work_streams": streams,
            },
        )
    with pytest.raises(Part1HandoffNotReady, match="key_aspects"):
        assert_part1_routing_ready(
            ticket_id="t-handoff",
            status=STATUS_INTAKE_COMPLETE,
            part2_ready=True,
            handoff={
                "ticket_id": "t-handoff",
                "status": STATUS_INTAKE_COMPLETE,
                "part2_ready": True,
                "reparse_pdf_required": False,
                "work_streams": [
                    {"department_id": "marketing", "key_aspects": []}
                ],
            },
        )
    contract = assert_part1_routing_ready(
        ticket_id="t-handoff",
        status=STATUS_INTAKE_COMPLETE,
        part2_ready=True,
        handoff={
            "ticket_id": "t-handoff",
            "status": STATUS_INTAKE_COMPLETE,
            "part2_ready": True,
            "reparse_pdf_required": False,
            "work_streams": streams,
        },
    )
    assert contract["ticket_id"] == "t-handoff"
    payload = synthesizer_payload_from_handoff(contract)
    assert payload["ticket_id"] == "t-handoff"
    assert payload["primary_input"] == PRIMARY_GENERATOR_INPUT
    assert payload["work_streams"][0]["key_aspects"] == streams[0]["key_aspects"]


def test_generator_rejects_pdf_as_primary_input() -> None:
    aspects = ["Brand exclusivity for Synthetic Co"]
    with pytest.raises(TypeError, match="raw PDF"):
        generate_department_draft(
            department_id="marketing",
            metadata={"client_name": "Synthetic Co"},
            key_aspects=aspects,
            pdf_path="/tmp/missing-rfp.pdf",
        )
    with pytest.raises(TypeError, match="raw PDF"):
        generate_department_draft(
            department_id="marketing",
            metadata={"client_name": "Synthetic Co"},
            key_aspects=aspects,
            markdown_text="# converted from PDF",
        )
    summary = Part1DepartmentSummary.from_work_stream(
        {
            "department_id": "marketing",
            "key_aspects": aspects,
        },
        metadata={
            "client_name": "Synthetic Co",
            "source_pdf_path": "data/raw/gone.pdf",
            "markdown_text": "# leaked",
        },
        ticket_id="t-handoff",
    )
    assert "source_pdf_path" not in summary.metadata
    assert "markdown_text" not in summary.metadata
    assert summary.ticket_id == "t-handoff"
    assert summary.key_aspects == aspects
    with pytest.raises(ValueError, match="key_aspects"):
        get_generator_agent("marketing").receive_part1_summary(
            Part1DepartmentSummary(
                department_id="marketing",
                key_aspects=[],
                metadata={"client_name": "Synthetic Co"},
            )
        )


def test_part2_runs_from_handoff_when_pdf_is_missing() -> None:
    """PDF is not primary input: a missing/unreadable file must not block drafting."""
    intake = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-2.pdf")
    handoff = route_intake_to_part2(
        ticket_id="no-pdf-primary",
        intake_result=intake,
        source_pdf_path="/this/path/does/not/exist.pdf",
    )
    assert handoff is not None
    assert handoff["ticket_id"] == "no-pdf-primary"
    assert handoff["reparse_pdf_required"] is False
    assert not Path(handoff["source_pdf_path"]).exists()

    expected_aspects = {
        stream["department_id"]: list(stream["key_aspects"])
        for stream in handoff["work_streams"]
    }
    assert expected_aspects
    assert all(expected_aspects.values())

    with patch("markitdown.MarkItDown", side_effect=AssertionError("PDF re-ingest")):
        result = run_response_pipeline(
            ticket_id="no-pdf-primary",
            handoff=handoff,
            intake_status=STATUS_INTAKE_COMPLETE,
            part2_ready=True,
        )

    assert result.error_message is None
    assert result.all_passed is True
    load = next(e for e in result.trace if e["node"] == "load_handoff")
    assert load["payload"]["primary_input"] == PRIMARY_GENERATOR_INPUT
    assert load["payload"]["reparse_pdf_required"] is False
    assert load["payload"]["source"] == "part1_handoff_contract"

    drafted = {s["department_id"]: s["draft_content"] for s in result.section_results}
    assert set(drafted) == set(expected_aspects)
    for dept, aspects in expected_aspects.items():
        text = drafted[dept]
        for aspect in aspects:
            assert aspect[:24] in text
        assert f"`{dept}`" in text or dept in text.casefold()
