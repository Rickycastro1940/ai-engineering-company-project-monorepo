"""Integration: Part 3 driven by fixture + simulated programmatic approvals (no UI)."""

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
from data.pipelines.rfp_intake.constants import STATUS_DONE, STATUS_WAITING_FOR_APPROVAL

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "rfp_part3_e2e_simulated_approvals.py"
ARTIFACT = Path("/opt/cursor/artifacts/rfp_part3_simulated_approvals_e2e.json")


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "part3-sim.sqlite"))
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()


def test_fixture_queued_decisions_complete_andes_without_ui() -> None:
    """Fixture + queued_decisions = simulated reviewers (programmatic resume)."""
    kwargs = andes_pipeline_kwargs()
    result = run_approval_pipeline(
        **kwargs,
        thread_id=approval_thread_id(kwargs["ticket_id"]),
        use_interrupt=True,
    )
    assert result.status == STATUS_DONE
    assert result.final_document.get("ticket_id") == ANDES_SIMULATED_TICKET_ID
    assert result.final_document.get("markdown")
    assert {s["department_id"] for s in result.final_document["sections"]} == set(
        ANDES_DEPARTMENTS
    )
    assert all(
        (result.approvals.get(d) or {}).get("approval_status") == "approved"
        for d in ANDES_DEPARTMENTS
    )


def test_fixture_sequential_resume_is_reproducible_without_ui() -> None:
    """One interrupt pause, then one programmatic resume per department."""
    ticket_id = f"{ANDES_SIMULATED_TICKET_ID}-seq"
    thread_id = approval_thread_id(ticket_id)
    base = andes_pipeline_kwargs(ticket_id=ticket_id, queued_decisions=[])
    paused = run_approval_pipeline(
        **base,
        thread_id=thread_id,
        use_interrupt=True,
    )
    assert paused.status == STATUS_WAITING_FOR_APPROVAL
    assert paused.pending_approvals
    assert not (paused.final_document or {}).get("markdown")

    current = paused
    for decision in simulated_department_approvals(ANDES_DEPARTMENTS):
        current = run_approval_pipeline(
            ticket_id=ticket_id,
            status=STATUS_WAITING_FOR_APPROVAL,
            sections=base["sections"],
            metadata=base["metadata"],
            departments_needed=list(ANDES_DEPARTMENTS),
            requires_ceo_approval=False,
            thread_id=thread_id,
            resume=decision,
            use_interrupt=True,
        )
        assert (
            current.approvals.get(decision["department_id"]) or {}
        ).get("approval_status") == "approved"

    assert current.status == STATUS_DONE
    assert current.final_document.get("markdown")
    assert "Andes Tech" in current.final_document["markdown"]


def test_fixture_sunset_includes_ceo_simulated_approval() -> None:
    result = run_approval_pipeline(
        **sunset_pipeline_kwargs(),
        thread_id=approval_thread_id(sunset_pipeline_kwargs()["ticket_id"]),
        use_interrupt=True,
    )
    assert result.status == STATUS_DONE
    assert result.final_document.get("markdown")
    assert "Mariana Restrepo" in result.final_document["markdown"]
    assert (result.ceo_approval or {}).get("approval_status") == "approved"


def test_script_rfp_part3_e2e_simulated_approvals_is_reproducible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ship path: ``uv run python scripts/rfp_part3_e2e_simulated_approvals.py``."""
    assert SCRIPT.is_file()
    out = tmp_path / "part3-sim-out.json"
    ckpt = tmp_path / "script-ckpt.sqlite"
    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "RFP_ALLOW_SQLITE": "1",
        "RFP_CHECKPOINT_SQLITE": str(ckpt),
    }
    env.pop("RFP_CHECKPOINT_MEMORY", None)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--scenario",
            "andes",
            "--mode",
            "sequential",
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
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["mode"] == "sequential"
    assert payload["result"]["status"] == STATUS_DONE
    assert payload["thread_id"].startswith("RFP-")
    assert "resume_marketing" in {s["step"] for s in payload["steps"]}

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_script_sunset_queued_simulated_approvals_includes_ceo(
    tmp_path: Path,
) -> None:
    out = tmp_path / "sunset-queued.json"
    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "RFP_ALLOW_SQLITE": "1",
        "RFP_CHECKPOINT_SQLITE": str(tmp_path / "sunset-ckpt.sqlite"),
    }
    env.pop("RFP_CHECKPOINT_MEMORY", None)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--scenario",
            "sunset",
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
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["scenario"] == "sunset"
    assert payload["result"]["status"] == STATUS_DONE
    assert "Mariana Restrepo" in (payload["result"].get("final_document") or {}).get(
        "markdown", ""
    )