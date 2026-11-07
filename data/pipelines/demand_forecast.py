"""Next-day demand forecast for Brasaland kitchens and purchasing.

Restaurant Operations (Felipe Guerrero) needs ingredient orders based on
history, not WhatsApp guesses. Procurement (Lucía Fernández) needs a
chain view of protein and produce in both markets. Marketing's Brasa
Points stay on physical stamp cards (CONTEXT.md); this only forecasts
how many points those cards would earn.

History is mocked. There is no live POS or invoice feed. Colombia
locations stay in COP and Florida locations stay in USD.

The model is scikit-learn ``Ridge``. Features are location, hour, day of
week, a local holiday flag, temperature, and rain.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Iterable

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

HISTORY_DAYS = 180
OPEN_HOURS = tuple(range(11, 22))  # 11:00–22:00 local, same window as sales
MODEL_NAME = "sklearn.linear_model.Ridge"

# Weekly covers and local-currency sales. Scale matches services/api/sales.py
# (about one week of a USD 6 million year). Colombia amounts are COP.
_WEEKLY: tuple[tuple[str, str, str, str, str, str, int, float], ...] = (
    ("co-med-centro", "Medellín Centro", "Medellín", "Colombia", "COP", "Colombia", 412, 38_400_000),
    ("co-med-elpoblado", "Medellín El Poblado", "Medellín", "Colombia", "COP", "Colombia", 388, 41_200_000),
    ("co-bog-chapinero", "Bogotá Chapinero", "Bogotá", "Colombia", "COP", "Colombia", 355, 36_800_000),
    ("co-bog-norte", "Bogotá Norte", "Bogotá", "Colombia", "COP", "Colombia", 341, 35_100_000),
    ("co-cali-norte", "Cali Norte", "Cali", "Colombia", "COP", "Colombia", 298, 29_400_000),
    ("co-barranquilla", "Barranquilla", "Barranquilla", "Colombia", "COP", "Colombia", 276, 27_200_000),
    ("co-cartagena", "Cartagena", "Cartagena", "Colombia", "COP", "Colombia", 264, 31_600_000),
    ("co-pereira", "Pereira", "Pereira", "Colombia", "COP", "Colombia", 221, 22_800_000),
    ("us-mia-brickell", "Miami Brickell", "Miami", "United States", "USD", "Florida", 402, 11_400),
    ("us-mia-downtown", "Miami Downtown", "Miami", "United States", "USD", "Florida", 376, 10_250),
    ("us-orlando", "Orlando", "Orlando", "United States", "USD", "Florida", 318, 8_900),
    ("us-tampa", "Tampa", "Tampa", "United States", "USD", "Florida", 291, 8_150),
    ("us-ftlauderdale", "Fort Lauderdale", "Fort Lauderdale", "United States", "USD", "Florida", 274, 7_820),
    ("us-jacksonville", "Jacksonville", "Jacksonville", "United States", "USD", "Florida", 248, 6_940),
)

# Share of the day at each open hour. Evening service is the peak.
_HOUR_RAW = {
    11: 0.55,
    12: 1.15,
    13: 1.45,
    14: 1.05,
    15: 0.70,
    16: 0.55,
    17: 0.75,
    18: 1.20,
    19: 1.70,
    20: 1.35,
    21: 0.85,
}
_HOUR_SHARE = {hour: weight / sum(_HOUR_RAW.values()) for hour, weight in _HOUR_RAW.items()}
_DOW_FACTOR = {0: 0.84, 1: 0.90, 2: 0.96, 3: 1.00, 4: 1.18, 5: 1.32, 6: 1.05}

# Kilograms per cover. Same recipes in every kitchen (CONTEXT.md Training).
PER_COVER_KG = {
    "beef_kg": 0.085,
    "chicken_kg": 0.055,
    "pork_kg": 0.060,
    "greens_kg": 0.030,
    "tomato_kg": 0.015,
    "onion_kg": 0.012,
}
PROTEIN_KEYS = ("beef_kg", "chicken_kg", "pork_kg")
PRODUCE_KEYS = ("greens_kg", "tomato_kg", "onion_kg")

# Illustrative supplier prices for a purchase suggestion. Not invoice history.
UNIT_PRICE = {
    "COP": {
        "beef_kg": 28_000,
        "chicken_kg": 12_000,
        "pork_kg": 18_000,
        "greens_kg": 4_500,
        "tomato_kg": 3_200,
        "onion_kg": 2_400,
    },
    "USD": {
        "beef_kg": 9.40,
        "chicken_kg": 4.10,
        "pork_kg": 6.20,
        "greens_kg": 2.40,
        "tomato_kg": 1.90,
        "onion_kg": 1.30,
    },
}

CITY_BASE_C = {
    "Medellín": 22.0,
    "Bogotá": 14.0,
    "Cali": 24.0,
    "Barranquilla": 28.5,
    "Cartagena": 29.0,
    "Pereira": 21.0,
    "Miami": 27.5,
    "Orlando": 26.0,
    "Tampa": 25.5,
    "Fort Lauderdale": 27.0,
    "Jacksonville": 23.5,
}

HOURLY_CATEGORICAL = ["location_id", "hour", "day_of_week"]
HOURLY_NUMERIC = ["is_holiday", "rain", "temperature_c"]
DAILY_CATEGORICAL = ["location_id", "day_of_week"]
DAILY_NUMERIC = ["is_holiday", "rain", "temperature_c"]
DAILY_TARGETS = list(PER_COVER_KG) + ["brasa_points", "stamp_card_visits"]

# CONTEXT.md: about 60% of customers do not use the stamp card.
STAMP_CARD_USE = 0.40
POINTS_PER_COP = 10_000
POINTS_PER_USD = 10


class UnknownLocationError(LookupError):
    """Raised when a forecast is requested for an id outside the 14 locations."""

    def __init__(self, location_id: str) -> None:
        self.location_id = location_id
        super().__init__(location_id)


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    city: str
    country: str
    currency: str
    region: str
    weekly_covers: int
    weekly_sales: float

    @property
    def daily_base_covers(self) -> float:
        return self.weekly_covers / 7.0

    @property
    def average_ticket(self) -> float:
        return self.weekly_sales / self.weekly_covers


def roster() -> list[Site]:
    """14 company-owned restaurants (Colombia + Florida)."""
    return [
        Site(
            id=row[0],
            name=row[1],
            city=row[2],
            country=row[3],
            currency=row[4],
            region=row[5],
            weekly_covers=row[6],
            weekly_sales=row[7],
        )
        for row in _WEEKLY
    ]


def roster_ids() -> list[str]:
    return [site.id for site in roster()]


def get_site(location_id: str) -> Site:
    for site in roster():
        if site.id == location_id:
            return site
    raise UnknownLocationError(location_id)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    shift = (weekday - first.weekday()) % 7
    return date(year, month, 1 + shift + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        cursor = date(year, 12, 31)
    else:
        cursor = date(year, month + 1, 1) - timedelta(days=1)
    while cursor.weekday() != weekday:
        cursor -= timedelta(days=1)
    return cursor


def holiday_name(site: Site, day: date) -> str | None:
    """Local public holiday. Colombia and Florida do not share a calendar."""
    if site.country == "Colombia":
        names = {
            (1, 1): "New Year's Day",
            (5, 1): "Labour Day",
            (7, 20): "Independence Day",
            (8, 7): "Battle of Boyacá",
            (12, 8): "Immaculate Conception",
            (12, 25): "Christmas Day",
        }
        return names.get((day.month, day.day))
    names = {
        (1, 1): "New Year's Day",
        (7, 4): "Independence Day",
        (12, 25): "Christmas Day",
    }
    if day == _nth_weekday(day.year, 11, 3, 4):
        return "Thanksgiving"
    if day == _last_weekday(day.year, 5, 0):
        return "Memorial Day"
    if day == _nth_weekday(day.year, 9, 0, 1):
        return "Labor Day"
    return names.get((day.month, day.day))


def mock_weather(site: Site, day: date) -> tuple[float, bool]:
    """Deterministic temperature (°C) and rain flag. Not a live weather feed."""
    doy = day.timetuple().tm_yday
    seasonal = 4.0 * math.sin(2 * math.pi * (doy - 110) / 365.0)
    if site.region == "Florida":
        seasonal *= 1.6
    temperature = CITY_BASE_C[site.city] + seasonal
    offset = sum(ord(char) for char in site.id)
    rain = (day.toordinal() + offset) % 5 == 0
    return round(temperature, 1), rain


def _temp_factor(temperature_c: float) -> float:
    return min(1.12, max(0.78, 1.0 - 0.01 * (temperature_c - 22.0)))


def hourly_covers(
    site: Site,
    day: date,
    hour: int,
    *,
    is_holiday: bool,
    rain: bool,
    temperature_c: float,
) -> float:
    """Mocked covers for one open hour. Holidays lift demand; rain and heat cut it."""
    covers = site.daily_base_covers * _HOUR_SHARE[hour]
    covers *= _DOW_FACTOR[day.weekday()]
    covers *= 1.48 if is_holiday else 1.0
    covers *= 0.74 if rain else 1.0
    covers *= _temp_factor(temperature_c)
    wobble = 1.0 + 0.015 * math.sin((day.toordinal() + hour) / 3.0)
    return max(0.0, covers * wobble)


def _daily_covers(site: Site, day: date, *, is_holiday: bool, rain: bool, temperature_c: float) -> float:
    return sum(
        hourly_covers(
            site,
            day,
            hour,
            is_holiday=is_holiday,
            rain=rain,
            temperature_c=temperature_c,
        )
        for hour in OPEN_HOURS
    )


def _points_earned(site: Site, covers: float) -> float:
    spend = covers * site.average_ticket
    divisor = POINTS_PER_COP if site.currency == "COP" else POINTS_PER_USD
    return spend / divisor


def _daterange(start: date, end: date) -> Iterable[date]:
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def _encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:  # pragma: no cover - older scikit-learn
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def _hourly_pipeline() -> Pipeline:
    prep = ColumnTransformer(
        [
            ("cat", _encoder(), HOURLY_CATEGORICAL),
            ("num", StandardScaler(), HOURLY_NUMERIC),
        ]
    )
    return Pipeline([("prep", prep), ("model", Ridge(alpha=1.0))])


def _daily_pipeline() -> Pipeline:
    prep = ColumnTransformer(
        [
            ("cat", _encoder(), DAILY_CATEGORICAL),
            ("num", StandardScaler(), DAILY_NUMERIC),
        ]
    )
    return Pipeline(
        [
            ("prep", prep),
            ("model", MultiOutputRegressor(Ridge(alpha=1.0))),
        ]
    )


def _history_frames(history_end: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = history_end - timedelta(days=HISTORY_DAYS - 1)
    hourly_rows: list[dict] = []
    daily_rows: list[dict] = []
    for day in _daterange(start, history_end):
        for site in roster():
            name = holiday_name(site, day)
            is_holiday = name is not None
            temperature_c, rain = mock_weather(site, day)
            covers = _daily_covers(
                site,
                day,
                is_holiday=is_holiday,
                rain=rain,
                temperature_c=temperature_c,
            )
            for hour in OPEN_HOURS:
                hourly_rows.append(
                    {
                        "location_id": site.id,
                        "hour": str(hour),
                        "day_of_week": str(day.weekday()),
                        "is_holiday": int(is_holiday),
                        "rain": int(rain),
                        "temperature_c": temperature_c,
                        "covers": hourly_covers(
                            site,
                            day,
                            hour,
                            is_holiday=is_holiday,
                            rain=rain,
                            temperature_c=temperature_c,
                        ),
                    }
                )
            row = {
                "location_id": site.id,
                "day_of_week": str(day.weekday()),
                "is_holiday": int(is_holiday),
                "rain": int(rain),
                "temperature_c": temperature_c,
                "brasa_points": _points_earned(site, covers),
                "stamp_card_visits": covers * STAMP_CARD_USE,
            }
            for key, per_cover in PER_COVER_KG.items():
                row[key] = covers * per_cover
            daily_rows.append(row)
    return pd.DataFrame(hourly_rows), pd.DataFrame(daily_rows)


@dataclass
class FittedModels:
    history_start: date
    history_end: date
    hourly: Pipeline
    daily: Pipeline


@lru_cache(maxsize=4)
def fit_models(history_end: date) -> FittedModels:
    """Fit on mocked days up to and including ``history_end``."""
    hourly_frame, daily_frame = _history_frames(history_end)
    hourly = _hourly_pipeline()
    hourly.fit(hourly_frame[HOURLY_CATEGORICAL + HOURLY_NUMERIC], hourly_frame["covers"])
    daily = _daily_pipeline()
    daily.fit(daily_frame[DAILY_CATEGORICAL + DAILY_NUMERIC], daily_frame[DAILY_TARGETS])
    history_start = history_end - timedelta(days=HISTORY_DAYS - 1)
    return FittedModels(history_start, history_end, hourly, daily)


def score_hourly_covers(
    models: FittedModels,
    site: Site,
    day: date,
    hour: int,
    *,
    is_holiday: bool,
    rain: bool,
    temperature_c: float,
) -> float:
    frame = pd.DataFrame(
        [
            {
                "location_id": site.id,
                "hour": str(hour),
                "day_of_week": str(day.weekday()),
                "is_holiday": int(is_holiday),
                "rain": int(rain),
                "temperature_c": float(temperature_c),
            }
        ]
    )
    predicted = float(models.hourly.predict(frame)[0])
    return max(0.0, predicted)


def score_daily(
    models: FittedModels,
    site: Site,
    day: date,
    *,
    is_holiday: bool,
    rain: bool,
    temperature_c: float,
) -> dict[str, float]:
    frame = pd.DataFrame(
        [
            {
                "location_id": site.id,
                "day_of_week": str(day.weekday()),
                "is_holiday": int(is_holiday),
                "rain": int(rain),
                "temperature_c": float(temperature_c),
            }
        ]
    )
    predicted = models.daily.predict(frame)[0]
    return {key: max(0.0, float(value)) for key, value in zip(DAILY_TARGETS, predicted)}


def _money(amount: float, currency: str) -> float:
    if currency == "COP":
        return float(round(amount))
    return round(amount, 2)


def _kg_map(scores: dict[str, float], keys: tuple[str, ...]) -> dict[str, float]:
    return {key: round(scores[key], 2) for key in keys}


def _purchase_cost(scores: dict[str, float], currency: str) -> float:
    prices = UNIT_PRICE[currency]
    total = sum(scores[key] * prices[key] for key in PER_COVER_KG)
    return _money(total, currency)


def default_forecast_date() -> date:
    """Next calendar day in America/Bogota (the chain's reporting timezone)."""
    try:
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("America/Bogota")).date()
    except Exception:
        today = date.today()
    return today + timedelta(days=1)


def forecast_demand(forecast_on: date, location_id: str | None = None) -> dict:
    """Forecast one day for every location, or for a single location id."""
    sites = roster()
    if location_id is not None:
        sites = [get_site(location_id)]
    history_end = forecast_on - timedelta(days=1)
    models = fit_models(history_end)
    locations: list[dict] = []
    for site in sites:
        name = holiday_name(site, forecast_on)
        is_holiday = name is not None
        temperature_c, rain = mock_weather(site, forecast_on)
        hourly = []
        for hour in OPEN_HOURS:
            covers = score_hourly_covers(
                models,
                site,
                forecast_on,
                hour,
                is_holiday=is_holiday,
                rain=rain,
                temperature_c=temperature_c,
            )
            hourly.append(
                {
                    "hour": hour,
                    "label": f"{hour:02d}:00-{hour + 1:02d}:00 local",
                    "covers": round(covers, 1),
                }
            )
        peak = max(hourly, key=lambda row: row["covers"])
        daily = score_daily(
            models,
            site,
            forecast_on,
            is_holiday=is_holiday,
            rain=rain,
            temperature_c=temperature_c,
        )
        protein = _kg_map(daily, PROTEIN_KEYS)
        produce = _kg_map(daily, PRODUCE_KEYS)
        locations.append(
            {
                "location_id": site.id,
                "location_name": site.name,
                "city": site.city,
                "country": site.country,
                "region": site.region,
                "currency": site.currency,
                "holiday": name,
                "weather": {"temperature_c": temperature_c, "rain": rain},
                "peak_hour": peak["hour"],
                "peak_label": peak["label"],
                "peak_covers": peak["covers"],
                "hourly_covers": hourly,
                "protein_kg": protein,
                "produce_kg": produce,
                "estimated_purchase_local": _purchase_cost(daily, site.currency),
                "loyalty": {
                    "program": "Brasa Points",
                    "medium": "physical_stamp_card",
                    "digital_loyalty": False,
                    "expected_stamp_card_visits": round(daily["stamp_card_visits"], 1),
                    "expected_brasa_points_earned": round(daily["brasa_points"], 1),
                    "points_rule": (
                        "Physical stamp card: 1 Brasa Point per 10,000 COP or 10 USD. "
                        "About 60% of customers do not use the card. Digital wallet is not live."
                    ),
                },
            }
        )
    return {
        "company": "Brasaland",
        "forecast_date": forecast_on.isoformat(),
        "history_start": models.history_start.isoformat(),
        "history_end": models.history_end.isoformat(),
        "history_source": "mocked",
        "model": MODEL_NAME,
        "features": [
            "location_id",
            "hour",
            "day_of_week",
            "local_holiday",
            "temperature_c",
            "rain",
        ],
        "open_hours": "11:00-22:00 local",
        "location_count": len(locations),
        "source": (
            "CONTEXT.md Operations — ingredient orders from historical sales; "
            "Procurement — consolidated protein and produce for Colombia (COP) and Florida (USD). "
            "Mocked history, not a live POS or invoice feed."
        ),
        "locations": locations,
        "procurement": _rollup(locations),
    }


def _rollup(locations: list[dict]) -> dict:
    protein = {key: 0.0 for key in PROTEIN_KEYS}
    produce = {key: 0.0 for key in PRODUCE_KEYS}
    purchase_cop = 0.0
    purchase_usd = 0.0
    points = 0.0
    for row in locations:
        for key in PROTEIN_KEYS:
            protein[key] += row["protein_kg"][key]
        for key in PRODUCE_KEYS:
            produce[key] += row["produce_kg"][key]
        if row["currency"] == "COP":
            purchase_cop += row["estimated_purchase_local"]
        else:
            purchase_usd += row["estimated_purchase_local"]
        points += row["loyalty"]["expected_brasa_points_earned"]
    return {
        "protein_kg": {key: round(value, 2) for key, value in protein.items()},
        "produce_kg": {key: round(value, 2) for key, value in produce.items()},
        "estimated_purchase_cop": float(round(purchase_cop)),
        "estimated_purchase_usd": round(purchase_usd, 2),
        "expected_brasa_points_earned": round(points, 1),
        "note": (
            "Illustrative protein and produce prices for central ordering. "
            "COP and USD stay separate. Not a live supplier invoice."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Brasaland next-day demand forecast (mocked history)")
    parser.add_argument("--date", help="Forecast date YYYY-MM-DD (default: tomorrow America/Bogota)")
    parser.add_argument("--location", help="One location id, for example co-med-centro")
    args = parser.parse_args(argv)
    forecast_on = date.fromisoformat(args.date) if args.date else default_forecast_date()
    try:
        payload = forecast_demand(forecast_on, location_id=args.location)
    except UnknownLocationError:
        print(f"Unknown location: {args.location}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
