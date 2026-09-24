"""Reporting API routes for the weekly location cost & waste pipeline.

Phase 5 — Application integration (PIPELINE_DESIGN.md / CONTEXT-company.md):

| Role | Endpoint | Calls |
| --- | --- | --- |
| Status | ``GET /reporting/pipeline-runs/latest`` | ``get_latest_pipeline_run()`` |
| Trigger | ``POST /reporting/pipeline-runs`` | Celery → ``run_pipeline`` |
| KPI query | ``GET /reporting/weekly-location-performance`` | ``get_weekly_location_performance()`` |

No extract / transform / load / KPI math belongs in this module.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from data.pipelines.pipeline import (
    get_latest_pipeline_run,
    get_weekly_location_performance,
)
from services.safe_errors import ExternalServiceError, public_error_text
from services.task_status import get_task_payload
from services.tasks import run_weekly_pipeline

logger = logging.getLogger("brasaland.reporting")

router = APIRouter(tags=["reporting"])

_STORAGE_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    TimeoutError,
    ConnectionError,
    ExternalServiceError,
    RuntimeError,
)
try:
    import httpx

    _STORAGE_ERRORS = (*_STORAGE_ERRORS, httpx.HTTPError)
except ImportError:
    pass
try:
    from postgrest.exceptions import APIError as PostgrestAPIError

    _STORAGE_ERRORS = (*_STORAGE_ERRORS, PostgrestAPIError)
except ImportError:
    pass

_ENQUEUE_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    TimeoutError,
    ConnectionError,
    RuntimeError,  # Celery raises after Redis reconnect retries are exhausted
)
try:
    from kombu.exceptions import OperationalError as KombuOperationalError

    _ENQUEUE_ERRORS = (*_ENQUEUE_ERRORS, KombuOperationalError)
except ImportError:
    pass
try:
    from redis.exceptions import RedisError

    _ENQUEUE_ERRORS = (*_ENQUEUE_ERRORS, RedisError)
except ImportError:
    pass
try:
    from celery.exceptions import CeleryError

    _ENQUEUE_ERRORS = (*_ENQUEUE_ERRORS, CeleryError)
except ImportError:
    pass


class PipelineTriggerRequest(BaseModel):
    """Chain-week bounds for a manual ``brasaland_weekly_performance_pipeline`` run."""

    start_date: str = Field(..., description="Chain-week start (YYYY-MM-DD, inclusive)")
    end_date: str = Field(..., description="Chain-week end (YYYY-MM-DD, exclusive)")


@router.get("/reporting/pipeline-runs/latest")
def get_latest_run():
    """Status query — newest ``reporting.pipeline_runs`` row (or ``last_run.json``).

    Returns start/end times, window, records_processed, status, and errors.
    Does not open ``telemetry_events`` and does not start a run.
    """
    try:
        payload = get_latest_pipeline_run()
    except OSError as error:
        raise HTTPException(
            status_code=503,
            detail="Could not read the last pipeline run.",
        ) from error
    if isinstance(payload, dict) and payload.get("error_message"):
        payload = {
            **payload,
            "error_message": public_error_text(
                payload.get("error_message"), "Pipeline failed."
            ),
        }
    if isinstance(payload, dict) and payload.get("error"):
        payload = {
            **payload,
            "error": public_error_text(payload.get("error"), "Pipeline failed."),
        }
    return payload


@router.post("/reporting/pipeline-runs")
def trigger_pipeline(payload: PipelineTriggerRequest):
    """Manual trigger — enqueue Prefect ``run_pipeline`` via Celery; return 202.

    The worker runs extract → transform → load. This route does not call those
    stages itself.
    """
    try:
        async_result = run_weekly_pipeline.delay(payload.start_date, payload.end_date)
    except _ENQUEUE_ERRORS as error:
        logger.warning("pipeline enqueue failed: %s", error.__class__.__name__)
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue the weekly pipeline. Confirm Redis is running.",
        ) from error
    return JSONResponse(
        status_code=202,
        content={"task_id": async_result.id},
    )


@router.get("/reporting/weekly-location-performance")
def get_weekly_performance(
    week_start: Optional[str] = Query(
        default=None,
        description="Optional chain-week start (YYYY-MM-DD) filter",
    ),
):
    """KPI query — reads ``reporting.weekly_location_performance`` only.

    Feed for Part 3's executive / ops dashboard (Mariana, Felipe, Lucía).
    No ETL: no cost sums, event-type filters, or location joins here.
    """
    try:
        return get_weekly_location_performance(week_start=week_start)
    except _STORAGE_ERRORS as error:
        logger.warning("weekly performance query failed: %s", error.__class__.__name__)
        raise HTTPException(
            status_code=503,
            detail="Unable to read weekly location performance from reporting storage.",
        ) from error


@router.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    """Poll Celery task status for a manual ``POST /reporting/pipeline-runs`` trigger."""
    try:
        return get_task_payload(task_id)
    except _ENQUEUE_ERRORS as error:
        logger.warning("task status lookup failed: %s", error.__class__.__name__)
        raise HTTPException(
            status_code=503,
            detail="Task status is unavailable. Confirm Redis is running.",
        ) from error
