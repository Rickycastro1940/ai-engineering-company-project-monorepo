"""One CONTEXT-company.md §5 compliance-failure case.

Keep it small: one fixture, one assertion on fail — no generator–evaluator loop.
Guideline: no section may promise setup/delivery shorter than 10 business days.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_intake.context_rules import parse_context_section_5_bullets
from data.pipelines.rfp_response.compliance_rules import CONTEXT_SECTION_5_RULES
from data.pipelines.rfp_response.evaluators import evaluate_compliance

CONTEXT = Path(__file__).resolve().parents[2] / "CONTEXT-company.md"


@pytest.fixture
def draft_that_promises_setup_in_three_days() -> str:
    """Draft that promises a setup time CONTEXT §5 forbids (< 10 business days)."""
    return "Setup in 3 business days for the catering kickoff."


def test_compliance_fails_when_setup_under_ten_business_days(
    draft_that_promises_setup_in_three_days: str,
) -> None:
    guideline = next(
        r for r in CONTEXT_SECTION_5_RULES if r["id"] == "min_setup_business_days"
    )
    bullets = parse_context_section_5_bullets(CONTEXT.read_text(encoding="utf-8"))
    assert guideline["guideline"] in bullets
    assert "10 business days" in guideline["guideline"]

    result = evaluate_compliance(draft_that_promises_setup_in_three_days)
    assert result.passed is False
    assert "min_setup_business_days" in result.rule_ids
