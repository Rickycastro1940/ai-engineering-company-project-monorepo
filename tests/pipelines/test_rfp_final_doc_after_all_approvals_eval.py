"""Evaluate: FinalDocument is generated automatically only after every approval.

Proves in code (not docs alone):
1. ``synthesizer_node`` calls ``synthesizer_ready`` *before* ``build_final_document``
2. Partial owner approvals leave no FinalDocument (status stays waiting)
3. Once every active department (and CEO when required) approves, synthesis
   runs automatically — no separate generate step — and status becomes ``done``
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from data.pipelines.rfp_approval import run_approval_pipeline
from data.pipelines.rfp_approval.approvers import DEPARTMENT_OWNERS
from data.pipelines.rfp_approval.checkpointer import (
    approval_thread_id,
    reset_approval_checkpointer,
)
from data.pipelines.rfp_approval.fixtures import (
    andes_pipeline_kwargs,
    sunset_pipeline_kwargs,
)
from data.pipelines.rfp_approval.graph import (
    invoke_rfp_approval_graph,
    synthesizer_node,
)
from data.pipelines.rfp_approval.synthesizer import synthesizer_ready
from data.pipelines.rfp_intake.constants import STATUS_DONE, STATUS_WAITING_FOR_APPROVAL

ARTIFACT = Path("/opt/cursor/artifacts/rfp_final_doc_after_all_approvals.json")


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "final-after-all.sqlite"))
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()


def test_synthesizer_source_gates_build_behind_ready_check() -> None:
    src = inspect.getsource(synthesizer_node)
    ready_at = src.index("synthesizer_ready(")
    build_at = src.index("build_final_document(")
    assert ready_at < build_at, "build_final_document must follow synthesizer_ready"
    assert "if not ready:" in src
    assert '"final_document": {}' in src or "'final_document': {}" in src


def test_synthesizer_ready_blocks_until_every_department_approved() -> None:
    depts = ["marketing", "operaciones", "procurement"]
    # None approved
    ready, reason = synthesizer_ready(
        department_approvals={d: "pending" for d in depts},
        departments_needed=depts,
        requires_ceo=False,
        ceo_approval_status=None,
    )
    assert ready is False
    assert "marketing" in reason

    # Two of three
    ready, reason = synthesizer_ready(
        department_approvals={
            "marketing": "approved",
            "operaciones": "approved",
            "procurement": "pending",
        },
        departments_needed=depts,
        requires_ceo=False,
        ceo_approval_status=None,
    )
    assert ready is False
    assert "procurement" in reason

    # All departments, but CEO still required
    ready, reason = synthesizer_ready(
        department_approvals={d: "approved" for d in depts},
        departments_needed=depts,
        requires_ceo=True,
        ceo_approval_status="pending",
    )
    assert ready is False
    assert "CEO" in reason or "Mariana" in reason

    # Every required sign-off
    ready, reason = synthesizer_ready(
        department_approvals={d: "approved" for d in depts},
        departments_needed=depts,
        requires_ceo=False,
        ceo_approval_status=None,
    )
    assert ready is True
    assert reason == ""


def test_incremental_approvals_no_final_doc_until_last_owner() -> None:
    """Approve one department at a time — FinalDocument only after the last."""
    kwargs = andes_pipeline_kwargs(
        ticket_id="eval-final-incremental",
        queued_decisions=[],
    )
    thread_id = approval_thread_id(kwargs["ticket_id"])
    invoke_kwargs = {k: v for k, v in kwargs.items() if k != "queued_decisions"}
    depts = list(kwargs["departments_needed"])

    paused = invoke_rfp_approval_graph(
        **invoke_kwargs,
        use_interrupt=True,
        thread_id=thread_id,
    )
    assert paused.get("status") == STATUS_WAITING_FOR_APPROVAL
    assert not (paused.get("final_document") or {}).get("markdown")
    assert not (paused.get("final_document") or {}).get("ticket_id")

    snapshots: list[dict] = []
    for i, dept in enumerate(depts):
        current = invoke_rfp_approval_graph(
            **invoke_kwargs,
            use_interrupt=True,
            thread_id=thread_id,
            resume={
                "department_id": dept,
                "decision": "approved",
                "approver": DEPARTMENT_OWNERS[dept],
            },
        )
        doc = current.get("final_document") or {}
        last = i == len(depts) - 1
        snapshots.append(
            {
                "after_approving": dept,
                "approved_so_far": depts[: i + 1],
                "status": current.get("status"),
                "has_final_document": bool(doc.get("markdown") or doc.get("ticket_id")),
                "final_ticket_id": doc.get("ticket_id"),
            }
        )
        if not last:
            assert current.get("status") == STATUS_WAITING_FOR_APPROVAL
            assert not doc.get("markdown")
            assert not doc.get("ticket_id")
            synth = [
                e
                for e in (current.get("trace") or [])
                if e.get("node") == "synthesizer"
                and (e.get("output") or {}).get("completion")
                == "consolidated_approved_sections"
            ]
            assert not synth
        else:
            assert current.get("status") == STATUS_DONE
            assert doc.get("ticket_id") == kwargs["ticket_id"]
            assert doc.get("markdown")
            assert {s["department_id"] for s in doc["sections"]} == set(depts)
            assert all(s.get("approval_status") == "approved" for s in doc["sections"])
            synth = [
                e for e in (current.get("trace") or []) if e.get("node") == "synthesizer"
            ]
            assert synth
            assert synth[-1]["output"].get("completion") == (
                "consolidated_approved_sections"
            )

    # Full auto paths (Andes + Sunset) for the same claim.
    andes = run_approval_pipeline(**andes_pipeline_kwargs(ticket_id="eval-final-andes"))
    assert andes.status == STATUS_DONE
    assert andes.final_document.get("ticket_id") == "eval-final-andes"

    sunset_kw = sunset_pipeline_kwargs(include_ceo=False)
    sunset_kw["ticket_id"] = "eval-final-sunset-no-ceo"
    blocked = run_approval_pipeline(**sunset_kw)
    assert blocked.status == STATUS_WAITING_FOR_APPROVAL
    assert not (blocked.final_document or {}).get("markdown")

    sunset = run_approval_pipeline(
        **sunset_pipeline_kwargs(ticket_id="eval-final-sunset-full")
    )
    assert sunset.status == STATUS_DONE
    assert sunset.final_document.get("ticket_id") == "eval-final-sunset-full"
    assert "Mariana Restrepo" in sunset.final_document.get("markdown", "")

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "claim": (
                    "The final document is generated automatically only once "
                    "every department has given approval"
                ),
                "verdict": "pass",
                "gate": "synthesizer_ready → build_final_document (automatic)",
                "incremental_andes": snapshots,
                "andes_full": {
                    "status": andes.status,
                    "final_ticket_id": andes.final_document.get("ticket_id"),
                    "section_ids": [
                        s["department_id"] for s in andes.final_document["sections"]
                    ],
                },
                "sunset_without_ceo": {
                    "status": blocked.status,
                    "has_final_document": bool(
                        (blocked.final_document or {}).get("markdown")
                    ),
                },
                "sunset_with_ceo": {
                    "status": sunset.status,
                    "final_ticket_id": sunset.final_document.get("ticket_id"),
                    "has_mariana": "Mariana Restrepo"
                    in sunset.final_document.get("markdown", ""),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )