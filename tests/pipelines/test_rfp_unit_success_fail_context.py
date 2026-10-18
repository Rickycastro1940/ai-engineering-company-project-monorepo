"""Evaluate: unit tests cover success, generic eval-fail, and one CONTEXT §5 fail.

Three distinct unit cases (no PDF, no HTTP, no generator–evaluator loop):

1. Success — a compliant draft passes evaluation.
2. Generic evaluation-failure — readability fails without a CONTEXT §5 rule_id.
3. CONTEXT-anchored compliance failure — a draft that breaks a §5 guideline
   from CONTEXT-company.md (setup/delivery shorter than 10 business days).
"""

from __future__ import annotations

import ast
from pathlib import Path

from data.pipelines.rfp_intake.constants import DEPARTMENT_OPERACIONES
from data.pipelines.rfp_intake.context_rules import parse_context_section_5_bullets
from data.pipelines.rfp_response.compliance_rules import CONTEXT_SECTION_5_RULES
from data.pipelines.rfp_response.evaluators import (
    ComplianceEvaluatorAgent,
    EvaluatorContext,
    ReadabilityEvaluatorAgent,
    evaluate_compliance,
)
from data.pipelines.rfp_response.generator import generate_department_draft

REPO = Path(__file__).resolve().parents[2]
CONTEXT = REPO / "CONTEXT-company.md"
UNIT_DIR = REPO / "tests" / "pipelines"
EVALUATOR_UNIT = UNIT_DIR / "test_rfp_evaluator_agent_unit.py"
COMPLIANCE_FAIL_UNIT = UNIT_DIR / "test_rfp_compliance_context_failure_unit.py"
GENERATOR_UNIT = UNIT_DIR / "test_rfp_generator_agent_unit.py"
SECTION_5_RULE_IDS = {r["id"] for r in CONTEXT_SECTION_5_RULES}


def _test_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


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


def test_unit_modules_declare_success_generic_fail_and_context_fail() -> None:
    eval_names = _test_names(EVALUATOR_UNIT)
    assert any("passes" in n or "pass" in n for n in eval_names), eval_names
    assert any("generic" in n and "fail" in n for n in eval_names), eval_names
    assert any("fail" in n for n in eval_names), eval_names

    eval_src = EVALUATOR_UNIT.read_text(encoding="utf-8")
    assert "passed is True" in eval_src
    assert "ReadabilityEvaluatorAgent" in eval_src
    assert "ComplianceEvaluatorAgent" in eval_src
    assert "TestClient" not in eval_src
    assert "run_section_loop" not in eval_src

    ctx_names = _test_names(COMPLIANCE_FAIL_UNIT)
    assert any("compliance_fails" in n or "fail" in n for n in ctx_names), ctx_names
    ctx_src = COMPLIANCE_FAIL_UNIT.read_text(encoding="utf-8")
    assert "@pytest.fixture" in ctx_src
    assert "evaluate_compliance" in ctx_src
    assert "min_setup_business_days" in ctx_src
    assert "TestClient" not in ctx_src
    assert "run_section_loop" not in ctx_src

    gen_src = GENERATOR_UNIT.read_text(encoding="utf-8")
    assert "generator_agent" in gen_src
    assert "TestClient" not in gen_src


def test_unit_success_case_compliant_draft_passes() -> None:
    agent = ComplianceEvaluatorAgent()
    ctx = EvaluatorContext(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content=_compliant_draft(),
        key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
        metadata={"client_name": "Andes Tech", "location": "Medellín"},
    )
    result = agent.evaluate(ctx)
    assert result.passed is True
    assert result.name == "compliance"
    assert result.evaluator_agent == "compliance_evaluator_agent"


def test_unit_generic_evaluation_failure_is_not_a_context_section_5_rule() -> None:
    agent = ReadabilityEvaluatorAgent()
    ctx = EvaluatorContext(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content="TOO SHORT. ALL CAPS JUNK.",
        key_aspects=["Operational feasibility"],
        metadata={"client_name": "Andes Tech"},
    )
    result = agent.evaluate(ctx)
    assert result.passed is False
    assert result.name == "readability"
    assert result.failures
    assert not (set(result.rule_ids) & SECTION_5_RULE_IDS)


def test_unit_context_anchored_compliance_failure_matches_section_5() -> None:
    text = CONTEXT.read_text(encoding="utf-8")
    bullets = parse_context_section_5_bullets(text)
    guideline = next(
        r for r in CONTEXT_SECTION_5_RULES if r["id"] == "min_setup_business_days"
    )
    assert guideline["guideline"] in bullets
    assert "10 business days" in guideline["guideline"]
    assert "10 business days" in text.split("## 5. Business Constraints")[1]

    result = evaluate_compliance("Setup in 3 business days for the catering kickoff.")
    assert result.passed is False
    assert "min_setup_business_days" in result.rule_ids
    assert result.name == "compliance"


def test_the_three_unit_cases_are_distinct_outcomes() -> None:
    success = ComplianceEvaluatorAgent().evaluate(
        EvaluatorContext(
            department_id=DEPARTMENT_OPERACIONES,
            draft_content=_compliant_draft(),
            key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
            metadata={"client_name": "Andes Tech", "location": "Medellín"},
        )
    )
    generic = ReadabilityEvaluatorAgent().evaluate(
        EvaluatorContext(
            department_id=DEPARTMENT_OPERACIONES,
            draft_content="TOO SHORT. ALL CAPS JUNK.",
            key_aspects=["Operational feasibility"],
            metadata={"client_name": "Andes Tech"},
        )
    )
    context = evaluate_compliance("Setup in 3 business days for the catering kickoff.")

    assert success.passed is True
    assert generic.passed is False
    assert context.passed is False
    assert generic.name == "readability"
    assert context.name == "compliance"
    assert "min_setup_business_days" in context.rule_ids
    assert "min_setup_business_days" not in generic.rule_ids
    assert success.name != generic.name or success.passed != generic.passed
