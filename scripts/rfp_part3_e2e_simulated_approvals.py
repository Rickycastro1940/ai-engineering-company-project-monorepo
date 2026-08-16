#!/usr/bin/env python3
"""Reproducible Part 3 E2E: simulated named-owner approvals (no UI clicks).

Drives HITL pause + programmatic ``Command(resume=)`` equivalents via
``queued_decisions`` / sequential ``resume=`` on a durable checkpointer.

Usage::

    RFP_ALLOW_SQLITE=1 RFP_CHECKPOINT_SQLITE=/tmp/rfp-part3-e2e.sqlite \\
      uv run python scripts/rfp_part3_e2e_simulated_approvals.py

    # Sequential resumes (one department at a time), still no UI:
    uv run python scripts/rfp_part3_e2e_simulated_approvals.py --mode sequential

    # Sunset Bay + CEO Mariana Restrepo:
    uv run python scripts/rfp_part3_e2e_simulated_approvals.py --scenario sunset
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _ensure_env() -> Path:
    """File-backed SQLite checkpointer so interrupt/resume is durable and repeatable."""
    os.environ.setdefault("RFP_ALLOW_SQLITE", "1")
    ckpt = os.environ.get("RFP_CHECKPOINT_SQLITE")
    if not ckpt:
        path = Path(tempfile.gettempdir()) / f"rfp-part3-e2e-{uuid4().hex}.sqlite"
        os.environ["RFP_CHECKPOINT_SQLITE"] = str(path)
        ckpt = str(path)
    os.environ.pop("RFP_CHECKPOINT_MEMORY", None)
    return Path(ckpt)


def _run_queued(scenario: str) -> dict[str, Any]:
    from data.pipelines.rfp_approval import run_approval_pipeline
    from data.pipelines.rfp_approval.checkpointer import (
        approval_thread_id,
        reset_approval_checkpointer,
    )
    from data.pipelines.rfp_approval.fixtures import (
        andes_pipeline_kwargs,
        sunset_pipeline_kwargs,
    )

    reset_approval_checkpointer()
    kwargs = (
        sunset_pipeline_kwargs()
        if scenario == "sunset"
        else andes_pipeline_kwargs()
    )
    ticket_id = str(kwargs["ticket_id"])
    result = run_approval_pipeline(
        **kwargs,
        thread_id=approval_thread_id(ticket_id),
        use_interrupt=True,
    )
    return {
        "mode": "queued_decisions",
        "scenario": scenario,
        "thread_id": approval_thread_id(ticket_id),
        "result": result.to_dict(),
    }


def _run_sequential(scenario: str) -> dict[str, Any]:
    """Pause once, then resume each department (and CEO) one decision at a time."""
    from data.pipelines.rfp_approval import run_approval_pipeline
    from data.pipelines.rfp_approval.checkpointer import (
        approval_thread_id,
        reset_approval_checkpointer,
    )
    from data.pipelines.rfp_approval.fixtures import (
        andes_pipeline_kwargs,
        simulated_ceo_approval,
        simulated_department_approvals,
        sunset_pipeline_kwargs,
    )

    reset_approval_checkpointer()
    base = (
        sunset_pipeline_kwargs(include_ceo=False)
        if scenario == "sunset"
        else andes_pipeline_kwargs(queued_decisions=[])
    )
    ticket_id = str(base["ticket_id"])
    thread_id = approval_thread_id(ticket_id)
    departments = list(base["departments_needed"])

    paused = run_approval_pipeline(
        **{**base, "queued_decisions": []},
        thread_id=thread_id,
        use_interrupt=True,
    )
    steps: list[dict[str, Any]] = [
        {
            "step": "paused",
            "status": paused.status,
            "pending": [p.get("department_id") for p in paused.pending_approvals],
        }
    ]
    if not paused.pending_approvals and paused.status != "waiting_for_approval":
        return {
            "mode": "sequential",
            "scenario": scenario,
            "thread_id": thread_id,
            "steps": steps,
            "result": paused.to_dict(),
            "error": "expected HITL pause before simulated resumes",
        }

    current = paused
    for decision in simulated_department_approvals(departments):
        current = run_approval_pipeline(
            **{**base, "queued_decisions": None},
            thread_id=thread_id,
            resume=decision,
            use_interrupt=True,
        )
        steps.append(
            {
                "step": f"resume_{decision['department_id']}",
                "status": current.status,
                "approvals": {
                    d: (current.approvals.get(d) or {}).get("approval_status")
                    for d in departments
                },
            }
        )

    if scenario == "sunset":
        current = run_approval_pipeline(
            **{**base, "queued_decisions": None},
            thread_id=thread_id,
            resume=simulated_ceo_approval(),
            use_interrupt=True,
        )
        steps.append(
            {
                "step": "resume_ceo",
                "status": current.status,
                "ceo": (current.ceo_approval or {}).get("approval_status"),
            }
        )

    return {
        "mode": "sequential",
        "scenario": scenario,
        "thread_id": thread_id,
        "steps": steps,
        "result": current.to_dict(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Part 3 E2E with simulated approvals (programmatic resume, no UI)"
    )
    parser.add_argument(
        "--scenario",
        choices=("andes", "sunset"),
        default="andes",
        help="Andes (no CEO) or Sunset Bay (CEO required)",
    )
    parser.add_argument(
        "--mode",
        choices=("queued", "sequential"),
        default="queued",
        help="queued_decisions drain vs one resume per department",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional JSON output path",
    )
    args = parser.parse_args(argv)

    ckpt = _ensure_env()
    payload = (
        _run_sequential(args.scenario)
        if args.mode == "sequential"
        else _run_queued(args.scenario)
    )
    payload["checkpoint_sqlite"] = str(ckpt)

    result = payload.get("result") or {}
    status = result.get("status")
    doc = result.get("final_document") or {}
    ok = status == "done" and bool(doc.get("markdown") or doc.get("sections"))
    payload["ok"] = ok

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    print(text[:8000])
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")

    if not ok:
        print(
            f"expected status=done with FinalDocument; got status={status!r}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
