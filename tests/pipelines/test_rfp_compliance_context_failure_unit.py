"""One CONTEXT-company.md §5 compliance-failure case.

Keep it small: one fixture, one assertion on fail — no generator–evaluator loop.
Guideline: no section may promise setup/delivery shorter than 10 business days.
"""

from __future__ import annotations

import pytest

from data.pipelines.rfp_response.evaluators import evaluate_compliance


@pytest.fixture
def draft_that_promises_setup_in_three_days() -> str:
    """Draft that promises a setup time CONTEXT §5 forbids (< 10 business days)."""
    return "Setup in 3 business days for the catering kickoff."


def test_compliance_fails_when_setup_under_ten_business_days(
    draft_that_promises_setup_in_three_days: str,
) -> None:
    result = evaluate_compliance(draft_that_promises_setup_in_three_days)
    assert result.passed is False
