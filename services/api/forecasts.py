"""Demand forecast API — Operations and Procurement from CONTEXT.md.

Felipe Guerrero needs a next-day read of peak hour and protein/produce
for each kitchen. Lucía Fernández needs those quantities rolled up in
COP (Colombia) and USD (Florida). Brasa Points stay on physical stamp
cards; the loyalty block is an expected stamp-card tally, not a wallet.

The fit lives in data/pipelines/demand_forecast.py. This router only
exposes it.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from users import get_current_user

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.pipelines.demand_forecast import (  # noqa: E402
    UnknownLocationError,
    default_forecast_date,
    forecast_demand,
)

router = APIRouter(
    prefix="/forecasts",
    tags=["forecasts"],
    dependencies=[Depends(get_current_user)],
)


class WeatherOutlook(BaseModel):
    temperature_c: float
    rain: bool


class HourlyCovers(BaseModel):
    hour: int = Field(ge=0, le=23)
    label: str
    covers: float = Field(ge=0)


class LoyaltyOutlook(BaseModel):
    program: str
    medium: str
    digital_loyalty: bool
    expected_stamp_card_visits: float = Field(ge=0)
    expected_brasa_points_earned: float = Field(ge=0)
    points_rule: str


class LocationDemand(BaseModel):
    location_id: str
    location_name: str
    city: str
    country: str
    region: str
    currency: str
    holiday: str | None
    weather: WeatherOutlook
    peak_hour: int
    peak_label: str
    peak_covers: float = Field(ge=0)
    hourly_covers: list[HourlyCovers]
    protein_kg: dict[str, float]
    produce_kg: dict[str, float]
    estimated_purchase_local: float = Field(ge=0)
    loyalty: LoyaltyOutlook


class ProcurementRollup(BaseModel):
    protein_kg: dict[str, float]
    produce_kg: dict[str, float]
    estimated_purchase_cop: float = Field(ge=0)
    estimated_purchase_usd: float = Field(ge=0)
    expected_brasa_points_earned: float = Field(ge=0)
    note: str


class DemandForecast(BaseModel):
    company: str
    forecast_date: str
    history_start: str
    history_end: str
    history_source: str
    model: str
    features: list[str]
    open_hours: str
    location_count: int = Field(ge=0)
    source: str
    locations: list[LocationDemand]
    procurement: ProcurementRollup


@router.get("/demand", response_model=DemandForecast)
def demand_forecast(
    forecast_date: date | None = Query(
        default=None,
        alias="date",
        description="Day to forecast (YYYY-MM-DD). Default is tomorrow in America/Bogota.",
    ),
    location_id: str | None = Query(default=None, description="One of the 14 location ids"),
) -> DemandForecast:
    day = forecast_date or default_forecast_date()
    try:
        payload = forecast_demand(day, location_id=location_id)
    except UnknownLocationError as error:
        raise HTTPException(status_code=404, detail="Location was not found.") from error
    return DemandForecast.model_validate(payload)
