"""Per-department generator agents consume Part 1 summaries and write pricing sections."""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_intake import run_intake_pipeline
from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_CONTRIBUTIONS,
    DEPARTMENT_IDS,
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
    STATUS_INTAKE_COMPLETE,
)
from data.pipelines.rfp_intake.routing import route_intake_to_part2
from data.pipelines.rfp_response.agents import (
    GENERATOR_AGENTS,
    MarketingGeneratorAgent,
    OperacionesGeneratorAgent,
    Part1DepartmentSummary,
    ProcurementGeneratorAgent,
    TrainingGeneratorAgent,
    get_generator_agent,
    run_generator_agent,
)
from data.pipelines.rfp_response.generator import generate_department_draft

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"

_SECTION_MARKERS = {
    DEPARTMENT_MARKETING: (
        "exclusivity",
        "co-branding",
        "offer validity",
        "commercial",
    ),
    DEPARTMENT_OPERACIONES: (
        "kitchen",
        "cost per event",
        "setup",
        "staff",
    ),
    DEPARTMENT_PROCUREMENT: (
        "ingredient cost",
        "supplier lead",
        "usd $",
        "cop $",
    ),
    DEPARTMENT_TRAINING: (
        "certification",
        "recipe",
        "training",
        "development",
    ),
}


def test_one_generator_agent_registered_per_context_department() -> None:
    assert set(GENERATOR_AGENTS) == set(DEPARTMENT_IDS)
    assert isinstance(get_generator_agent(DEPARTMENT_MARKETING), MarketingGeneratorAgent)
    assert isinstance(get_generator_agent(DEPARTMENT_OPERACIONES), OperacionesGeneratorAgent)
    assert isinstance(get_generator_agent(DEPARTMENT_PROCUREMENT), ProcurementGeneratorAgent)
    assert isinstance(get_generator_agent(DEPARTMENT_TRAINING), TrainingGeneratorAgent)
    with pytest.raises(KeyError):
        get_generator_agent("sales")


def test_agent_rejects_summary_for_another_department() -> None:
    agent = get_generator_agent(DEPARTMENT_MARKETING)
    wrong = Part1DepartmentSummary(
        department_id=DEPARTMENT_OPERACIONES,
        key_aspects=["Operational feasibility for Acme"],
        metadata={"client_name": "Acme"},
    )
    with pytest.raises(ValueError, match="expected 'marketing'"):
        agent.receive_part1_summary(wrong)


def test_each_agent_writes_department_specific_pricing_section() -> None:
    """Each agent produces its CONTEXT §2.1 slice of the pricing proposal."""
    meta = {
        "client_name": "Sunset Bay Resorts",
        "location": "Florida",
        "service_type": "co-branded concession",
        "budget_range": "USD $60,000–75,000 / year",
        "deadline": "2026-09-01",
    }
    summaries = {
        DEPARTMENT_MARKETING: [
            "Ticket owner (Camila Ospina / Marketing-as-Sales) for Sunset Bay Resorts",
            "Exclusivity / brand terms present in RFP extract",
        ],
        DEPARTMENT_OPERACIONES: [
            "Operational feasibility for Sunset Bay Resorts @ Florida",
            "Setup/delivery timeline must be ≥10 business days",
        ],
        DEPARTMENT_PROCUREMENT: [
            "Ingredient cost / supplier lead times — keep USD $ and COP $ as written",
            "Budget range from RFP: USD $60,000–75,000 / year",
        ],
        DEPARTMENT_TRAINING: [
            "New recipe / signature-menu development time if required by RFP",
            "Certification and quality standards rollout plan",
        ],
    }
    drafts: dict[str, str] = {}
    for dept, aspects in summaries.items():
        summary = Part1DepartmentSummary(
            department_id=dept,
            key_aspects=aspects,
            metadata=meta,
        )
        result = run_generator_agent(summary)
        assert result.generator_agent == get_generator_agent(dept).agent_name
        assert result.part1_summary_used is True
        text = result.draft_content.casefold()
        drafts[dept] = text
        assert "pricing proposal" in text
        assert dept in text
        assert "sunset bay resorts" in text
        for aspect in aspects:
            assert aspect[:24].casefold() in text
        remit = DEPARTMENT_CONTRIBUTIONS[dept].split(":")[0].casefold()
        assert remit.split(",")[0].strip() in text or remit[:20] in text
        for marker in _SECTION_MARKERS[dept]:
            assert marker in text, f"{dept} missing {marker!r}"

    # Sections must not be interchangeable — ops is not a brand-terms letter
    assert "cost per event" in drafts[DEPARTMENT_OPERACIONES]
    assert "ingredient cost" in drafts[DEPARTMENT_PROCUREMENT]
    assert "exclusivity" in drafts[DEPARTMENT_MARKETING]
    assert "certification" in drafts[DEPARTMENT_TRAINING]
    assert drafts[DEPARTMENT_MARKETING] != drafts[DEPARTMENT_OPERACIONES]


def test_agents_consume_part1_handoff_workstream_summaries_not_pdf() -> None:
    intake = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-1.pdf")
    handoff = route_intake_to_part2(
        ticket_id="gen-agents-1",
        intake_result=intake,
        source_pdf_path="data/raw/rfp/gen-agents-1/file.pdf",
    )
    assert handoff is not None
    assert handoff["status"] == STATUS_INTAKE_COMPLETE

    used_agents: set[str] = set()
    for stream in handoff["work_streams"]:
        summary = Part1DepartmentSummary.from_work_stream(
            stream,
            metadata=handoff["metadata"],
            ticket_id=handoff["ticket_id"],
        )
        # This is the Part 1 summary for THIS department only
        assert summary.key_aspects == intake.sections[summary.department_id]
        result = run_generator_agent(summary)
        used_agents.add(result.generator_agent)
        assert result.department_id == stream["department_id"]
        assert "Pricing proposal section" in result.draft_content
        for aspect in summary.key_aspects:
            token = aspect[:24]
            assert token.casefold() in result.draft_content.casefold()

    expected = {get_generator_agent(d).agent_name for d in intake.departments_needed}
    assert used_agents == expected


def test_facade_still_dispatches_named_agent() -> None:
    draft = generate_department_draft(
        department_id=DEPARTMENT_PROCUREMENT,
        metadata={"client_name": "Andes Tech", "location": "Medellín"},
        key_aspects=["Ingredient cost / supplier lead times for Andes Tech"],
    )
    assert draft.generator_agent == "procurement_generator_agent"
    assert "ingredient cost" in draft.draft_content.casefold()
    assert "andes tech" in draft.draft_content.casefold()
