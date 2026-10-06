"""``GET /telemetry/report`` — engineering technical report with in-memory cache."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.telemetry.analysis import (
    get_auth_failure_rate,
    get_error_rate_by_type,
    get_events_per_day,
)

router = APIRouter(tags=["telemetry"])

_STORAGE_ERRORS: tuple[type[BaseException], ...] = (OSError, TimeoutError, ConnectionError)
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

# Key: (start_date_str, end_date_str) → {"expiry": float, "data": dict}
REPORT_CACHE: dict[tuple[str, str], dict] = {}
CACHE_TTL_SECONDS = 60


class MetricsSchema(BaseModel):
    events_per_day: list[dict]
    error_rate_by_type: list[dict]
    auth_failure_rate: list[dict]


class TelemetryReportResponse(BaseModel):
    period: dict = Field(
        ...,
        description='Window as {"from": ISO start inclusive, "to": ISO end exclusive}',
    )
    metrics: MetricsSchema


def _supabase_client():
    """Lazy client so importing the app does not require Supabase env."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise HTTPException(
            status_code=503,
            detail="Telemetry store is unavailable (missing SUPABASE_URL or SUPABASE_KEY).",
        )
    try:
        from supabase import create_client
    except ImportError as error:
        raise HTTPException(
            status_code=503,
            detail="Telemetry store is unavailable (supabase package not installed).",
        ) from error
    return create_client(url, key)


def load_telemetry_from_supabase(start_date: str, end_date: str) -> pd.DataFrame:
    """SQL layer: rows in [start_date, end_date) with columns the metrics need."""
    try:
        response = (
            _supabase_client()
            .table("telemetry_events")
            .select("id", "timestamp", "event_type", "tags")
            .gte("timestamp", start_date)
            .lt("timestamp", end_date)
            .execute()
        )
    except HTTPException:
        raise
    except _STORAGE_ERRORS as error:
        raise HTTPException(
            status_code=503,
            detail="Telemetry store is unavailable.",
        ) from error

    return pd.DataFrame(response.data or [])


def clear_report_cache() -> None:
    """Test helper — drop all cached report payloads."""
    REPORT_CACHE.clear()


def build_telemetry_report(start_date: str, end_date: str, *, use_cache: bool = True) -> dict:
    """Analysis → payload → optional 60s cache for (start_date, end_date)."""
    cache_key = (start_date, end_date)
    current_time = time.time()

    if use_cache and cache_key in REPORT_CACHE:
        entry = REPORT_CACHE[cache_key]
        if current_time < entry["expiry"]:
            return entry["data"]

    df = load_telemetry_from_supabase(start_date, end_date)
    report_data = {
        "period": {"from": start_date, "to": end_date},
        "metrics": {
            "events_per_day": get_events_per_day(df.copy()),
            "error_rate_by_type": get_error_rate_by_type(df.copy()),
            "auth_failure_rate": get_auth_failure_rate(df.copy()),
        },
    }

    if use_cache:
        REPORT_CACHE[cache_key] = {
            "expiry": current_time + CACHE_TTL_SECONDS,
            "data": report_data,
        }
    return report_data


@router.get("/telemetry/report", response_model=TelemetryReportResponse)
async def get_telemetry_report(
    start_date: str | None = Query(
        None, description="ISO 8601 start (inclusive). Default: now − 7 days UTC."
    ),
    end_date: str | None = Query(
        None, description="ISO 8601 end (exclusive). Default: now UTC."
    ),
):
    now = datetime.now(timezone.utc)
    if not start_date:
        start_date = (now - timedelta(days=7)).isoformat()
    if not end_date:
        end_date = now.isoformat()
    return build_telemetry_report(start_date, end_date)
