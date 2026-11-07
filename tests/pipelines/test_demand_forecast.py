"""Mocked demand forecast: peak hour, protein/produce, holidays, weather, loyalty."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.pipelines.demand_forecast import (  # noqa: E402
    OPEN_HOURS,
    UnknownLocationError,
    fit_models,
    forecast_demand,
    get_site,
    holiday_name,
    roster,
    roster_ids,
    score_daily,
    score_hourly_covers,
)

FORECAST_ON = date(2026, 11, 9)  # Monday, not a holiday in either market


def test_roster_is_fourteen_locations_in_two_currencies() -> None:
    sites = roster()
    assert len(sites) == 14
    assert len(roster_ids()) == len(set(roster_ids()))
    colombia = [site for site in sites if site.country == "Colombia"]
    florida = [site for site in sites if site.region == "Florida"]
    assert len(colombia) == 8
    assert len(florida) == 6
    assert {site.currency for site in colombia} == {"COP"}
    assert {site.currency for site in florida} == {"USD"}


def test_roster_ids_match_the_central_api() -> None:
    services_api = REPO_ROOT / "services" / "api"
    if str(services_api) not in sys.path:
        sys.path.insert(0, str(services_api))
    from locations import location_roster

    assert roster_ids() == [location.id for location in location_roster()]
    assert [site.currency for site in roster()] == [location.currency for location in location_roster()]


def test_holiday_calendars_stay_in_their_market() -> None:
    colombia = get_site("co-med-centro")
    florida = get_site("us-mia-brickell")
    assert holiday_name(colombia, date(2026, 7, 20)) == "Independence Day"
    assert holiday_name(colombia, date(2026, 8, 7)) == "Battle of Boyacá"
    assert holiday_name(colombia, date(2026, 7, 4)) is None
    assert holiday_name(colombia, date(2026, 11, 26)) is None
    assert holiday_name(florida, date(2026, 7, 4)) == "Independence Day"
    assert holiday_name(florida, date(2026, 11, 26)) == "Thanksgiving"
    assert holiday_name(florida, date(2026, 5, 25)) == "Memorial Day"
    assert holiday_name(florida, date(2026, 9, 7)) == "Labor Day"
    assert holiday_name(florida, date(2026, 7, 20)) is None
    assert holiday_name(florida, date(2026, 8, 7)) is None


def test_ridge_lifts_a_holiday_and_cuts_rain_and_heat() -> None:
    models = fit_models(FORECAST_ON - timedelta(days=1))
    site = get_site("co-bog-chapinero")
    holiday = score_hourly_covers(
        models, site, FORECAST_ON, 19, is_holiday=True, rain=False, temperature_c=18.0
    )
    ordinary = score_hourly_covers(
        models, site, FORECAST_ON, 19, is_holiday=False, rain=False, temperature_c=18.0
    )
    wet = score_hourly_covers(
        models, site, FORECAST_ON, 19, is_holiday=False, rain=True, temperature_c=18.0
    )
    hot = score_hourly_covers(
        models, site, FORECAST_ON, 13, is_holiday=False, rain=False, temperature_c=32.0
    )
    cool = score_hourly_covers(
        models, site, FORECAST_ON, 13, is_holiday=False, rain=False, temperature_c=16.0
    )
    assert holiday > ordinary
    assert wet < ordinary
    assert hot < cool

    holiday_order = score_daily(
        models, site, FORECAST_ON, is_holiday=True, rain=False, temperature_c=18.0
    )
    ordinary_order = score_daily(
        models, site, FORECAST_ON, is_holiday=False, rain=False, temperature_c=18.0
    )
    assert holiday_order["beef_kg"] > ordinary_order["beef_kg"]
    assert holiday_order["greens_kg"] > ordinary_order["greens_kg"]
    assert holiday_order["brasa_points"] > ordinary_order["brasa_points"]


def test_forecast_covers_both_markets_and_peaks_inside_open_hours() -> None:
    payload = forecast_demand(FORECAST_ON)
    assert payload["company"] == "Brasaland"
    assert payload["history_source"] == "mocked"
    assert payload["model"].startswith("sklearn")
    assert payload["location_count"] == 14
    currencies = {row["currency"] for row in payload["locations"]}
    assert currencies == {"COP", "USD"}
    regions = {row["region"] for row in payload["locations"]}
    assert regions == {"Colombia", "Florida"}
    for row in payload["locations"]:
        assert row["peak_hour"] in OPEN_HOURS
        assert row["peak_covers"] > 0
        assert row["hourly_covers"][0]["hour"] == 11
        assert row["hourly_covers"][-1]["hour"] == 21
        assert row["protein_kg"]["beef_kg"] > 0
        assert row["protein_kg"]["chicken_kg"] > 0
        assert row["protein_kg"]["pork_kg"] > 0
        assert row["produce_kg"]["greens_kg"] > 0
        assert row["estimated_purchase_local"] > 0
        assert row["loyalty"]["digital_loyalty"] is False
        assert row["loyalty"]["medium"] == "physical_stamp_card"
        assert row["loyalty"]["expected_brasa_points_earned"] > 0
        assert "10,000 COP" in row["loyalty"]["points_rule"]
    rollup = payload["procurement"]
    assert rollup["estimated_purchase_cop"] > 0
    assert rollup["estimated_purchase_usd"] > 0
    assert rollup["protein_kg"]["beef_kg"] > 0
    cop_rows = [row for row in payload["locations"] if row["currency"] == "COP"]
    usd_rows = [row for row in payload["locations"] if row["currency"] == "USD"]
    assert rollup["estimated_purchase_cop"] == pytest.approx(
        sum(row["estimated_purchase_local"] for row in cop_rows)
    )
    assert rollup["estimated_purchase_usd"] == pytest.approx(
        sum(row["estimated_purchase_local"] for row in usd_rows)
    )


def test_single_location_and_unknown_id() -> None:
    payload = forecast_demand(FORECAST_ON, location_id="us-tampa")
    assert payload["location_count"] == 1
    assert payload["locations"][0]["location_id"] == "us-tampa"
    assert payload["locations"][0]["currency"] == "USD"
    assert payload["procurement"]["estimated_purchase_cop"] == 0
    assert payload["procurement"]["estimated_purchase_usd"] > 0
    with pytest.raises(UnknownLocationError):
        forecast_demand(FORECAST_ON, location_id="co-unknown")


def test_repeat_calls_match() -> None:
    first = forecast_demand(FORECAST_ON, location_id="co-med-centro")
    second = forecast_demand(FORECAST_ON, location_id="co-med-centro")
    assert first == second
