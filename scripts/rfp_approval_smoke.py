#!/usr/bin/env python3
"""Smoke Part 3: Part 2 drafts → named-owner HITL → FinalDocument (no PDF in Part 3)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from data.pipelines.rfp_approval import run_approval_pipeline
from data.pipelines.rfp_approval.approvers import DEPARTMENT_OWNERS
from data.pipelines.rfp_intake.constants import STATUS_WAITING_FOR_APPROVAL

ANDES_SECTIONS = [
    {
        "department_id": "marketing",
        "owner": "Camila Ospina",
        "draft_content": "## Brand terms\nOffer validity 30 days from issuance.\n",
        "approval_status": "pending",
    },
    {
        "department_id": "operaciones",
        "owner": "Felipe Guerrero",
        "draft_content": "## Setup times\nSetup in 12 business days.\n## Cost per event\nUSD $40 per cover.\n",
        "approval_status": "pending",
    },
    {
        "department_id": "procurement",
        "owner": "Lucía Fernández",
        "draft_content": "## Estimated ingredient cost based on volume\nUSD $25 ingredient cost per cover.\n",
        "approval_status": "pending",
    },
]


def main() -> int:
    departments = [s["department_id"] for s in ANDES_SECTIONS]
    decisions = [
        {
            "department_id": dept,
            "decision": "approved",
            "approver": DEPARTMENT_OWNERS[dept],
        }
        for dept in departments
    ]
    result = run_approval_pipeline(
        ticket_id="smoke-approval",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=ANDES_SECTIONS,
        metadata={
            "client_name": "Andes Tech Solutions",
            "location": "Medellín",
            "estimated_contract_value_usd": 20000,
        },
        departments_needed=departments,
        requires_ceo_approval=False,
        queued_decisions=decisions,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False)[:5000])
    if result.status != "done" or not result.final_document:
        print("expected status=done with a FinalDocument", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
