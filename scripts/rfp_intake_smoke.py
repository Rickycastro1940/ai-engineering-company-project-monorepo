#!/usr/bin/env python3
"""CLI: run Brasaland RFP intake on a PDF (or curriculum seed).

Examples:
  uv run python scripts/rfp_intake_smoke.py
  uv run python scripts/rfp_intake_smoke.py rfp-requests/brasaland/CONTEXT-brasaland-request-1.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.pipelines.rfp_intake import run_intake_pipeline  # noqa: E402

SEEDS = [
    REPO_ROOT / "rfp-requests" / "brasaland" / "CONTEXT-brasaland-request-1.pdf",
    REPO_ROOT / "rfp-requests" / "brasaland" / "CONTEXT-brasaland-request-2.pdf",
    REPO_ROOT / "rfp-requests" / "brasaland" / "CONTEXT-brasaland-request-3.pdf",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Brasaland RFP intake smoke runner")
    parser.add_argument(
        "pdf",
        nargs="*",
        type=Path,
        help="PDF path(s). Default: all curriculum seeds under rfp-requests/brasaland/",
    )
    args = parser.parse_args(argv)
    paths = args.pdf or SEEDS
    exit_code = 0
    for path in paths:
        path = path if path.is_absolute() else REPO_ROOT / path
        print(f"=== {path.name} ===")
        result = run_intake_pipeline(pdf_path=path)
        print(
            json.dumps(
                {
                    "status": result.status,
                    "client": (result.metadata or {}).get("client_name"),
                    "departments_needed": result.departments_needed,
                    "requires_ceo_approval": result.requires_ceo_approval,
                    "discard_reason": result.discard_reason,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        if result.status == "failed":
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
