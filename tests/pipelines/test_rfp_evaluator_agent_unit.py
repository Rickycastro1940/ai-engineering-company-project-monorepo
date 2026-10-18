"""Unit tests: at least one Part 2 evaluator agent, including a failing evaluation.

No PDF, no HTTP, no generator–evaluator loop — call the agent directly.
"""

from __future__ import annotations

from data.pipelines.rfp_intake.constants import DEPARTMENT_OPERACIONES
from data.pipelines.rfp_response.evaluators import (
    ComplianceEvaluatorAgent,
    EvaluatorContext,
    ReadabilityEvaluatorAgent,
)
from data.pipelines.rfp_response.generator import generate_department_draft


def test_compliance_evaluator_agent_unit_passes_context_compliant_draft() -> None:
    """Unit: compliance_evaluator_agent accepts a CONTEXT §5-compliant section."""
    agent = ComplianceEvaluatorAgent()
    draft = generate_department_draft(
        department_id=DEPARTMENT_OPERACIONES,
        metadata={
            "client_name": "Andes Tech",
            "location": "Medellín",
            "service_type": "weekly catering",
        },
        key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
    ).draft_content
    ctx = EvaluatorContext(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content=draft,
        key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
        metadata={"client_name": "Andes Tech", "location": "Medellín"},
    )

    result = agent.evaluate(ctx)

    assert result.evaluator_agent == "compliance_evaluator_agent"
    assert result.name == "compliance"
    assert result.passed is True


def test_readability_evaluator_agent_unit_generic_evaluation_fails() -> None:
    """Unit: generic evaluation failure (readability), not a CONTEXT §5 rule_id."""
    agent = ReadabilityEvaluatorAgent()
    ctx = EvaluatorContext(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content="TOO SHORT. ALL CAPS JUNK.",
        key_aspects=["Operational feasibility for Andes Tech"],
        metadata={"client_name": "Andes Tech"},
    )

    result = agent.evaluate(ctx)

    assert result.evaluator_agent == "readability_evaluator_agent"
    assert result.name == "readability"
    assert result.passed is False
    assert result.failures
    assert not result.rule_ids


def test_compliance_evaluator_agent_unit_evaluation_fails() -> None:
    """Unit: evaluation fails when the draft breaks a CONTEXT §5 guideline."""
    agent = ComplianceEvaluatorAgent()
    ctx = EvaluatorContext(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content="Setup in 3 business days. Price USD $100 only.",
        key_aspects=["Operational feasibility for Andes Tech"],
        metadata={"client_name": "Andes Tech"},
    )

    result = agent.evaluate(ctx)

    assert result.evaluator_agent == "compliance_evaluator_agent"
    assert result.passed is False
    assert "min_setup_business_days" in result.rule_ids
