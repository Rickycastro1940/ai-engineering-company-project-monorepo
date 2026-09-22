"""Brasaland sales API — Operations / Executive domain from CONTEXT.md.

Felipe needs per-location sales in COP and USD. Mariana needs chain totals
in both currencies. POS systems are not integrated; this is a seeded snapshot.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from users import get_current_user

from locations import all_locations, get_location

router = APIRouter(
    prefix="/sales",
    tags=["sales"],
    dependencies=[Depends(get_current_user)],
)

Currency = Literal["COP", "USD"]

# Illustrative reporting FX only — not a live feed (CONTEXT.md: no POS integration).
ILLUSTRATIVE_USD_COP = 4000
REPORTING_WEEK = "2026-09-15"


class LocationSales(BaseModel):
    location_id: str
    location_name: str
    country: str
    region: str
    currency: Currency
    covers: int = Field(ge=0)
    amount_local: float = Field(ge=0)
    amount_cop: float = Field(ge=0)
    amount_usd: float = Field(ge=0)
    open_hours: str
    no_sales_during_open_hours: bool


class SalesOverview(BaseModel):
    company: str = "Brasaland"
    reporting_week_start: str
    total_locations: int
    currencies: list[Currency]
    chain_total_cop: float
    chain_total_usd: float
    colombia_total_cop: float
    florida_total_usd: float
    no_sales_alerts: list[str]
    source: str = (
        "CONTEXT.md Operations + Executive — COP and USD; "
        "seeded snapshot (POS not integrated)"
    )
    fx_note: str = (
        f"amount_cop/amount_usd use illustrative USD:COP={ILLUSTRATIVE_USD_COP} "
        "for dual-currency dashboards; not a live FX feed"
    )
    locations: list[LocationSales]


def _to_cop(amount: float, currency: Currency) -> float:
    if currency == "COP":
        return amount
    return amount * ILLUSTRATIVE_USD_COP


def _to_usd(amount: float, currency: Currency) -> float:
    if currency == "USD":
        return amount
    return round(amount / ILLUSTRATIVE_USD_COP, 2)


def _seed_row(location_id: str, covers: int, amount_local: float) -> LocationSales:
    location = get_location(location_id)
    if location is None:
        raise RuntimeError(f"Unknown location seed {location_id}")
    return LocationSales(
        location_id=location.id,
        location_name=location.name,
        country=location.country,
        region=location.region,
        currency=location.currency,
        covers=covers,
        amount_local=amount_local,
        amount_cop=_to_cop(amount_local, location.currency),
        amount_usd=_to_usd(amount_local, location.currency),
        open_hours="11:00-22:00 local",
        no_sales_during_open_hours=covers == 0 or amount_local == 0,
    )


# Deterministic weekly snapshot for the 14 CONTEXT.md locations.
_SALES: list[LocationSales] = [
    _seed_row("co-med-centro", 412, 38_400_000),
    _seed_row("co-med-elpoblado", 388, 41_200_000),
    _seed_row("co-bog-chapinero", 355, 36_800_000),
    _seed_row("co-bog-norte", 341, 35_100_000),
    _seed_row("co-cali-norte", 298, 29_400_000),
    _seed_row("co-barranquilla", 276, 27_200_000),
    _seed_row("co-cartagena", 264, 31_600_000),
    _seed_row("co-pereira", 221, 22_800_000),
    _seed_row("us-mia-brickell", 402, 11_400),
    _seed_row("us-mia-downtown", 376, 10_250),
    _seed_row("us-orlando", 318, 8_900),
    _seed_row("us-tampa", 291, 8_150),
    _seed_row("us-ftlauderdale", 274, 7_820),
    _seed_row("us-jacksonville", 248, 6_940),
]


def _overview() -> SalesOverview:
    colombia = [row for row in _SALES if row.region == "Colombia"]
    florida = [row for row in _SALES if row.region == "Florida"]
    alerts = [row.location_id for row in _SALES if row.no_sales_during_open_hours]
    return SalesOverview(
        reporting_week_start=REPORTING_WEEK,
        total_locations=len(_SALES),
        currencies=["COP", "USD"],
        chain_total_cop=sum(row.amount_cop for row in _SALES),
        chain_total_usd=sum(row.amount_usd for row in _SALES),
        colombia_total_cop=sum(row.amount_cop for row in colombia),
        florida_total_usd=sum(row.amount_usd for row in florida),
        no_sales_alerts=alerts,
        locations=list(_SALES),
    )


@router.get("", response_model=list[LocationSales])
def list_sales() -> list[LocationSales]:
    return list(_SALES)


@router.get("/overview", response_model=SalesOverview)
def sales_overview() -> SalesOverview:
    overview = _overview()
    if overview.total_locations != len(all_locations()):
        raise HTTPException(status_code=500, detail="Sales snapshot is missing locations.")
    return overview


@router.get("/alerts", response_model=list[LocationSales])
def sales_alerts() -> list[LocationSales]:
    """Locations with no covers/sales in the snapshot during opening hours."""
    return [row for row in _SALES if row.no_sales_during_open_hours]


@router.get("/{location_id}", response_model=LocationSales)
def get_location_sales(location_id: str) -> LocationSales:
    for row in _SALES:
        if row.location_id == location_id:
            return row
    raise HTTPException(status_code=404, detail="Sales for that location were not found.")
