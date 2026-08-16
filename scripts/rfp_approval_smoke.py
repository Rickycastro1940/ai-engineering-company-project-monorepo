#!/usr/bin/env python3
"""Smoke Part 3: fixture drafts → simulated named-owner HITL → FinalDocument.

Delegates to the shared reproducible fixture (no PDF, no UI clicks).
Prefer ``scripts/rfp_part3_e2e_simulated_approvals.py`` for sequential resume.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from data.pipelines.rfp_approval import run_approval_pipeline
from data.pipelines.rfp_approval.checkpointer import (
    approval_thread_id,
    reset_approval_checkpointer,
)
from data.pipelines.rfp_approval.fixtures import andes_pipeline_kwargs


def main() -> int:
    os.environ.setdefault("RFP_ALLOW_SQLITE", "1")
    if not os.environ.get("RFP_CHECKPOINT_SQLITE"):
        os.environ["RFP_CHECKPOINT_SQLITE"] = str(
            Path(tempfile.gettempdir()) / f"rfp-approval-smoke-{uuid4().hex}.sqlite"
        )
    os.environ.pop("RFP_CHECKPOINT_MEMORY", None)
    reset_approval_checkpointer()

    kwargs = andes_pipeline_kwargs()
    result = run_approval_pipeline(
        **kwargs,
        thread_id=approval_thread_id(str(kwargs["ticket_id"])),
        use_interrupt=True,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False)[:5000])
    if result.status != "done" or not result.final_document:
        print("expected status=done with a FinalDocument", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
