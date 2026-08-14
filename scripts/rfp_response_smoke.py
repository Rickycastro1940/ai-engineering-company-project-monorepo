#!/usr/bin/env python3
"""Smoke Part 2 response generation from a CONTEXT seed PDF (intake → generate)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from data.pipelines.rfp_intake import run_intake_pipeline
from data.pipelines.rfp_intake.routing import route_intake_to_part2
from data.pipelines.rfp_response import run_response_pipeline

DEFAULT = REPO / "rfp-requests" / "brasaland" / "CONTEXT-brasaland-request-1.pdf"


def main() -> int:
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    intake = run_intake_pipeline(pdf_path=pdf)
    print("intake:", intake.status, "depts:", intake.departments_needed)
    if intake.status != "intake_complete":
        print("discard:", intake.discard_reason)
        return 1
    handoff = route_intake_to_part2(
        ticket_id="smoke-ticket",
        intake_result=intake,
        source_pdf_path=str(pdf),
    )
    assert handoff is not None
    result = run_response_pipeline(ticket_id="smoke-ticket", handoff=handoff)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False)[:4000])
    return 0 if result.all_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
