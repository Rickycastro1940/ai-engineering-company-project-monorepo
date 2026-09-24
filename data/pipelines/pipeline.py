"""Brasaland weekly location cost & waste pipeline (Part 2).

Main entry: ``data/pipelines/pipeline.py`` (this file).
Contracts: root ``CONTEXT-company.md`` (KPIs / schema / endpoints) and
``data/pipelines/PIPELINE_DESIGN.md`` Phase 4 (flows + tasks).

Prefect structure (Phase 1 — flows and tasks):
- Stage subflows: extract → transform → load
- Independent ``@task`` units with explicit inputs/outputs per stage
- Optional non-critical eval snapshot via ``return_state=True`` (must not fail ETL)

Placement:
- ``data/raw/`` — extract snapshots and intermediate KPI frames
- ``data/process/location_kpis.py`` — reusable transform
- ``data/eval/`` — fixtures and validation outputs

Does not write ``telemetry_events`` and does not touch engineering telemetry analysis.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv
from prefect import flow, task
from prefect.states import State
from prefect.tasks import task_input_hash
from supabase import Client, create_client

from data.process.location_kpis import KPI_EVENT_TYPES, aggregate_location_kpis as _aggregate_kpis
from services.safe_errors import ExternalServiceError, call_external, public_error_text

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
env_path = _REPO_ROOT / ".env"
load_dotenv(dotenv_path=env_path)

_LAST_RUN_PATH = Path(__file__).resolve().parent / "last_run.json"
_RAW_DIR = _REPO_ROOT / "data" / "raw"
_EVAL_DIR = _REPO_ROOT / "data" / "eval"
_EVAL_FIXTURES = _EVAL_DIR / "weekly_location_performance_fixtures.json"
_EVAL_OUTPUT = _EVAL_DIR / "last_validation.json"

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


def _safe_window_token(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value)[:64]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)


def _dataframe_records(df: pd.DataFrame) -> list:
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso"))


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


def _land_raw_extracts(
    telemetry_df: pd.DataFrame,
    locations_df: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> dict[str, str]:
    """Persist extract snapshots under data/raw/ for audit / reprocessing."""
    token = f"{_safe_window_token(start_date)}_{_safe_window_token(end_date)}"
    telemetry_path = _RAW_DIR / f"telemetry_events_{token}.json"
    locations_path = _RAW_DIR / f"locations_{token}.json"
    _write_json(
        telemetry_path,
        {
            "window_start": start_date,
            "window_end": end_date,
            "event_types": list(KPI_EVENT_TYPES),
            "rows": _dataframe_records(telemetry_df),
        },
    )
    _write_json(
        locations_path,
        {"rows": _dataframe_records(locations_df)},
    )
    return {
        "telemetry_events": str(telemetry_path),
        "locations": str(locations_path),
    }


def _land_kpi_intermediate(kpis_df: pd.DataFrame, week_start: str) -> str:
    path = _RAW_DIR / f"weekly_location_performance_{_safe_window_token(week_start)}.json"
    _write_json(
        path,
        {
            "week_start": week_start,
            "destination_table": f"{_REPORTING_SCHEMA}.{_PERFORMANCE_TABLE}",
            "rows": _dataframe_records(kpis_df),
        },
    )
    return str(path)


def write_validation_output(kpis_df: pd.DataFrame, week_start: str) -> dict[str, Any]:
    """Compare a KPI frame to data/eval fixtures when week_start matches; always land output."""
    checks: list[dict[str, Any]] = []
    passed = True
    if _EVAL_FIXTURES.exists():
        fixtures = json.loads(_EVAL_FIXTURES.read_text(encoding="utf-8"))
        if fixtures.get("week_start") == week_start and kpis_df is not None and not kpis_df.empty:
            for loc in fixtures.get("locations", []):
                location_id = loc["location_id"]
                expected = loc["expected"]
                match = kpis_df[kpis_df["location_id"] == location_id]
                if match.empty:
                    checks.append(
                        {
                            "location_id": location_id,
                            "ok": False,
                            "reason": "missing_location_row",
                        }
                    )
                    passed = False
                    continue
                row = match.iloc[0]
                location_ok = True
                diffs = {}
                for key, want in expected.items():
                    got = row.get(key)
                    if got != want:
                        location_ok = False
                        diffs[key] = {"expected": want, "actual": got}
                checks.append(
                    {
                        "location_id": location_id,
                        "ok": location_ok,
                        "diffs": diffs,
                    }
                )
                passed = passed and location_ok
        else:
            checks.append(
                {
                    "ok": True,
                    "note": "fixture week_start does not match this run; skipped fixture asserts",
                }
            )
    else:
        checks.append({"ok": True, "note": "no fixtures file present"})

    report = {
        "validated_at": _utc_now_iso(),
        "week_start": week_start,
        "passed": passed,
        "row_count": 0 if kpis_df is None or kpis_df.empty else int(len(kpis_df)),
        "checks": checks,
        "kpis": _dataframe_records(kpis_df) if kpis_df is not None else [],
    }
    _write_json(_EVAL_OUTPUT, report)
    return report


# ---------------------------------------------------------------------------
# Stage 1 — Extraction tasks (explicit I/O) + subflow
# ---------------------------------------------------------------------------


@task(retries=3, retry_delay_seconds=5, name="extract_telemetry_events")
def extract_telemetry_events(start_date: str, end_date: str):
    """Input: chain-week bounds. Output: telemetry_events rows (four KPI types)."""
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


@task(retries=3, retry_delay_seconds=5, name="extract_domain_data")
def extract_domain_data():
    """Input: none. Output: locations dimension (id, country, currency)."""
    response = call_external(
        "reporting store",
        lambda: _supabase_client()
        .table("locations")
        .select("id, country, currency")
        .execute(),
    )
    return pd.DataFrame(response.data or [])


@task(name="land_raw_extracts")
def land_raw_extracts(telemetry_df, locations_df, start_date: str, end_date: str):
    """Input: extract frames + window. Output: paths under data/raw/."""
    paths = _land_raw_extracts(telemetry_df, locations_df, start_date, end_date)
    print(f"Landed extract snapshots: {paths}")
    return paths


@flow(name="extract_brasaland_data_flow", log_prints=True)
def extract_brasaland_data_flow(start_date: str, end_date: str):
    """Extraction stage: read-only snapshots for the chain week.

    Returns ``(telemetry_df, locations_df)``.
    """
    telemetry_df = extract_telemetry_events(start_date, end_date)
    locations_df = extract_domain_data()
    land_raw_extracts(telemetry_df, locations_df, start_date, end_date)
    return telemetry_df, locations_df


# ---------------------------------------------------------------------------
# Stage 2 — Transformation tasks + subflow
# ---------------------------------------------------------------------------


@task(
    cache_key_fn=task_input_hash,
    cache_expiration=timedelta(days=1),
    name="aggregate_location_kpis",
)
def aggregate_location_kpis(telemetry_df, locations_df, week_start: str):
    """Input: extract frames + week_start. Output: one KPI row per location."""
    return _aggregate_kpis(telemetry_df, locations_df, week_start)


@task(name="land_kpi_intermediate")
def land_kpi_intermediate(kpis_df, week_start: str) -> str:
    """Input: KPI frame. Output: intermediate JSON path under data/raw/."""
    path = _land_kpi_intermediate(kpis_df, week_start)
    print(f"Landed KPI intermediate: {path}")
    return path


@flow(name="transform_brasaland_kpis_flow", log_prints=True)
def transform_brasaland_kpis_flow(telemetry_df, locations_df, week_start: str):
    """Transformation stage: pure KPI rollup (no destination write)."""
    kpis_df = aggregate_location_kpis(telemetry_df, locations_df, week_start)
    land_kpi_intermediate(kpis_df, week_start)
    return kpis_df


# ---------------------------------------------------------------------------
# Stage 3 — Load tasks + subflow
# ---------------------------------------------------------------------------


@task(retries=3, retry_delay_seconds=5, name="upsert_to_reporting_table")
def upsert_to_reporting_table(kpis_df) -> int:
    """Input: KPI frame. Output: count of upserted rows into reporting table."""
    if kpis_df is None or getattr(kpis_df, "empty", True):
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


@flow(name="load_brasaland_reporting_flow", log_prints=True)
def load_brasaland_reporting_flow(kpis_df) -> int:
    """Load stage: idempotent upsert into reporting.weekly_location_performance."""
    return upsert_to_reporting_table(kpis_df)


# ---------------------------------------------------------------------------
# Optional non-critical step (eval snapshot) — never blocks ETL
# ---------------------------------------------------------------------------


@task(name="write_eval_snapshot", retries=0)
def write_eval_snapshot(kpis_df, week_start: str):
    """Optional secondary report: fixture validation under data/eval/.

    Non-critical: the parent flow must call this with ``return_state=True`` so a
    failure here does not interrupt extract → transform → load.
    """
    return write_validation_output(kpis_df, week_start)


# ---------------------------------------------------------------------------
# HTTP helpers (used by services/reporting/ — no ETL in routes)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Main orchestrator flow
# ---------------------------------------------------------------------------


@flow(name="brasaland_weekly_performance_pipeline", log_prints=True)
def run_pipeline(start_date: str, end_date: str) -> dict[str, Any]:
    """Monday chain-week ETL: extract → transform → load (+ optional eval).

    Stage subflows carry the critical path. The eval snapshot is invoked with
    ``return_state=True`` so a failure there never fails the main run.
    """
    run_id = str(uuid.uuid4())
    run_row = _insert_run_start(run_id, start_date, end_date)
    records_processed = 0
    try:
        telemetry_data, domain_data = extract_brasaland_data_flow(start_date, end_date)
        if "id" in telemetry_data.columns:
            records_processed = int(telemetry_data["id"].nunique())
        else:
            records_processed = int(len(telemetry_data))

        kpis = transform_brasaland_kpis_flow(telemetry_data, domain_data, start_date)
        load_brasaland_reporting_flow(kpis)

        # Optional / non-critical: secondary eval snapshot under data/eval/.
        eval_state: State = write_eval_snapshot(kpis, start_date, return_state=True)
        if eval_state.is_failed():
            print(
                "Eval snapshot failed (non-critical); "
                "extract/transform/load already completed successfully."
            )
        else:
            print(f"Eval snapshot state: {eval_state.type}")
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
