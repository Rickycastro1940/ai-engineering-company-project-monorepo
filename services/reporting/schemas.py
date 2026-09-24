"""HTTP response models for Brasaland reporting (CONTEXT-company.md contract)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LocationWeekPerformance(BaseModel):
    """One location-week KPI row — columns match reporting.weekly_location_performance."""

    model_config = ConfigDict(extra="ignore")

    location_id: str
    country: str
    currency: str
    total_purchase_cost: float
    total_waste_cost: float
    waste_ratio: float
    stockout_events_count: int
    price_alert_events_count: int


class WeeklyLocationPerformanceResponse(BaseModel):
    """KPI query body from CONTEXT-company.md endpoint contract."""

    model_config = ConfigDict(extra="ignore")

    week_start: Optional[str] = None
    locations: list[LocationWeekPerformance] = Field(default_factory=list)


class PipelineRunLatestResponse(BaseModel):
    """Status query — reporting.pipeline_runs columns (CONTEXT-company.md)."""

    model_config = ConfigDict(extra="ignore")

    run_id: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    records_processed: Optional[int] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    # Empty-store marker when no runs exist yet
    message: Optional[str] = None


class PipelineTriggerRequest(BaseModel):
    """Body for POST /reporting/pipeline-runs."""

    start_date: str = Field(..., description="Chain-week start (YYYY-MM-DD, inclusive)")
    end_date: str = Field(..., description="Chain-week end (YYYY-MM-DD, exclusive)")


class PipelineTriggerResponse(BaseModel):
    """202 body from CONTEXT-company.md — Celery task id only."""

    task_id: str


class TaskStatusResponse(BaseModel):
    """Companion poll body for GET /tasks/{task_id}."""

    model_config = ConfigDict(extra="ignore")

    task_id: str
    status: str
    result: object = None
