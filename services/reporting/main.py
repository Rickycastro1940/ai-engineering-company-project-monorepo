import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from data.pipelines.pipeline import (
    get_latest_pipeline_run,
    get_weekly_location_performance,
)
from services.tasks import run_weekly_pipeline
from services.task_status import get_task_payload
from services.safe_errors import ExternalServiceError, public_error_text

load_dotenv()

logger = logging.getLogger("brasaland.reporting")
app = FastAPI(title="Brasaland Reporting API", debug=False)

_api_dir = Path(__file__).resolve().parents[1] / "api"
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))
from errors import register_error_handlers  # noqa: E402

register_error_handlers(app)

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

_ENQUEUE_ERRORS: tuple[type[BaseException], ...] = (OSError, TimeoutError, ConnectionError)
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


class PipelineTriggerRequest(BaseModel):
    start_date: str
    end_date: str


@app.get("/reporting/weekly-location-performance")
def get_weekly_performance(week_start: str = None):
    """KPI query — reads reporting.weekly_location_performance only (no ETL)."""
    try:
        return get_weekly_location_performance(week_start=week_start)
    except _STORAGE_ERRORS as error:
        logger.warning("weekly performance query failed: %s", error.__class__.__name__)
        raise HTTPException(
            status_code=503,
            detail="Unable to read weekly location performance from reporting storage.",
        ) from error


@app.post("/reporting/pipeline-runs")
def trigger_pipeline(payload: PipelineTriggerRequest):
    """Enqueue the weekly pipeline as a Celery task; return immediately."""
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


@app.get("/tasks/{task_id}")
def get_task_status(task_id: str):
    """Return Celery task status/result from the Redis result backend."""
    try:
        return get_task_payload(task_id)
    except _ENQUEUE_ERRORS as error:
        logger.warning("task status lookup failed: %s", error.__class__.__name__)
        raise HTTPException(
            status_code=503,
            detail="Task status is unavailable. Confirm Redis is running.",
        ) from error


@app.get("/reporting/pipeline-runs/latest")
def get_latest_run():
    """Status query — newest reporting.pipeline_runs row (mirrored in last_run.json)."""
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
            "error_message": public_error_text(payload.get("error_message"), "Pipeline failed."),
        }
    if isinstance(payload, dict) and payload.get("error"):
        payload = {
            **payload,
            "error": public_error_text(payload.get("error"), "Pipeline failed."),
        }
    return payload


# Mount the frontend UI (must be at the bottom)
app.mount("/", StaticFiles(directory="uis/backoffice", html=True), name="ui")
