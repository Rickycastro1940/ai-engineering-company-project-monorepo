"""Evaluate: evaluation output follows the EvaluationResult shape.

CONTEXT §2.3 DepartmentSection.evaluation_results is
(readability, relevance, compliance) — structured objects, not a prose blob.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_type_hints

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_OPERACIONES,
    STATUS_INTAKE_COMPLETE,
    STATUS_UNDER_EVALUATION,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_response.compliance_rules import EVAL_DIMENSIONS
from data.pipelines.rfp_response.evaluators import (
    DimensionResult,
    EvaluationResult,
    UnstructuredEvaluationError,
    assert_evaluation_result_shape,
    evaluate_section,
)
from data.pipelines.rfp_response.generator import generate_department_draft
from data.pipelines.rfp_response.loop import run_section_loop
from services.rfp import router as rfp_router
from services.rfp.models import RfpDepartmentSection
from services.rfp.store import (
    get_ticket,
    init_db,
    list_sections,
    persist_part2_progress,
    reset_engine,
    ticket_to_dict,
)

REPO = Path(__file__).resolve().parents[2]
CONTEXT = REPO / "CONTEXT-company.md"
SEEDS = REPO / "rfp-requests" / "brasaland"

DIMENSION_OBJECT_KEYS = (
    "name",
    "passed",
    "score",
    "notes",
    "failures",
    "rule_ids",
    "evaluator_agent",
)


def _context_section_2_3() -> str:
    text = CONTEXT.read_text(encoding="utf-8")
    return text.split("### 2.3")[1].split("###")[0]


def _assert_dimension_object(value: object, *, expected_name: str) -> None:
    assert isinstance(value, dict), (
        f"{expected_name} must be a structured object, not {type(value).__name__}"
    )
    assert not isinstance(value, str)
    assert value.get("name") == expected_name
    assert isinstance(value["passed"], bool)
    assert isinstance(value["score"], (int, float))
    assert not isinstance(value["score"], bool)
    assert isinstance(value["notes"], list)
    assert isinstance(value["failures"], list)
    assert isinstance(value["rule_ids"], list)
    for key in DIMENSION_OBJECT_KEYS:
        assert key in value


def _assert_evaluation_result_object(payload: object) -> dict:
    assert isinstance(payload, dict), (
        f"evaluation_results must be a dict, not {type(payload).__name__}"
    )
    assert not isinstance(payload, str)
    for dim in EVAL_DIMENSIONS:
        _assert_dimension_object(payload[dim], expected_name=dim)
    assert isinstance(payload["feedback"], list)
    assert isinstance(payload["scores"], dict)
    for dim in EVAL_DIMENSIONS:
        assert isinstance(payload["scores"][dim], (int, float))
    return payload


def _compliant_draft() -> str:
    return generate_department_draft(
        department_id=DEPARTMENT_OPERACIONES,
        metadata={
            "client_name": "Andes Tech",
            "location": "Medellín",
            "service_type": "weekly catering",
        },
        key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
    ).draft_content


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'eval-shape.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_context_2_3_evaluation_results_are_three_named_dimensions() -> None:
    """CONTEXT lists evaluation_results as (readability, relevance, compliance)."""
    section = _context_section_2_3()
    assert "`evaluation_results`" in section or "evaluation_results" in section
    assert "(readability, relevance, compliance)" in section
    assert EVAL_DIMENSIONS == ("readability", "relevance", "compliance")


def test_department_section_model_stores_evaluation_results_as_json() -> None:
    assert hasattr(RfpDepartmentSection, "evaluation_results_json")
    assert hasattr(RfpDepartmentSection, "draft_content")


def test_evaluation_result_dataclass_fields_are_structured_dimensions() -> None:
    hints = get_type_hints(EvaluationResult)
    assert hints["readability"] is DimensionResult
    assert hints["relevance"] is DimensionResult
    assert hints["compliance"] is DimensionResult
    assert "feedback" in hints


def test_evaluate_section_to_dict_is_object_not_prose() -> None:
    result = evaluate_section(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content=_compliant_draft(),
        key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
        metadata={"client_name": "Andes Tech", "location": "Medellín"},
    )
    assert isinstance(result, EvaluationResult)
    payload = result.to_dict()
    _assert_evaluation_result_object(payload)
    dumped = json.dumps(payload)
    parsed = json.loads(dumped)
    assert isinstance(parsed, dict)
    assert isinstance(parsed["readability"], dict)
    assert isinstance(parsed["readability"]["passed"], bool)


def test_failing_evaluation_is_still_structured_not_a_paragraph() -> None:
    result = evaluate_section(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content="Setup in 3 business days. Price USD $100 only.",
        key_aspects=["Operational feasibility for Andes Tech"],
        metadata={"client_name": "Andes Tech"},
    )
    payload = result.to_dict()
    _assert_evaluation_result_object(payload)
    assert payload["passed"] is False
    assert payload["compliance"]["passed"] is False
    assert payload["compliance"]["failures"]
    assert all(isinstance(item, str) for item in payload["feedback"])


def test_unstructured_text_is_not_an_evaluation_result() -> None:
    with pytest.raises(UnstructuredEvaluationError, match="not unstructured text"):
        assert_evaluation_result_shape("The draft looks good and complies with all rules.")


def test_dimension_paragraphs_are_not_an_evaluation_result() -> None:
    with pytest.raises(UnstructuredEvaluationError, match="readability"):
        assert_evaluation_result_shape(
            {
                "readability": "Clear and professional prose throughout.",
                "relevance": "Answers the RFP key aspects.",
                "compliance": "Meets every guideline in section 5.",
            }
        )


def test_missing_dimension_objects_are_rejected() -> None:
    with pytest.raises(UnstructuredEvaluationError, match="compliance"):
        assert_evaluation_result_shape(
            {
                "readability": {"name": "readability", "passed": True, "score": 1.0},
                "relevance": {"name": "relevance", "passed": True, "score": 1.0},
                "feedback": "Looks compliant overall.",
            }
        )


def test_feedback_must_be_a_list_not_a_narrative() -> None:
    with pytest.raises(UnstructuredEvaluationError, match="feedback"):
        assert_evaluation_result_shape(
            {
                "readability": {"name": "readability", "passed": True, "score": 1.0},
                "relevance": {"name": "relevance", "passed": True, "score": 1.0},
                "compliance": {"name": "compliance", "passed": True, "score": 1.0},
                "feedback": "Please add COP prices and the brand pillars.",
            }
        )


def test_section_loop_emits_structured_evaluation_results() -> None:
    loop = run_section_loop(
        department_id=DEPARTMENT_OPERACIONES,
        metadata={
            "client_name": "Andes Tech",
            "location": "Medellín",
            "service_type": "weekly catering",
        },
        key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
    )
    payload = loop.to_dict()
    ev = payload["evaluation_results"]
    _assert_evaluation_result_object(ev)
    assert ev is not loop.evaluation  # serialized dict, not the dataclass


def test_http_generate_response_persists_structured_evaluation_objects(
    client: TestClient,
) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    assert created["status"] == STATUS_INTAKE_COMPLETE
    ticket_id = created["ticket_id"]

    res = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == STATUS_WAITING_FOR_APPROVAL

    pipeline_sections = body["part2_pipeline"]["section_results"]
    assert pipeline_sections
    for section in pipeline_sections:
        _assert_evaluation_result_object(section["evaluation_results"])

    for row in list_sections(ticket_id):
        raw = row.evaluation_results_json
        assert raw
        parsed = json.loads(raw)
        assert isinstance(parsed, dict), "stored evaluation_results_json must be an object"
        _assert_evaluation_result_object(parsed)

    detail = ticket_to_dict(get_ticket(ticket_id))  # type: ignore[arg-type]
    for section in detail["department_sections"]:
        ev = section["evaluation_results"]
        assert isinstance(ev, dict)
        _assert_evaluation_result_object(ev)


def test_persist_rejects_unstructured_evaluation_text(client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]

    with pytest.raises(UnstructuredEvaluationError, match="not unstructured text"):
        persist_part2_progress(
            ticket_id,
            status=STATUS_UNDER_EVALUATION,
            section_results=[
                {
                    "department_id": "operaciones",
                    "draft_content": "draft",
                    "evaluation_results": "The draft looks good and is compliant.",
                }
            ],
        )
