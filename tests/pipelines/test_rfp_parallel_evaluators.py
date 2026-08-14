"""Parallel evaluator agents over each generated section."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from data.pipelines.rfp_intake.constants import DEPARTMENT_OPERACIONES
from data.pipelines.rfp_response.evaluators import (
    EVALUATOR_AGENTS,
    ComplianceEvaluatorAgent,
    EvaluationResult,
    ReadabilityEvaluatorAgent,
    RelevanceEvaluatorAgent,
    evaluate_section,
)
from data.pipelines.rfp_response.generator import generate_department_draft


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


def test_three_named_evaluator_agents_registered() -> None:
    names = {a.agent_name for a in EVALUATOR_AGENTS}
    dims = {a.dimension for a in EVALUATOR_AGENTS}
    assert names == {
        "readability_evaluator_agent",
        "relevance_evaluator_agent",
        "compliance_evaluator_agent",
    }
    assert dims == {"readability", "relevance", "compliance"}
    assert isinstance(EVALUATOR_AGENTS[0], ReadabilityEvaluatorAgent)
    assert isinstance(EVALUATOR_AGENTS[1], RelevanceEvaluatorAgent)
    assert isinstance(EVALUATOR_AGENTS[2], ComplianceEvaluatorAgent)


def test_evaluate_section_runs_agents_in_parallel() -> None:
    import data.pipelines.rfp_response.evaluators as ev_mod

    assert ev_mod.ThreadPoolExecutor is ThreadPoolExecutor
    src = ev_mod.__file__
    text = open(src, encoding="utf-8").read()
    assert "ThreadPoolExecutor" in text
    assert "rfp-eval" in text

    result = evaluate_section(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content=_compliant_draft(),
        key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
        metadata={"client_name": "Andes Tech", "location": "Medellín"},
    )
    assert isinstance(result, EvaluationResult)
    assert result.parallel is True
    assert result.evaluator_agents == [
        "readability_evaluator_agent",
        "relevance_evaluator_agent",
        "compliance_evaluator_agent",
    ]
    payload = result.to_dict()
    assert payload["readability"]["passed"] is True
    assert payload["relevance"]["passed"] is True
    assert payload["compliance"]["passed"] is True
    assert payload["scores"]["readability"] >= 0.6
    assert payload["parallel"] is True
    assert "library=py-readability-metrics" in result.readability.notes
    assert result.readability.evaluator_agent == "readability_evaluator_agent"
    assert result.relevance.evaluator_agent == "relevance_evaluator_agent"
    assert result.compliance.evaluator_agent == "compliance_evaluator_agent"


def test_readability_agent_uses_py_readability_metrics() -> None:
    result = evaluate_section(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content=_compliant_draft(),
        key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
        metadata={"client_name": "Andes Tech"},
    )
    joined = " ".join(result.readability.notes)
    assert "py-readability-metrics" in joined
    assert "flesch_reading_ease=" in joined or "flesch_skipped=" in joined


def test_relevance_agent_rejects_draft_that_ignores_rfp_ask() -> None:
    unrelated = (
        "# Notes\n\nThis operaciones memo talks about office plants and "
        "says nothing about the client or the catering request from Part 1. "
        "consistent quality warm experience speed of service. "
        "Offer validity period: 30 days from issuance. USD $1 and COP $1."
    )
    result = evaluate_section(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content=unrelated,
        key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
        metadata={"client_name": "Andes Tech", "location": "Medellín"},
    )
    assert result.relevance.passed is False
    joined = " ".join(result.relevance.failures).casefold()
    assert "andes tech" in joined or "key_aspects" in joined or "client" in joined
    assert result.passed is False


def test_compliance_agent_uses_context_section_5() -> None:
    bad = "We beat McDonald's. Setup in 3 business days. Price USD $100 only."
    result = evaluate_section(
        department_id="marketing",
        draft_content=bad,
        key_aspects=["Brand terms for Acme"],
        metadata={"client_name": "Acme"},
    )
    assert result.compliance.passed is False
    assert "no_competitors" in result.compliance.rule_ids
    assert "min_setup_business_days" in result.compliance.rule_ids
    assert "dual_currency" in result.compliance.rule_ids or "brand_pillars" in result.compliance.rule_ids
    assert result.compliance.evaluator_agent == "compliance_evaluator_agent"
