"""Status control for Brasaland background jobs.

Writes ``public.job_runs`` (see ``data/pipelines/job_runs.sql``). The nightly
export in ``scripts/nightly_export.py`` is the caller. This module is not a
FastAPI router and is not started by ``uvicorn``.

Statuses match the table check: ``pending``, ``processing``, ``completed``,
``failed``. ``started_at`` is set when a run is claimed. ``finished_at`` is
set when it completes or fails.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import Client, create_client

from services.safe_errors import ExternalServiceError, call_external, public_error_text

load_dotenv()

JOB_STATUSES = ("pending", "processing", "completed", "failed")

_supabase: Client | None = None


class JobAlreadyRunning(Exception):
    """Another processing row already holds (job_name, target_date)."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client() -> Client:
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ExternalServiceError("job store")
        try:
            _supabase = create_client(url, key)
        except Exception as error:
            raise ExternalServiceError("job store") from error
    return _supabase


def _unique_violation(error: BaseException) -> bool:
    code = getattr(error, "code", None)
    if str(code) == "23505":
        return True
    text = str(error).lower()
    return "23505" in text or "duplicate key" in text


def create_run(job_name: str, target_date: str):
    """Insert a processing row and return its id. Raises JobAlreadyRunning on the lock."""
    payload = {
        "job_name": job_name,
        "target_date": target_date,
        "status": "processing",
        "started_at": _utcnow(),
    }

    def _insert():
        return _client().table("job_runs").insert(payload).execute()

    try:
        response = call_external("job store", _insert)
    except ExternalServiceError as error:
        cause = error.__cause__
        if cause is not None and _unique_violation(cause):
            raise JobAlreadyRunning(job_name) from cause
        raise
    if response.data:
        return response.data[0]["id"]
    return None


def mark_processing(run_id):
    response = call_external(
        "job store",
        lambda: _client()
        .table("job_runs")
        .update({"status": "processing", "started_at": _utcnow()})
        .eq("id", run_id)
        .execute(),
    )
    return response.data


def mark_completed(run_id):
    response = call_external(
        "job store",
        lambda: _client()
        .table("job_runs")
        .update({"status": "completed", "finished_at": _utcnow(), "error_message": None})
        .eq("id", run_id)
        .execute(),
    )
    return response.data


def mark_failed(run_id, error_message: str):
    safe_message = public_error_text(error_message, "nightly export failed")
    response = call_external(
        "job store",
        lambda: _client()
        .table("job_runs")
        .update(
            {
                "status": "failed",
                "finished_at": _utcnow(),
                "error_message": safe_message,
            }
        )
        .eq("id", run_id)
        .execute(),
    )
    return response.data


def has_processing_lock(job_name: str) -> bool:
    response = call_external(
        "job store",
        lambda: _client()
        .table("job_runs")
        .select("id")
        .eq("job_name", job_name)
        .eq("status", "processing")
        .execute(),
    )
    return len(response.data or []) > 0


def has_completed_for_date(job_name: str, target_date: str) -> bool:
    response = call_external(
        "job store",
        lambda: _client()
        .table("job_runs")
        .select("id")
        .eq("job_name", job_name)
        .eq("target_date", target_date)
        .eq("status", "completed")
        .execute(),
    )
    return len(response.data or []) > 0


def latest_run(job_name: str, target_date: str | None = None) -> dict | None:
    """Newest status row for a job, optionally for one target date."""

    def _query():
        query = (
            _client()
            .table("job_runs")
            .select(
                "id,job_name,target_date,status,started_at,finished_at,error_message,created_at"
            )
            .eq("job_name", job_name)
            .order("id", desc=True)
            .limit(1)
        )
        if target_date is not None:
            query = query.eq("target_date", target_date)
        return query.execute()

    response = call_external("job store", _query)
    rows = response.data or []
    if not rows:
        return None
    return rows[0]
