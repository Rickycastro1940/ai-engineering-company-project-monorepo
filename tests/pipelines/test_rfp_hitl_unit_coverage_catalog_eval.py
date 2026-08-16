"""Evaluate: unit/integration tests exist for HITL interrupt/resume, iteration limit,
arbitration, and parallel approval under interrupt.

Does not re-implement those suites — asserts the ship coverage modules and key
test names exist, then writes a catalog artifact after a live pytest collection.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ARTIFACT = Path("/opt/cursor/artifacts/rfp_hitl_unit_coverage_catalog.json")
REPO = Path(__file__).resolve().parents[2]
PIPELINES = REPO / "tests" / "pipelines"

# Capability → modules that must exist + representative test names.
REQUIRED_COVERAGE: dict[str, dict[str, object]] = {
    "interrupt_resume": {
        "modules": [
            "test_rfp_hitl_interrupt.py",
            "test_rfp_resume_from_interrupt.py",
        ],
        "tests": [
            "test_collect_approvals_interrupts_then_enters_apply_approval",
            "test_interrupt_pauses_then_resume_with_camila_approval",
            "test_resume_enters_apply_approval_without_restarting_load_handoff",
            "test_execution_resumes_from_interrupt_without_restarting_flow",
            "test_resume_without_existing_pause_does_not_restart_from_start",
        ],
    },
    "iteration_limit": {
        "modules": [
            "test_rfp_part3_guardrails.py",
            "test_rfp_iteration_limit_applied.py",
            "test_rfp_part3_interrupt_arbitration_e2e.py",
        ],
        "tests": [
            "test_bump_department_iterations_enforces_limit",
            "test_arbitration_stops_when_department_loop_exceeds_max",
            "test_iteration_limit_constant_and_helper_are_executable",
            "test_arbitration_path_applies_iteration_limit_at_runtime",
            "test_human_request_changes_path_applies_iteration_limit_at_runtime",
            "test_iteration_limit_reached_sets_needs_human_review",
            "test_human_request_changes_past_cap_sets_needs_human_review",
        ],
    },
    "arbitration": {
        "modules": [
            "test_rfp_arbitration_unit.py",
            "test_rfp_arbitration_fixed_context_eval.py",
            "test_rfp_part3_interrupt_arbitration_e2e.py",
        ],
        "tests": [
            "test_cost_vs_feasibility_surfaces_and_camila_forces_request_changes",
            "test_setup_sla_breach_felipe_is_fixed_arbiter",
            "test_ceo_threshold_blocks_synthesizer_until_mariana_approves",
            "test_arbitration_on_cost_vs_feasibility_disagreement",
            "test_arbitration_on_setup_sla_breach_disagreement",
            "test_arbitration_ceo_threshold_on_sunset_disagreement_path",
            "test_arbitration_source_is_fixed_table_not_llm_client",
        ],
    },
    "parallel_approval_under_interrupt": {
        "modules": [
            "test_rfp_hitl_interrupt.py",
            "test_rfp_part3_interrupt_arbitration_e2e.py",
            "test_rfp_pause_before_each_department.py",
        ],
        "tests": [
            "test_department_interrupt_is_per_branch_and_skips_already_done",
            "test_second_department_resume_persists_after_first_send_branch",
            "test_approve_department_b_while_a_remains_interrupted_proves_parallel_send",
            "test_sequential_resumes_each_keep_remaining_departments_paused",
        ],
    },
}


def _module_defines_tests(path: Path, names: list[str]) -> list[str]:
    src = path.read_text(encoding="utf-8")
    return [name for name in names if f"def {name}" in src]


def test_required_hitl_coverage_modules_and_tests_exist() -> None:
    catalog: dict[str, dict] = {}
    missing: list[str] = []
    for capability, spec in REQUIRED_COVERAGE.items():
        modules = list(spec["modules"])  # type: ignore[arg-type]
        tests = list(spec["tests"])  # type: ignore[arg-type]
        found_tests: list[str] = []
        module_paths: list[str] = []
        for name in modules:
            path = PIPELINES / name
            if not path.is_file():
                missing.append(f"missing module {name}")
                continue
            module_paths.append(str(path.relative_to(REPO)))
            found_tests.extend(_module_defines_tests(path, tests))
        absent = [t for t in tests if t not in found_tests]
        for name in absent:
            missing.append(f"{capability}: missing test {name}")
        catalog[capability] = {
            "modules": module_paths,
            "required_tests": tests,
            "found_tests": sorted(set(found_tests)),
        }
    assert not missing, missing

    # Live collection proves pytest discovers the coverage (not docs-only).
    targets = sorted(
        {
            str(PIPELINES / m)
            for spec in REQUIRED_COVERAGE.values()
            for m in spec["modules"]  # type: ignore[union-attr]
        }
    )
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *targets],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    collected_lines = [
        line.strip()
        for line in proc.stdout.splitlines()
        if "::" in line and line.strip().startswith("tests/")
    ]
    # pytest -q collect-only often prints "tests/...::name" or just counts;
    # fall back to scanning stdout for each required test name.
    collected_blob = proc.stdout + "\n" + proc.stderr
    for capability, spec in REQUIRED_COVERAGE.items():
        for name in spec["tests"]:  # type: ignore[union-attr]
            assert name in collected_blob, f"{capability}: pytest did not collect {name}"

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "claim": (
                    "Unit tests exist for interruption/resume, the iteration limit, "
                    "arbitration, and parallel approval under interrupt"
                ),
                "verdict": "pass",
                "catalog": catalog,
                "pytest_collect_summary": [
                    line
                    for line in proc.stdout.splitlines()
                    if "test" in line.casefold() or "selected" in line.casefold()
                ][-5:],
                "collected_line_count": len(collected_lines),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
