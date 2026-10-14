"""Nightly landing copy of Brasaland telemetry.

Reads ``public.telemetry_events`` (time column ``timestamp``) for one UTC
calendar day and writes ``data/raw/telemetry_YYYY-MM-DD.csv`` only when that
file is not already there. The CSV is a backup snapshot. The Milestone 6
pipeline (``data/pipelines/pipeline.py``) reads the database, not this file.

``target_date`` comes from the first CLI argument, else ``TARGET_DATE``, else
yesterday in UTC. Status (final status, ``target_date``, timestamps, and
``error_message``) is written to ``public.job_runs`` by ``services.job_runner``.
OS crontab starts this script. The FastAPI process does not.

Run: ``python scripts/nightly_export.py``
"""

from __future__ import annotations

import os
import sys
import subprocess
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

# public.telemetry_events uses "timestamp". The legacy table also has created_at;
# the nightly reader follows the current table, not the legacy name.
TELEMETRY_TIME_COLUMN = "timestamp"
TELEMETRY_TABLE = "telemetry_events"
OPERATIONAL_EVENT_TYPES = (
    "inbound_order_created",
    "stock_waste_registered",
    "stock_threshold_triggered",
)
JOB_NAME = "nightly_export"
# Milestone 6 CLI. There is no data.pipelines.telemetry_kpi_daily package here.
PIPELINE_SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "pipelines", "pipeline.py")
)


def _fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    sys.exit(code)


def _parse_target_date(raw: str) -> str:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        _fail(f"Target date must be YYYY-MM-DD, got: {raw}")


def default_target_date(now: datetime | None = None) -> str:
    """Yesterday's calendar date in UTC."""
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    return (current - timedelta(days=1)).strftime("%Y-%m-%d")


def resolve_target_date(argv: list[str] | None = None, env: dict | None = None) -> str:
    """CLI argument, then TARGET_DATE, then yesterday in UTC."""
    args = sys.argv if argv is None else argv
    source = os.environ if env is None else env
    if len(args) > 1 and args[1].strip():
        return _parse_target_date(args[1].strip())
    raw = source.get("TARGET_DATE")
    if raw is not None and str(raw).strip():
        return _parse_target_date(str(raw).strip())
    return default_target_date()


def export_bounds(target_date: str) -> tuple[str, str]:
    """Inclusive start, exclusive end for one UTC calendar day."""
    start = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return (
        start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def main() -> None:
    target_date = resolve_target_date()

    from supabase import create_client

    from services import job_runner
    from services.safe_errors import ExternalServiceError, call_external, public_error_text

    print(f"Target date: {target_date}")

    job_name = JOB_NAME
    run_id = None

    try:
        if job_runner.has_processing_lock(job_name):
            print("A job is currently processing. Exiting.")
            sys.exit(0)

        if job_runner.has_completed_for_date(job_name, target_date):
            print(f"Job has already completed successfully for {target_date}. Exiting.")
            sys.exit(0)

        run = job_runner.create_run(job_name, target_date)
        if not run:
            _fail("Failed to create job run.")

        run_id = run
        job_runner.mark_processing(run_id)
    except job_runner.JobAlreadyRunning:
        print("A job is currently processing. Exiting.")
        sys.exit(0)
    except ExternalServiceError:
        _fail("Job store is unavailable.")
    except ImportError:
        _fail("Job store dependencies are missing.")

    try:
        csv_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "raw"))
        try:
            os.makedirs(csv_dir, exist_ok=True)
        except OSError:
            _fail("Could not create the telemetry export directory.")

        csv_path = os.path.join(csv_dir, f"telemetry_{target_date}.csv")

        # Audit snapshot only. The pipeline below reads telemetry_events, not this CSV.
        if os.path.exists(csv_path):
            if not os.path.isfile(csv_path) or os.path.getsize(csv_path) == 0:
                _fail(f"Existing telemetry export is missing or empty: telemetry_{target_date}.csv")
            print("Telemetry file already exists, skipping export.")
        else:
            print(f"Exporting telemetry events for {target_date}...")
            url = os.environ.get("SUPABASE_URL")
            key = os.environ.get("SUPABASE_KEY")
            if not url or not key:
                raise ExternalServiceError("reporting store")
            supabase = call_external("reporting store", lambda: create_client(url, key))

            start_dt, end_dt = export_bounds(target_date)
            print(f"Window [{start_dt}, {end_dt}) column={TELEMETRY_TIME_COLUMN}")

            response = call_external(
                "reporting store",
                lambda: supabase.table(TELEMETRY_TABLE)
                .select("*")
                .in_("event_type", list(OPERATIONAL_EVENT_TYPES))
                .gte(TELEMETRY_TIME_COLUMN, start_dt)
                .lt(TELEMETRY_TIME_COLUMN, end_dt)
                .execute(),
            )

            rows = getattr(response, "data", None)
            if rows is None:
                _fail("Telemetry export returned no dataset.")
            if not isinstance(rows, list):
                _fail("Telemetry export returned malformed data.")

            try:
                import pandas as pd
            except ImportError:
                _fail("pandas is required to write the telemetry CSV.")

            df = pd.DataFrame(rows)
            try:
                df.to_csv(csv_path, index=False)
            except OSError:
                _fail(f"Could not write telemetry CSV: telemetry_{target_date}.csv")
            print(f"Exported {len(df)} rows")

        if not os.path.isfile(PIPELINE_SCRIPT):
            _fail("Pipeline script was not found.")

        print("Running pipeline subprocess")
        # Milestone 6 entry point (not data.pipelines.telemetry_kpi_daily, which is absent).
        result = subprocess.run(
            [sys.executable, PIPELINE_SCRIPT],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError("Pipeline subprocess failed")

        job_runner.mark_completed(run_id)
        print("Job run completed successfully.")

    except SystemExit as exit_exc:
        if run_id is not None and exit_exc.code not in (0, None):
            try:
                job_runner.mark_failed(run_id, "nightly export failed")
            except ExternalServiceError:
                pass
        raise
    except Exception as error:
        safe = public_error_text(str(error), "nightly export failed")
        print(f"Job run failed: {safe}", file=sys.stderr)
        if run_id is not None:
            try:
                job_runner.mark_failed(run_id, safe)
            except ExternalServiceError:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
