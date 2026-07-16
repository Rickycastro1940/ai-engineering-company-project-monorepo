#!/usr/bin/env python3
"""Serve the Brasaland weekly pipeline on the documented Monday cron.

Cron expression (source of truth: ``data.pipelines.schedule``):

  ``0 9 * * 1`` — every Monday at 09:00 UTC

Requires Prefect installed and a reachable Prefect API (local or Cloud):

  python3 scripts/serve_pipeline_schedule.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prefect import flow  # noqa: E402

from data.pipelines.pipeline import run_pipeline  # noqa: E402
from data.pipelines.schedule import (  # noqa: E402
    CRON_EXPRESSION,
    CRON_TIMEZONE,
    SCHEDULE_NAME,
    previous_week_window,
    schedule_metadata,
)


@flow(name="brasaland_weekly_scheduled_pipeline", log_prints=True)
def brasaland_weekly_scheduled_pipeline() -> dict:
    """Prefect entrypoint: resolve previous week, then run tracked ETL."""
    window = previous_week_window()
    print(
        "Scheduled run window start=%s end=%s target_date=%s cron=%s tz=%s"
        % (
            window.start_date,
            window.end_date,
            window.target_date,
            CRON_EXPRESSION,
            CRON_TIMEZONE,
        )
    )
    job = run_pipeline(
        window.start_date,
        window.end_date,
        target_date=window.target_date,
    )
    return {"schedule": schedule_metadata(), "job": job.to_dict()}


def main() -> None:
    meta = schedule_metadata()
    print(
        "Serving %s with cron=%s timezone=%s"
        % (meta["name"], meta["cron"], meta["timezone"]),
        flush=True,
    )
    # Prefect 2/3: cron= wires the deployment schedule at serve time.
    brasaland_weekly_scheduled_pipeline.serve(
        name=SCHEDULE_NAME,
        cron=CRON_EXPRESSION,
    )


if __name__ == "__main__":
    main()
