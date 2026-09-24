"""Unit tests for Brasaland weekly location KPI transform (Part 2).

Fixtures and expected values follow data/pipelines/PIPELINE_DESIGN.md and
data/eval/weekly_location_performance_fixtures.json (CONTEXT.md roster ids).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from data.pipelines.pipeline import _supabase_client
from data.process.location_kpis import aggregate_location_kpis

_EVAL = Path(__file__).resolve().parents[2] / "data" / "eval" / "weekly_location_performance_fixtures.json"


def _load_eval() -> dict:
    with open(_EVAL, encoding="utf-8") as handle:
        return json.load(handle)


def test_aggregate_location_kpis_from_eval_fixtures():
    """Hand-calculated KPIs for us-mia-downtown and co-med-centro."""
    fixture = _load_eval()
    events = []
    locations = []
    for loc in fixture["locations"]:
        events.extend(loc["events"])
        locations.append(
            {
                "id": loc["location_id"],
                "country": loc["country"],
                "currency": loc["currency"],
            }
        )

    result_df = aggregate_location_kpis(
        pd.DataFrame(events),
        pd.DataFrame(locations),
        fixture["week_start"],
    )
    assert len(result_df) == 2

    for loc in fixture["locations"]:
        row = result_df[result_df["location_id"] == loc["location_id"]].iloc[0]
        expected = loc["expected"]
        assert row["total_purchase_cost"] == expected["total_purchase_cost"]
        assert row["total_waste_cost"] == expected["total_waste_cost"]
        assert row["waste_ratio"] == expected["waste_ratio"]
        assert row["stockout_events_count"] == expected["stockout_events_count"]
        assert row["price_alert_events_count"] == expected["price_alert_events_count"]
        assert row["country"] == loc["country"]
        assert row["currency"] == loc["currency"]
        assert row["week_start"] == fixture["week_start"]


def test_aggregate_location_kpis_dedupes_event_id():
    """Corrected inbound cost on the same telemetry_events.id replaces, not stacks."""
    fixture = _load_eval()
    case = fixture["dedupe_case"]
    locations_df = pd.DataFrame(
        [{"id": "us-mia-downtown", "country": "United States", "currency": "USD"}]
    )
    result_df = aggregate_location_kpis(
        pd.DataFrame(case["events"]),
        locations_df,
        fixture["week_start"],
    )
    assert result_df.iloc[0]["total_purchase_cost"] == case["expected_purchase_cost"]


def test_aggregate_location_kpis_empty_input():
    result_df = aggregate_location_kpis(pd.DataFrame(), pd.DataFrame(), "2026-09-21")
    assert result_df.empty


def test_aggregate_location_kpis_non_dict_payload():
    telemetry_df = pd.DataFrame(
        {
            "id": ["x1"],
            "event_type": ["inbound_order_created"],
            "event_payload": ["not-a-dict"],
        }
    )
    locations_df = pd.DataFrame(
        [{"id": "co-med-centro", "country": "Colombia", "currency": "COP"}]
    )
    result_df = aggregate_location_kpis(telemetry_df, locations_df, "2026-09-21")
    assert result_df.empty


def test_aggregate_location_kpis_malformed_payload():
    telemetry_df = pd.DataFrame(
        {
            "id": ["a", "b"],
            "event_type": ["inbound_order_created", "stock_waste_registered"],
            "event_payload": [
                {"location_id": "co-bog-norte"},
                {"location_id": "co-bog-norte"},
            ],
        }
    )
    locations_df = pd.DataFrame(
        [{"id": "co-bog-norte", "country": "Colombia", "currency": "COP"}]
    )
    result_df = aggregate_location_kpis(telemetry_df, locations_df, "2026-09-21")
    row = result_df.iloc[0]
    assert row["total_purchase_cost"] == 0.0
    assert row["total_waste_cost"] == 0.0
    assert row["waste_ratio"] == 0.0
    assert row["country"] == "Colombia"
    assert row["currency"] == "COP"


def test_missing_supabase_credentials_fail_clearly(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        _supabase_client()
