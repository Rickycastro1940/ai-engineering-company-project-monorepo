"""Evaluate: unit tests exist for classifier_agent and at least one department worker.

Milestone 9 Part 1 checklist item — pure/agent unit coverage under tests/pipelines/.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLASSIFIER_UNIT = REPO / "tests" / "pipelines" / "test_rfp_classifier_unit.py"
WORKER_UNIT = REPO / "tests" / "pipelines" / "test_rfp_worker_agent.py"


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


def test_unit_modules_are_not_http_integration_tests() -> None:
    """Unit modules must not spin up FastAPI / TestClient."""
    for path in (CLASSIFIER_UNIT, WORKER_UNIT):
        src = path.read_text(encoding="utf-8")
        assert "TestClient" not in src
        assert "FastAPI" not in src
        assert "/rfp/tickets" not in src
