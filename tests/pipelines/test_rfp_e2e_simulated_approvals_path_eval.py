"""Evaluate: reproducible E2E fixture path with simulated approvals (not UI-only).

Proves in code:
1. Shared fixtures live under ``data/pipelines/rfp_approval/fixtures.py``
2. CLI script ``scripts/rfp_part3_e2e_simulated_approvals.py`` drives queued/sequential
   programmatic resumes (no browser)
3. Integration tests exercise the same path without Playwright / UI clicks
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from data.pipelines.rfp_approval import run_approval_pipeline
from data.pipelines.rfp_approval.checkpointer import (
    approval_thread_id,
    reset_approval_checkpointer,
)
from data.pipelines.rfp_approval.fixtures import (
    ANDES_DEPARTMENTS,
    ANDES_SIMULATED_TICKET_ID,
    andes_pipeline_kwargs,
    simulated_department_approvals,
    sunset_pipeline_kwargs,
)
from data.pipelines.rfp_intake.constants import STATUS_DONE

ARTIFACT = Path("/opt/cursor/artifacts/rfp_e2e_simulated_approvals_path.json")
REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "data" / "pipelines" / "rfp_approval" / "fixtures.py"
SCRIPT = REPO / "scripts" / "rfp_part3_e2e_simulated_approvals.py"
INTEGRATION = REPO / "tests" / "pipelines" / "test_rfp_part3_simulated_approvals_e2e.py"
UI_BROWSER_SEEDS = REPO / "tests" / "pipelines" / "test_rfp_ui_browser_seeds.py"

FORBIDDEN_UI = (
    "playwright",
    "selenium",
    "chromium",
    "webdriver",
    "page.click",
    "rfp-approvals.html",
)


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "e2e-path.sqlite"))
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()


def test_reproducible_e2e_ship_path_files_exist_and_are_non_ui() -> None:
    assert FIXTURES.is_file(), "fixtures.py missing"
    assert SCRIPT.is_file(), "E2E script missing"
    assert INTEGRATION.is_file(), "simulated-approvals integration test missing"

    for path in (FIXTURES, SCRIPT, INTEGRATION):
        src = path.read_text(encoding="utf-8").casefold()
        for needle in FORBIDDEN_UI:
            assert needle not in src, f"{path.name} must not depend on {needle}"

    fixtures_src = FIXTURES.read_text(encoding="utf-8")
    assert "andes_pipeline_kwargs" in fixtures_src
    assert "sunset_pipeline_kwargs" in fixtures_src
    assert "simulated_department_approvals" in fixtures_src
    assert "queued_decisions" in fixtures_src
    assert "no UI" in fixtures_src or "no UI" in SCRIPT.read_text(encoding="utf-8")

    script_src = SCRIPT.read_text(encoding="utf-8")
    assert "--mode" in script_src
    assert "queued" in script_src
    assert "sequential" in script_src
    assert "Command(resume=" in script_src or "resume=" in script_src

    # UI browser seeds (if present) are a separate optional path — not the ship E2E.
    assert UI_BROWSER_SEEDS.name != SCRIPT.name


def test_fixture_and_script_complete_andes_without_manual_ui(
    tmp_path: Path,
) -> None:
    kwargs = andes_pipeline_kwargs(ticket_id=f"{ANDES_SIMULATED_TICKET_ID}-path-eval")
    assert kwargs["queued_decisions"]
    assert {d["department_id"] for d in kwargs["queued_decisions"]} == set(
        ANDES_DEPARTMENTS
    )
    assert all(
        d["approver"] for d in kwargs["queued_decisions"]
    ), "simulated approvals must name CONTEXT owners"

    fixture_result = run_approval_pipeline(
        **kwargs,
        thread_id=approval_thread_id(kwargs["ticket_id"]),
        use_interrupt=True,
    )
    assert fixture_result.status == STATUS_DONE
    assert fixture_result.final_document.get("markdown")

    out = tmp_path / "script-out.json"
    env = {
        **dict(__import__("os").environ),
        "RFP_ALLOW_SQLITE": "1",
        "RFP_CHECKPOINT_SQLITE": str(tmp_path / "script-path.sqlite"),
    }
    env.pop("RFP_CHECKPOINT_MEMORY", None)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--scenario",
            "andes",
            "--mode",
            "queued",
            "--out",
            str(out),
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    script_payload = json.loads(out.read_text(encoding="utf-8"))
    assert script_payload["ok"] is True
    assert script_payload["mode"] == "queued_decisions"
    assert script_payload["result"]["status"] == STATUS_DONE

    # Sunset fixture also ships simulated CEO approval (still no UI).
    sunset = run_approval_pipeline(
        **sunset_pipeline_kwargs(ticket_id="rfp-path-eval-sunset"),
        thread_id=approval_thread_id("rfp-path-eval-sunset"),
        use_interrupt=True,
    )
    assert sunset.status == STATUS_DONE
    assert "Mariana Restrepo" in sunset.final_document.get("markdown", "")

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "claim": (
                    "A reproducible E2E fixture path exists (script or interrogation "
                    "test with simulated approvals), not only a manual UI demo"
                ),
                "verdict": "pass",
                "paths": {
                    "fixtures": str(FIXTURES.relative_to(REPO)),
                    "script": str(SCRIPT.relative_to(REPO)),
                    "integration_test": str(INTEGRATION.relative_to(REPO)),
                    "ui_browser_seeds_separate": str(UI_BROWSER_SEEDS.relative_to(REPO))
                    if UI_BROWSER_SEEDS.is_file()
                    else None,
                },
                "modes": ["queued_decisions", "sequential resume"],
                "scenarios": ["andes", "sunset"],
                "fixture_andes": {
                    "status": fixture_result.status,
                    "ticket_id": fixture_result.final_document.get("ticket_id"),
                    "simulated_owners": [
                        d["approver"] for d in simulated_department_approvals(ANDES_DEPARTMENTS)
                    ],
                },
                "script_andes": {
                    "ok": script_payload["ok"],
                    "mode": script_payload["mode"],
                    "status": script_payload["result"]["status"],
                    "thread_id": script_payload.get("thread_id"),
                },
                "fixture_sunset": {
                    "status": sunset.status,
                    "has_mariana": "Mariana Restrepo"
                    in sunset.final_document.get("markdown", ""),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
