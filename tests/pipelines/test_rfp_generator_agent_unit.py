"""Unit tests: at least one Part 2 generator agent (synthetic Part 1 summary).

No PDF, no HTTP, no generator–evaluator loop — call the agent directly.
"""

from __future__ import annotations

from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_MARKETING,
    DEPARTMENT_OWNERS,
)
from data.pipelines.rfp_response.agents import (
    MarketingGeneratorAgent,
    Part1DepartmentSummary,
)
from data.pipelines.rfp_response.compliance_rules import SECTION_REQUIRED_HEADINGS


def test_marketing_generator_agent_unit_synthetic_no_pdf() -> None:
    """Unit: marketing_generator_agent drafts from a Part 1 summary only."""
    agent = MarketingGeneratorAgent()
    summary = Part1DepartmentSummary(
        department_id=DEPARTMENT_MARKETING,
        owner=DEPARTMENT_OWNERS[DEPARTMENT_MARKETING],
        label="Marketing and Digital Experience",
        key_aspects=[
            "Brand exclusivity for Synthetic Co co-branding partnership",
            "Offer validity window discussed in the RFP extract",
        ],
        metadata={
            "client_name": "Synthetic Co",
            "location": "Bogotá",
            "service_type": "co-branding",
            "deadline": "2026-10-15",
        },
    )

    result = agent.generate(summary)

    assert result.generator_agent == "marketing_generator_agent"
    assert result.department_id == DEPARTMENT_MARKETING
    assert result.owner == "Camila Ospina"
    assert result.part1_summary_used is True
    assert "Synthetic Co" in result.draft_content
    for heading in SECTION_REQUIRED_HEADINGS[DEPARTMENT_MARKETING]:
        assert f"## {heading}" in result.draft_content
    assert "30 days from issuance" in result.draft_content
