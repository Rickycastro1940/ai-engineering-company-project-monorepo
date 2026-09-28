"""Brasaland locations API — Technology / Operations domain from CONTEXT.md.

CONTEXT.md: 14 company-owned restaurants in Colombia and Florida (US).
Operations needs sales visibility per location in COP and USD.
Roster rows live in SQLite (`central_store`) so they survive process restarts.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from users import get_current_user

import central_store

router = APIRouter(
    prefix="/locations",
    tags=["locations"],
    dependencies=[Depends(get_current_user)],
)

Country = Literal["Colombia", "United States"]
Currency = Literal["COP", "USD"]


class Location(BaseModel):
    id: str
    name: str
    city: str
    country: Country
    currency: Currency
    region: str = Field(description="Operating market label for dashboards")


class LocationsOverview(BaseModel):
    """Company-relevant summary for the internal backoffice welcome screen."""

    company: str = "Brasaland"
    total_locations: int
    countries: list[str]
    currencies: list[Currency]
    colombia_count: int
    florida_count: int
    source: str = "CONTEXT.md — 14 company-owned restaurants, Colombia + Florida"
    locations: list[Location]


# Seeded roster aligned with CONTEXT.md (14 locations, two markets, two currencies).
# Named cities are illustrative operational anchors; count and markets are briefing facts.
_SEED_LOCATIONS: list[Location] = [
    Location(
        id="co-med-centro",
        name="Medellín Centro",
        city="Medellín",
        country="Colombia",
        currency="COP",
        region="Colombia",
    ),
    Location(
        id="co-med-elpoblado",
        name="Medellín El Poblado",
        city="Medellín",
        country="Colombia",
        currency="COP",
        region="Colombia",
    ),
    Location(
        id="co-bog-chapinero",
        name="Bogotá Chapinero",
        city="Bogotá",
        country="Colombia",
        currency="COP",
        region="Colombia",
    ),
    Location(
        id="co-bog-norte",
        name="Bogotá Norte",
        city="Bogotá",
        country="Colombia",
        currency="COP",
        region="Colombia",
    ),
    Location(
        id="co-cali-norte",
        name="Cali Norte",
        city="Cali",
        country="Colombia",
        currency="COP",
        region="Colombia",
    ),
    Location(
        id="co-barranquilla",
        name="Barranquilla",
        city="Barranquilla",
        country="Colombia",
        currency="COP",
        region="Colombia",
    ),
    Location(
        id="co-cartagena",
        name="Cartagena",
        city="Cartagena",
        country="Colombia",
        currency="COP",
        region="Colombia",
    ),
    Location(
        id="co-pereira",
        name="Pereira",
        city="Pereira",
        country="Colombia",
        currency="COP",
        region="Colombia",
    ),
    Location(
        id="us-mia-brickell",
        name="Miami Brickell",
        city="Miami",
        country="United States",
        currency="USD",
        region="Florida",
    ),
    Location(
        id="us-mia-downtown",
        name="Miami Downtown",
        city="Miami",
        country="United States",
        currency="USD",
        region="Florida",
    ),
    Location(
        id="us-orlando",
        name="Orlando",
        city="Orlando",
        country="United States",
        currency="USD",
        region="Florida",
    ),
    Location(
        id="us-tampa",
        name="Tampa",
        city="Tampa",
        country="United States",
        currency="USD",
        region="Florida",
    ),
    Location(
        id="us-ftlauderdale",
        name="Fort Lauderdale",
        city="Fort Lauderdale",
        country="United States",
        currency="USD",
        region="Florida",
    ),
    Location(
        id="us-jacksonville",
        name="Jacksonville",
        city="Jacksonville",
        country="United States",
        currency="USD",
        region="Florida",
    ),
]


def _ensure_seeded() -> None:
    central_store.seed_locations([row.model_dump() for row in _SEED_LOCATIONS])


def location_roster() -> list[Location]:
    """14 company-owned restaurants from CONTEXT.md (Colombia + Florida)."""
    _ensure_seeded()
    return [Location(**row) for row in central_store.list_locations()]


def all_locations() -> list[Location]:
    """Roster other central-API routers join against (sales, customers)."""
    return location_roster()


def get_location(location_id: str) -> Location | None:
    _ensure_seeded()
    row = central_store.get_location(location_id)
    return Location(**row) if row is not None else None


@router.get("", response_model=list[Location])
def list_locations() -> list[Location]:
    return location_roster()


@router.get("/overview", response_model=LocationsOverview)
def locations_overview() -> LocationsOverview:
    locations = location_roster()
    colombia = [loc for loc in locations if loc.country == "Colombia"]
    florida = [loc for loc in locations if loc.region == "Florida"]
    return LocationsOverview(
        total_locations=len(locations),
        countries=sorted({loc.country for loc in locations}),
        currencies=["COP", "USD"],
        colombia_count=len(colombia),
        florida_count=len(florida),
        locations=locations,
    )
