"""Evaluate: unit tests exist for classifier, workers, and Part 2 agents.

Milestone 9 checklist — pure/agent unit coverage under tests/pipelines/.
Part 1: classifier_agent + at least one department worker.
Part 2: at least one generator agent + one evaluator agent, plus a
CONTEXT-company.md compliance-failure case (evaluation fails).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLASSIFIER_UNIT = REPO / "tests" / "pipelines" / "test_rfp_classifier_unit.py"
WORKER_UNIT = REPO / "tests" / "pipelines" / "test_rfp_worker_agent.py"
GENERATOR_UNIT = REPO / "tests" / "pipelines" / "test_rfp_generator_agent_unit.py"
EVALUATOR_UNIT = REPO / "tests" / "pipelines" / "test_rfp_evaluator_agent_unit.py"
COMPLIANCE_FAIL_UNIT = (
    REPO / "tests" / "pipelines" / "test_rfp_compliance_context_failure_unit.py"
)


def _test_function_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


def test_classifier_unit_module_exists_with_seed_and_synthetic_cases() -> None:
    assert CLASSIFIER_UNIT.is_file()
    names = _test_function_names(CLASSIFIER_UNIT)
    assert any("classifier" in n for n in names)
    assert any("seed" in n or "context_seed" in n for n in names)
    assert any("synthetic" in n for n in names)
    src = CLASSIFIER_UNIT.read_text(encoding="utf-8")
    assert "classifier_agent" in src
    assert "CONTEXT-brasaland-request-1.pdf" in src
    assert "CONTEXT-brasaland-request-3.pdf" in src


def test_worker_unit_module_covers_at_least_marketing() -> None:
    assert WORKER_UNIT.is_file()
    names = _test_function_names(WORKER_UNIT)
    assert any("marketing_worker" in n for n in names), names
    src = WORKER_UNIT.read_text(encoding="utf-8")
    assert "department_worker" in src
    assert "key_aspects" in src
    # At least one pure synthetic worker unit (no PDF required)
    assert "synthetic" in src.casefold()


def test_generator_agent_unit_module_exists() -> None:
    assert GENERATOR_UNIT.is_file()
    names = _test_function_names(GENERATOR_UNIT)
    assert any("generator_agent" in n for n in names), names
    src = GENERATOR_UNIT.read_text(encoding="utf-8")
    assert "MarketingGeneratorAgent" in src or "generator_agent" in src
    assert "Part1DepartmentSummary" in src
    assert "TestClient" not in src
    assert "run_section_loop" not in src


def test_evaluator_agent_unit_module_includes_failure_case() -> None:
    assert EVALUATOR_UNIT.is_file()
    names = _test_function_names(EVALUATOR_UNIT)
    assert any("evaluator_agent" in n for n in names), names
    assert any("fail" in n for n in names), names
    assert any("generic" in n for n in names), names
    src = EVALUATOR_UNIT.read_text(encoding="utf-8")
    assert "ComplianceEvaluatorAgent" in src or "EvaluatorAgent" in src
    assert "ReadabilityEvaluatorAgent" in src
    assert "passed is True" in src
    assert "passed is False" in src
    assert "TestClient" not in src
    assert "run_section_loop" not in src


def test_compliance_failure_unit_is_one_context_rule_fixture() -> None:
    """Small CONTEXT §5 fail case: one fixture, assertion on compliance.passed."""
    assert COMPLIANCE_FAIL_UNIT.is_file()
    src = COMPLIANCE_FAIL_UNIT.read_text(encoding="utf-8")
    assert "@pytest.fixture" in src
    assert "evaluate_compliance" in src
    assert "passed is False" in src
    assert "min_setup_business_days" in src
    assert "CONTEXT" in src or "10 business days" in src or "setup" in src.casefold()
    assert "run_section_loop" not in src
    assert "TestClient" not in src


def test_unit_modules_are_not_http_integration_tests() -> None:
    """Unit modules must not spin up FastAPI / TestClient."""
    for path in (
        CLASSIFIER_UNIT,
        WORKER_UNIT,
        GENERATOR_UNIT,
        EVALUATOR_UNIT,
        COMPLIANCE_FAIL_UNIT,
    ):
        src = path.read_text(encoding="utf-8")
        assert "TestClient" not in src
        assert "FastAPI" not in src
        assert "/rfp/tickets" not in src
