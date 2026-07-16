"""Brasaland reporting API.

Responsibility split (no duplication):
- `job_runs` (data/pipelines/job_runs.py + Supabase table) is the only system of
  record for execution lifecycle, locking, and idempotency.
- `/reporting/pipeline-runs*` is a thin HTTP alias for triggering/listing the
  Brasaland weekly pipeline jobs — it never owns a separate run store.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

try:
    from supabase import create_client
except ImportError:  # pragma: no cover
    create_client = None

from data.pipelines.job_runs import DEFAULT_JOB_NAME, get_job_run_store
from data.pipelines.pipeline import run_pipeline

app = FastAPI(title="Brasaland Reporting API")

url: Optional[str] = os.environ.get("SUPABASE_URL")
key: Optional[str] = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key) if create_client and url and key else None


class PipelineTriggerRequest(BaseModel):
    start_date: str
    end_date: str
    target_date: Optional[str] = Field(
        default=None,
        description="Business date this job is for. Defaults to start_date.",
    )


def _store():
    return get_job_run_store(supabase)


def _pipeline_jobs():
    """job_runs rows that belong to the Brasaland weekly pipeline only."""
    return [
        job
        for job in _store().list()
        if job.job_name == DEFAULT_JOB_NAME
    ]


@app.get("/reporting/weekly-location-performance")
def get_weekly_performance(week_start: str = None):
    if supabase is None:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    query = supabase.table("weekly_location_performance").select("*")
    if week_start:
        query = query.eq("week_start", week_start)

    response = query.order("week_start", desc=True).execute()

    if not response.data:
        return {"week_start": week_start, "locations": []}

    actual_week_start = week_start or response.data[0].get("week_start")
    locations = [row for row in response.data if row["week_start"] == actual_week_start]

    formatted_locations = [{
        "location_id": loc["location_id"],
        "country": loc["country"],
        "total_purchase_cost": loc["total_purchase_cost"],
        "total_waste_cost": loc["total_waste_cost"],
        "waste_ratio": loc["waste_ratio"],
        "stockout_events_count": loc["stockout_events_count"],
        "price_alert_events_count": loc["price_alert_events_count"],
        "currency": loc["currency"]
    } for loc in locations]

    return {
        "week_start": actual_week_start,
        "locations": formatted_locations
    }


@app.get("/reporting/job-runs")
def list_job_runs():
    """System-of-record listing for all job_runs."""
    return {"jobs": [job.to_dict() for job in _store().list()]}


@app.get("/reporting/job-runs/{job_id}")
def get_job_run(job_id: str):
    job = _store().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_run not found")
    return job.to_dict()


@app.get("/reporting/pipeline-runs")
def list_pipeline_runs():
    """Alias: Brasaland weekly pipeline executions from job_runs (filtered by job_name)."""
    return {
        "source": "job_runs",
        "job_name": DEFAULT_JOB_NAME,
        "runs": [job.to_dict() for job in _pipeline_jobs()],
    }


@app.post("/reporting/pipeline-runs")
def trigger_pipeline(request: PipelineTriggerRequest):
    """Alias: trigger weekly pipeline; persistence is entirely via job_runs."""
    try:
        job = run_pipeline(
            request.start_date,
            request.end_date,
            target_date=request.target_date,
            store=_store(),
        )
        return {
            "source": "job_runs",
            "status": job.status,
            "job": job.to_dict(),
            "message": "Pipeline executed for %s to %s (target_date=%s)"
            % (request.start_date, request.end_date, job.target_date),
        }
    except Exception as e:
        failed_job = None
        pipeline_jobs = _pipeline_jobs()
        if pipeline_jobs:
            failed_job = pipeline_jobs[0].to_dict()
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "source": "job_runs", "job": failed_job},
        )


@app.get("/reporting/pipeline-runs/latest")
def get_latest_pipeline_run():
    """Alias: latest Brasaland pipeline job from job_runs only."""
    jobs = _pipeline_jobs()
    if not jobs:
        return {
            "source": "job_runs",
            "job_name": DEFAULT_JOB_NAME,
            "message": "No pipeline runs recorded yet.",
        }
    latest = jobs[0].to_dict()
    latest["source"] = "job_runs"
    return latest


# Mount the frontend UI (must be at the bottom)
app.mount("/", StaticFiles(directory="uis/backoffice", html=True), name="ui")
