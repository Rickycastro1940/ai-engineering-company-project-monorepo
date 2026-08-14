"""Part 2: response generation + evaluation against CONTEXT §5."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake import run_intake_pipeline
from data.pipelines.rfp_intake.constants import (
    STATUS_INTAKE_COMPLETE,
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_intake.routing import route_intake_to_part2
from data.pipelines.rfp_response import (
    REQUIRED_RESPONSE_NODES,
    build_rfp_response_graph,
    run_response_pipeline,
)
from data.pipelines.rfp_response.compliance_rules import (
    BRAND_PILLARS,
    CEO_USD_THRESHOLD,
    CONTEXT_SECTION_5_RULES,
    MAX_SECTION_ITERATIONS,
    MIN_SETUP_BUSINESS_DAYS,
    OFFER_VALIDITY_PHRASE,
)
from data.pipelines.rfp_response.evaluators import (
    evaluate_compliance,
    evaluate_section,
)
from data.pipelines.rfp_response.generator import generate_department_draft
from services.rfp import router as rfp_router
from services.rfp.store import (
    get_ticket,
    init_db,
    list_sections,
    reset_engine,
    save_intake_result,
    ticket_to_dict,
)

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
PIPELINE = REPO / "data" / "pipelines" / "rfp_response"
CONTEXT = REPO / "CONTEXT-company.md"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'p2.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_part2_readiness_and_context_guidelines_documented() -> None:
    assert (PIPELINE / "PART2_READINESS.md").is_file()
    text = CONTEXT.read_text(encoding="utf-8")
    for pillar in BRAND_PILLARS:
        assert pillar in text.casefold()
    assert "10 business days" in text
    assert "30 days" in text
    assert "COP" in text and "USD" in text


def test_response_graph_registers_required_nodes() -> None:
    compiled = build_rfp_response_graph()
    nodes = set(compiled.get_graph().nodes)
    for name in REQUIRED_RESPONSE_NODES:
        assert name in nodes


def test_context_section_5_rules_match_company_md() -> None:
    """Evaluator rule catalog must stay aligned with CONTEXT-company.md §5."""
    text = CONTEXT.read_text(encoding="utf-8")
    section = text.split("## 5. Business Constraints")[1].split("## 6.")[0]
    section_cf = section.casefold()
    expected_ids = {
        "dual_currency",
        "brand_pillars",
        "min_setup_business_days",
        "no_competitors",
        "offer_validity",
        "ceo_threshold",
    }
    assert {r["id"] for r in CONTEXT_SECTION_5_RULES} == expected_ids
    assert "cop" in section_cf and "usd" in section_cf
    for pillar in BRAND_PILLARS:
        assert pillar in section_cf
    assert "10 business days" in section_cf
    assert "competitors by name" in section_cf
    assert "30 days from issuance" in section_cf
    assert "50,000" in section
    assert MIN_SETUP_BUSINESS_DAYS == 10
    assert OFFER_VALIDITY_PHRASE.casefold() in section_cf
    assert CEO_USD_THRESHOLD == 50_000.0


def test_compliance_rejects_competitor_and_short_setup() -> None:
    bad = (
        "We beat McDonald's on price. Setup in 3 business days. "
        "Price USD $100 only."
    )
    result = evaluate_compliance(bad, metadata={})
    assert result.passed is False
    assert "no_competitors" in result.rule_ids
    assert "min_setup_business_days" in result.rule_ids
    assert "dual_currency" in result.rule_ids
    joined = " ".join(result.failures).casefold()
    assert "competitor" in joined or "mcdonald" in joined
    assert "business days" in joined or "3" in joined
    assert "cop" in joined or "usd" in joined


def test_compliance_flags_ceo_threshold_from_metadata() -> None:
    draft = generate_department_draft(
        department_id="procurement",
        metadata={
            "client_name": "Sunset Bay",
            "location": "Florida",
            "estimated_contract_value_usd": 65_000,
        },
        key_aspects=["Supplier exclusivity terms for Sunset Bay"],
    ).draft_content
    result = evaluate_compliance(
        draft, metadata={"estimated_contract_value_usd": 65_000}
    )
    assert result.passed is True
    assert "ceo_threshold" in result.rule_ids
    assert any("ceo_approval_required_part3" in n for n in result.notes)


def test_compliance_accepts_guideline_compliant_draft() -> None:
    draft = generate_department_draft(
        department_id="marketing",
        metadata={
            "client_name": "Acme",
            "location": "Bogotá",
            "service_type": "co-branding",
            "deadline": "2026-10-01",
        },
        key_aspects=["Brand exclusivity for Acme"],
    ).draft_content
    result = evaluate_compliance(draft, metadata={"client_name": "Acme"})
    assert result.passed is True


def test_pipeline_sunset_bay_all_sections_pass() -> None:
    intake = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-1.pdf")
    assert intake.status == STATUS_INTAKE_COMPLETE
    handoff = route_intake_to_part2(
        ticket_id="p2-sunset",
        intake_result=intake,
        source_pdf_path=str(SEEDS / "CONTEXT-brasaland-request-1.pdf"),
    )
    assert handoff is not None
    result = run_response_pipeline(
        ticket_id="p2-sunset",
        handoff=handoff,
        intake_status=STATUS_INTAKE_COMPLETE,
        part2_ready=True,
    )
    assert result.error_message is None
    assert result.all_passed is True
    assert result.status == STATUS_WAITING_FOR_APPROVAL
    assert result.average_iterations <= MAX_SECTION_ITERATIONS
    depts = {r["department_id"] for r in result.section_results}
    assert depts == set(intake.departments_needed)
    for section in result.section_results:
        assert section["draft_content"]
        assert section["passed"] is True
        ev = section["evaluation_results"]
        assert ev["readability"]["passed"]
        assert ev["relevance"]["passed"]
        assert ev["compliance"]["passed"]
        for pillar in BRAND_PILLARS:
            assert pillar in section["draft_content"].casefold()


def test_pipeline_andes_skips_training() -> None:
    intake = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-2.pdf")
    handoff = route_intake_to_part2(
        ticket_id="p2-andes", intake_result=intake, source_pdf_path="x.pdf"
    )
    result = run_response_pipeline(
        ticket_id="p2-andes",
        handoff=handoff,
        intake_status=STATUS_INTAKE_COMPLETE,
        part2_ready=True,
    )
    assert result.all_passed is True
    assert "training" not in {r["department_id"] for r in result.section_results}


def test_http_generate_response_persists_drafts(client: TestClient) -> None:
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
    assert body["part2_pipeline"]["all_passed"] is True

    sections = list_sections(ticket_id)
    assert sections
    for row in sections:
        assert row.draft_content
        assert row.evaluation_results_json
        assert "readability" in row.evaluation_results_json

    detail = ticket_to_dict(get_ticket(ticket_id))  # type: ignore[arg-type]
    assert detail["part2_response"]["all_passed"] is True
    assert all(s.get("draft_content") for s in detail["department_sections"])


def test_no_pdf_reparse_required_in_part2_pipeline() -> None:
    src = (PIPELINE / "graph.py").read_text(encoding="utf-8")
    assert "reparse_pdf_required" in src
    assert "MarkItDown" not in src
    for path in PIPELINE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "MarkItDown" not in text


def test_section_loop_exhaustion_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Forced non-compliant feedback loop eventually marks exhausted."""
    from data.pipelines.rfp_response import loop as loop_mod
    from data.pipelines.rfp_response.evaluators import EvaluationResult, DimensionResult

    def always_fail(**kwargs):
        return EvaluationResult(
            department_id=kwargs["department_id"],
            passed=False,
            readability=DimensionResult("readability", True, 1.0),
            relevance=DimensionResult("relevance", True, 1.0),
            compliance=DimensionResult(
                "compliance",
                False,
                0.2,
                failures=["Missing brand pillar(s): consistent quality"],
            ),
            feedback=["Missing brand pillar(s): consistent quality"],
        )

    monkeypatch.setattr(loop_mod, "evaluate_section", always_fail)
    loop = loop_mod.run_section_loop(
        department_id="marketing",
        metadata={"client_name": "X", "location": "Y", "deadline": "2026-01-01"},
        key_aspects=["Brand terms"],
        max_iterations=2,
    )
    assert loop.exhausted is True
    assert loop.iterations == 2
    assert loop.evaluation.passed is False


def test_evaluate_section_dimensions_present() -> None:
    draft = generate_department_draft(
        department_id="operaciones",
        metadata={
            "client_name": "Andes Tech",
            "location": "Medellín",
            "service_type": "weekly catering",
        },
        key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
    ).draft_content
    result = evaluate_section(
        department_id="operaciones",
        draft_content=draft,
        key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
        metadata={"client_name": "Andes Tech"},
    )
    assert result.readability.name == "readability"
    assert result.relevance.name == "relevance"
    assert result.compliance.name == "compliance"
