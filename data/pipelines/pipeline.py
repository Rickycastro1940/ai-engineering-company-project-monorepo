"""Brasaland weekly location cost & waste pipeline (Part 2).

Orchestration only — KPI arithmetic lives in ``data/process/location_kpis.py``.
Contract: ``data/pipelines/PIPELINE_DESIGN.md``.
Does not touch ``GET /telemetry/report`` or engineering telemetry analysis.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv
from prefect import flow, task
from prefect.tasks import task_input_hash
from datetime import timedelta
from supabase import Client, create_client

from data.process.location_kpis import KPI_EVENT_TYPES, aggregate_location_kpis as _aggregate_kpis
from services.safe_errors import ExternalServiceError, call_external, public_error_text

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

_LAST_RUN_PATH = Path(__file__).resolve().parent / "last_run.json"
_REPORTING_SCHEMA = "reporting"
_PERFORMANCE_TABLE = "weekly_location_performance"
_RUNS_TABLE = "pipeline_runs"


def _supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_KEY. Set them in .env before running the weekly pipeline."
        )
    try:
        return create_client(url, key)
    except ExternalServiceError:
        raise
    except Exception as error:
        raise ExternalServiceError("reporting store") from error


def _reporting(client: Client):
    return client.schema(_REPORTING_SCHEMA)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_last_run(metadata: dict) -> None:
    with open(_LAST_RUN_PATH, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, default=str)


def _mirror_run(row: dict) -> None:
    """Mirror the latest pipeline_runs row for GET /reporting/pipeline-runs/latest."""
    payload = {
        "run_id": row.get("run_id"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "window_start": row.get("window_start"),
        "window_end": row.get("window_end"),
        "records_processed": row.get("records_processed"),
        "status": row.get("status"),
        "error_message": row.get("error_message"),
        # Compat aliases used by older callers / dashboards
        "start_date": row.get("window_start"),
        "end_date": row.get("window_end"),
    }
    if payload.get("error_message"):
        payload["error"] = payload["error_message"]
    _write_last_run(payload)


def _insert_run_start(run_id: str, window_start: str, window_end: str) -> dict:
    started_at = _utc_now_iso()
    row = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": None,
        "window_start": window_start,
        "window_end": window_end,
        "records_processed": 0,
        "status": "Running",
        "error_message": None,
    }
    try:
        call_external(
            "reporting store",
            lambda: _reporting(_supabase_client())
            .table(_RUNS_TABLE)
            .insert(row)
            .execute(),
        )
    except ExternalServiceError:
        # Still mirror locally so status endpoint can report the attempt.
        pass
    _mirror_run(row)
    return row


def _finish_run(row: dict, *, status: str, records_processed: int, error_message: Optional[str]) -> dict:
    finished = {
        **row,
        "finished_at": _utc_now_iso(),
        "status": status,
        "records_processed": records_processed,
        "error_message": error_message,
    }
    try:
        call_external(
            "reporting store",
            lambda: _reporting(_supabase_client())
            .table(_RUNS_TABLE)
            .update(
                {
                    "finished_at": finished["finished_at"],
                    "status": status,
                    "records_processed": records_processed,
                    "error_message": error_message,
                }
            )
            .eq("run_id", row["run_id"])
            .execute(),
        )
    except ExternalServiceError:
        pass
    _mirror_run(finished)
    return finished


def extract_telemetry_events(start_date: str, end_date: str) -> pd.DataFrame:
    response = call_external(
        "reporting store",
        lambda: _supabase_client()
        .table("telemetry_events")
        .select("id,event_type,created_at,event_payload")
        .in_("event_type", list(KPI_EVENT_TYPES))
        .gte("created_at", start_date)
        .lt("created_at", end_date)
        .execute(),
    )
    return pd.DataFrame(response.data or [])


def extract_domain_data() -> pd.DataFrame:
    response = call_external(
        "reporting store",
        lambda: _supabase_client()
        .table("locations")
        .select("id, country, currency")
        .execute(),
    )
    return pd.DataFrame(response.data or [])


@task(retries=3, retry_delay_seconds=5, name="extract_weekly_inputs")
def extract_weekly_inputs(start_date: str, end_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read telemetry_events (four KPI types) and locations for the chain week."""
    return extract_telemetry_events(start_date, end_date), extract_domain_data()


@task(
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(days=1),
    name="aggregate_location_kpis",
)
def aggregate_location_kpis(
    telemetry_df: pd.DataFrame,
    locations_df: pd.DataFrame,
    week_start: str,
) -> pd.DataFrame:
    """Prefect task wrapper around the pure transform in ``data/process``."""
    return _aggregate_kpis(telemetry_df, locations_df, week_start)


@task(retries=3, retry_delay_seconds=5, name="upsert_to_reporting_table")
def upsert_to_reporting_table(kpis_df: pd.DataFrame) -> int:
    """Replace location-week keys in reporting.weekly_location_performance."""
    if kpis_df is None or kpis_df.empty:
        print("No data to upsert.")
        return 0
    records = kpis_df.to_dict(orient="records")
    call_external(
        "reporting store",
        lambda: _reporting(_supabase_client())
        .table(_PERFORMANCE_TABLE)
        .upsert(records, on_conflict="location_id,week_start")
        .execute(),
    )
    print(f"Successfully upserted {len(records)} records!")
    return len(records)


def get_weekly_location_performance(week_start: Optional[str] = None) -> dict[str, Any]:
    """Read reporting.weekly_location_performance for the KPI query endpoint."""
    client = _supabase_client()
    query = _reporting(client).table(_PERFORMANCE_TABLE).select("*")
    if week_start:
        query = query.eq("week_start", week_start)
    response = call_external(
        "reporting store",
        lambda: query.order("week_start", desc=True).execute(),
    )
    rows = response.data or []
    if not rows:
        return {"week_start": week_start, "locations": []}

    actual_week_start = week_start or rows[0].get("week_start")
    locations = [row for row in rows if row.get("week_start") == actual_week_start]
    formatted = [
        {
            "location_id": loc.get("location_id"),
            "country": loc.get("country"),
            "currency": loc.get("currency"),
            "total_purchase_cost": loc.get("total_purchase_cost"),
            "total_waste_cost": loc.get("total_waste_cost"),
            "waste_ratio": loc.get("waste_ratio"),
            "stockout_events_count": loc.get("stockout_events_count"),
            "price_alert_events_count": loc.get("price_alert_events_count"),
        }
        for loc in locations
    ]
    return {"week_start": actual_week_start, "locations": formatted}


def get_latest_pipeline_run() -> dict[str, Any]:
    """Newest reporting.pipeline_runs row, falling back to last_run.json."""
    try:
        response = call_external(
            "reporting store",
            lambda: _reporting(_supabase_client())
            .table(_RUNS_TABLE)
            .select("*")
            .order("started_at", desc=True)
            .limit(1)
            .execute(),
        )
        rows = response.data or []
        if rows:
            row = rows[0]
            _mirror_run(row)
            return {
                "run_id": row.get("run_id"),
                "started_at": row.get("started_at"),
                "finished_at": row.get("finished_at"),
                "window_start": row.get("window_start"),
                "window_end": row.get("window_end"),
                "records_processed": row.get("records_processed"),
                "status": row.get("status"),
                "error_message": row.get("error_message"),
            }
    except (RuntimeError, ExternalServiceError):
        pass

    if not _LAST_RUN_PATH.exists():
        return {"message": "No pipeline runs recorded yet."}
    try:
        with open(_LAST_RUN_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"message": "No pipeline runs recorded yet."}
    if isinstance(payload, dict) and payload.get("error_message"):
        payload["error_message"] = public_error_text(
            payload.get("error_message"), "Pipeline failed."
        )
    if isinstance(payload, dict) and payload.get("error"):
        payload["error"] = public_error_text(payload.get("error"), "Pipeline failed.")
    return payload


@flow(name="brasaland_weekly_performance_pipeline", log_prints=True)
def run_pipeline(start_date: str, end_date: str) -> dict[str, Any]:
    """Monday chain-week ETL: extract → transform → load, with run log."""
    run_id = str(uuid.uuid4())
    run_row = _insert_run_start(run_id, start_date, end_date)
    records_processed = 0
    try:
        telemetry_data, domain_data = extract_weekly_inputs(start_date, end_date)
        if "id" in telemetry_data.columns:
            records_processed = int(telemetry_data["id"].nunique())
        else:
            records_processed = int(len(telemetry_data))
        kpis = aggregate_location_kpis(telemetry_data, domain_data, start_date)
        upsert_to_reporting_table(kpis)
    except Exception as error:
        safe = public_error_text(str(error), "reporting store is unavailable")
        _finish_run(
            run_row,
            status="Failed",
            records_processed=records_processed,
            error_message=safe,
        )
        raise

    finished = _finish_run(
        run_row,
        status="Success",
        records_processed=records_processed,
        error_message=None,
    )
    return finished


if __name__ == "__main__":
    print("Executing pipeline directly...")
    run_pipeline("2026-07-01", "2026-08-01")
    print("Pipeline execution completed successfully.")
