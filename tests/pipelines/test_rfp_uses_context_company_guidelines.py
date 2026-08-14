"""Evaluate: Part 2 uses CONTEXT-company.md guidelines and section formats.

Source of truth is CONTEXT-company.md (not a generic SaaS RFP schema):
- §2.1 contribution column → ``##`` headings per department
- §5 business constraints → compliance evaluator catalog
- §6 Part 2 deliverable → generate + evaluate readability/relevance/compliance
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_intake import run_intake_pipeline
from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_CONTRIBUTIONS,
    DEPARTMENT_IDS,
    DEPARTMENT_OWNERS,
    STATUS_INTAKE_COMPLETE,
)
from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_BRAND_PILLARS,
    CONTEXT_CEO_NAME,
    CONTEXT_MIN_SETUP_BUSINESS_DAYS,
    CONTEXT_OFFER_VALIDITY_PHRASE,
    CONTEXT_SECTION_5_GUIDELINES,
    CONTEXT_SECTION_REQUIRED_HEADINGS,
    parse_context_department_table,
    parse_context_section_5_bullets,
    read_context_company_md,
    section_headings_from_contribution,
)
from data.pipelines.rfp_intake.routing import route_intake_to_part2
from data.pipelines.rfp_response import run_response_pipeline
from data.pipelines.rfp_response.agents import GENERATOR_AGENTS, get_generator_agent
from data.pipelines.rfp_response.compliance_rules import (
    BRAND_PILLARS,
    CEO_NAME,
    CONTEXT_SECTION_5_RULES,
    MIN_SETUP_BUSINESS_DAYS,
    OFFER_VALIDITY_PHRASE,
    SECTION_OWNERS,
    SECTION_REQUIRED_HEADINGS,
)
from data.pipelines.rfp_response.evaluators import (
    evaluate_compliance,
    evaluate_relevance,
    evaluate_section,
)
from data.pipelines.rfp_response.generator import generate_department_draft

REPO = Path(__file__).resolve().parents[2]
CONTEXT = REPO / "CONTEXT-company.md"
SEEDS = REPO / "rfp-requests" / "brasaland"

GENERIC_SAAS_HEADINGS = ("## SLA credits", "## SOC 2", "## Implementation timeline")
SUNSET_META = {
    "client_name": "Sunset Bay Resorts",
    "location": "Florida",
    "service_type": "co-branded concession",
    "deadline": "2026-09-01",
    "budget_range": "USD $60,000–75,000 / year",
    "estimated_contract_value_usd": 75_000,
    "requires_ceo_approval": True,
}


def test_context_company_md_defines_formats_and_guidelines() -> None:
    text = read_context_company_md()
    assert CONTEXT.is_file()
    assert "### 2.1 Departments Involved in the Proposal" in text
    assert "## 5. Business Constraints" in text
    part2 = text.split("## 6. Expected Deliverables")[1].split("## 7.")[0]
    assert "Part 2" in part2
    assert "readability" in part2.casefold()
    assert "relevance" in part2.casefold()
    assert "compliance" in part2.casefold()
    assert "guidelines in section 5" in part2.casefold()


def test_section_5_guidelines_are_verbatim_in_compliance_catalog() -> None:
    bullets = parse_context_section_5_bullets()
    assert bullets == CONTEXT_SECTION_5_GUIDELINES
    assert len(bullets) == 6
    assert tuple(r["guideline"] for r in CONTEXT_SECTION_5_RULES) == bullets
    assert BRAND_PILLARS == CONTEXT_BRAND_PILLARS == (
        "consistent quality",
        "warm experience",
        "speed of service",
    )
    assert MIN_SETUP_BUSINESS_DAYS == CONTEXT_MIN_SETUP_BUSINESS_DAYS == 10
    assert OFFER_VALIDITY_PHRASE == CONTEXT_OFFER_VALIDITY_PHRASE == "30 days from issuance"
    assert CEO_NAME == CONTEXT_CEO_NAME == "Mariana Restrepo"
    src = (REPO / "data" / "pipelines" / "rfp_response" / "evaluators.py").read_text(
        encoding="utf-8"
    )
    assert "for rule in CONTEXT_SECTION_5_RULES" in src
    assert "GDPR" not in src
    assert "ISO 27001" not in src


def test_section_2_1_contribution_column_is_the_section_format() -> None:
    rows = parse_context_department_table()
    assert [r["department_id"] for r in rows] == [
        "marketing",
        "operaciones",
        "procurement",
        "training",
    ]
    for row in rows:
        dept = row["department_id"]
        headings = section_headings_from_contribution(dept, row["contribution"])
        assert CONTEXT_SECTION_REQUIRED_HEADINGS[dept] == headings
        assert SECTION_REQUIRED_HEADINGS[dept] == headings
        assert SECTION_OWNERS[dept] == row["owner"] == DEPARTMENT_OWNERS[dept]
        assert set(GENERATOR_AGENTS) == set(DEPARTMENT_IDS)

    assert SECTION_REQUIRED_HEADINGS["marketing"] == (
        "Brand terms",
        "Exclusivity",
        "Co-branding",
        "Offer validity period",
    )
    assert SECTION_REQUIRED_HEADINGS["operaciones"] == (
        "Kitchen/staff capacity",
        "Setup times",
        "Cost per event",
    )
    assert SECTION_REQUIRED_HEADINGS["procurement"] == (
        "Estimated ingredient cost based on volume",
        "Supplier lead times",
    )
    assert SECTION_REQUIRED_HEADINGS["training"] == (
        "New recipe or standard",
        "Development and certification time needed",
    )


@pytest.mark.parametrize("department_id", sorted(DEPARTMENT_IDS))
def test_generator_emits_context_format_not_generic_saas(department_id: str) -> None:
    agent = get_generator_agent(department_id)
    draft = generate_department_draft(
        department_id=department_id,
        metadata=SUNSET_META,
        key_aspects=[
            DEPARTMENT_CONTRIBUTIONS[department_id],
            "Sunset Bay Resorts co-branded concession in Florida",
        ],
    ).draft_content
    assert agent.agent_name == f"{department_id}_generator_agent"
    assert DEPARTMENT_OWNERS[department_id] in draft
    for heading in SECTION_REQUIRED_HEADINGS[department_id]:
        assert f"## {heading}" in draft, f"{department_id} missing CONTEXT heading {heading!r}"
    for banned in GENERIC_SAAS_HEADINGS:
        assert banned not in draft
    for pillar in CONTEXT_BRAND_PILLARS:
        assert pillar in draft.casefold()
    assert CONTEXT_OFFER_VALIDITY_PHRASE in draft
    assert "10 business days" in draft or "never shorter than 10" in draft.casefold()


@pytest.mark.parametrize("department_id", sorted(DEPARTMENT_IDS))
def test_generated_section_passes_context_evaluators(department_id: str) -> None:
    aspects = [
        DEPARTMENT_CONTRIBUTIONS[department_id],
        "Sunset Bay Resorts co-branded concession in Florida",
    ]
    draft = generate_department_draft(
        department_id=department_id,
        metadata=SUNSET_META,
        key_aspects=aspects,
    ).draft_content
    result = evaluate_section(
        department_id=department_id,
        draft_content=draft,
        key_aspects=aspects,
        metadata=SUNSET_META,
    )
    assert result.readability.passed is True
    assert result.relevance.passed is True
    assert result.compliance.passed is True
    assert result.passed is True
    assert "context_section_2_1_format_ok" in result.relevance.notes


def test_relevance_requires_context_2_1_headings() -> None:
    generic = """
# Executive summary
## Implementation timeline
## SLA credits
## SOC 2 Type II
Client: Sunset Bay Resorts. Florida co-branded concession.
consistent quality warm experience speed of service.
Offer validity period: 30 days from issuance. USD $1 and COP $1.
"""
    result = evaluate_relevance(
        generic,
        department_id="operaciones",
        key_aspects=["Operational feasibility for Sunset Bay"],
        metadata=SUNSET_META,
    )
    assert result.passed is False
    joined = " ".join(result.failures).casefold()
    assert "context §2.1" in joined
    assert "kitchen/staff capacity" in joined or "heading" in joined


def test_compliance_fails_when_a_context_section_5_guideline_is_broken() -> None:
    bullets = parse_context_section_5_bullets()
    setup_bullet = next(b for b in bullets if "10 business days" in b)
    assert setup_bullet == next(
        r["guideline"] for r in CONTEXT_SECTION_5_RULES if r["id"] == "min_setup_business_days"
    )
    result = evaluate_compliance(
        "Setup in 3 business days. Price USD $100 only. We beat El Corral.",
        metadata={},
    )
    assert result.passed is False
    assert "min_setup_business_days" in result.rule_ids
    assert "dual_currency" in result.rule_ids
    assert "no_competitors" in result.rule_ids


def test_pipeline_uses_context_formats_on_andes_handoff() -> None:
    intake = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-2.pdf")
    assert intake.status == STATUS_INTAKE_COMPLETE
    handoff = route_intake_to_part2(
        ticket_id="ctx-andes",
        intake_result=intake,
        source_pdf_path="andes.pdf",
    )
    result = run_response_pipeline(
        ticket_id="ctx-andes",
        handoff=handoff,
        intake_status=STATUS_INTAKE_COMPLETE,
        part2_ready=True,
    )
    assert result.error_message is None
    assert result.all_passed is True
    depts = {row["department_id"] for row in result.section_results}
    assert "training" not in depts
    for row in result.section_results:
        dept = row["department_id"]
        draft = row["draft_content"]
        owner = DEPARTMENT_OWNERS[dept]
        assert owner in draft
        for heading in SECTION_REQUIRED_HEADINGS[dept]:
            assert f"## {heading}" in draft
        ev = row["evaluation_results"]
        assert ev["readability"]["passed"] is True
        assert ev["relevance"]["passed"] is True
        assert ev["compliance"]["passed"] is True
        for banned in GENERIC_SAAS_HEADINGS:
            assert banned not in draft
