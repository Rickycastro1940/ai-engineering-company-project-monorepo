#!/usr/bin/env python3
"""Entry point for the configured Monday cron trigger.

Computes the previous ISO week window and runs the Brasaland weekly pipeline.
Used by GitHub Actions (``.github/workflows/brasaland-weekly-pipeline.yml``)
and can be invoked locally:

  python3 scripts/run_scheduled_pipeline.py
  python3 scripts/run_scheduled_pipeline.py --as-of 2026-07-14
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.pipelines.schedule import (  # noqa: E402
    CRON_EXPRESSION,
    CRON_DESCRIPTION,
    previous_week_window,
    schedule_metadata,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        default=None,
        help="UTC date (YYYY-MM-DD) used to resolve the previous week (default: today UTC)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print schedule + week window only; do not execute the pipeline",
    )
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    window = previous_week_window(as_of)
    meta = schedule_metadata()

    print("schedule: %s (%s)" % (meta["cron"], meta["description"]), flush=True)
    print(
        "window: start=%s end=%s target_date=%s"
        % (window.start_date, window.end_date, window.target_date),
        flush=True,
    )

    if args.dry_run:
        print("dry-run: skipping pipeline execution", flush=True)
        return 0

    from data.pipelines.pipeline import run_pipeline

    job = run_pipeline(
        window.start_date,
        window.end_date,
        target_date=window.target_date,
    )
    print(
        "done status=%s job_id=%s cron=%s"
        % (job.status, job.id, CRON_EXPRESSION),
        flush=True,
    )
    return 0 if job.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
