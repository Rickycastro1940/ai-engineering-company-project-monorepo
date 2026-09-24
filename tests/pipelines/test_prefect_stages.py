"""Prefect stage-flow wiring: extract → transform → load + optional eval."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from prefect.states import Completed, Failed


def test_stage_subflows_exist_and_are_callable():
    from data.pipelines import pipeline as mod

    assert hasattr(mod.extract_brasaland_data_flow, "fn")
    assert hasattr(mod.transform_brasaland_kpis_flow, "fn")
    assert hasattr(mod.load_brasaland_reporting_flow, "fn")
    assert hasattr(mod.run_pipeline, "fn")


def test_transform_subflow_returns_kpi_frame():
    from data.pipelines.pipeline import transform_brasaland_kpis_flow

    telemetry = pd.DataFrame(
        [
            {
                "id": "1",
                "event_type": "inbound_order_created",
                "event_payload": {"location_id": "us-mia-downtown", "cost": 100},
            },
            {
                "id": "2",
                "event_type": "stock_waste_registered",
                "event_payload": {"location_id": "us-mia-downtown", "cost": 10},
            },
        ]
    )
    locations = pd.DataFrame(
        [{"id": "us-mia-downtown", "country": "United States", "currency": "USD"}]
    )
    with patch("data.pipelines.pipeline.land_kpi_intermediate") as land:
        land.side_effect = lambda kpis_df, week_start: "raw/path.json"
        # Call underlying function to avoid Prefect engine in unit tests where possible;
        # use .fn for the flow body.
        result = transform_brasaland_kpis_flow.fn(telemetry, locations, "2026-09-21")
    assert not result.empty
    assert result.iloc[0]["total_purchase_cost"] == 100.0
    assert result.iloc[0]["waste_ratio"] == 0.1


def test_optional_eval_failure_does_not_fail_main_etl(monkeypatch):
    """write_eval_snapshot is invoked with return_state=True; ETL still Success."""
    from data.pipelines import pipeline as mod

    telemetry = pd.DataFrame(
        [
            {
                "id": "1",
                "event_type": "inbound_order_created",
                "event_payload": {"location_id": "us-mia-downtown", "cost": 50},
            }
        ]
    )
    locations = pd.DataFrame(
        [{"id": "us-mia-downtown", "country": "United States", "currency": "USD"}]
    )
    kpis = pd.DataFrame(
        [
            {
                "location_id": "us-mia-downtown",
                "week_start": "2026-09-21",
                "total_purchase_cost": 50.0,
                "total_waste_cost": 0.0,
                "waste_ratio": 0.0,
                "stockout_events_count": 0,
                "price_alert_events_count": 0,
                "country": "United States",
                "currency": "USD",
            }
        ]
    )

    monkeypatch.setattr(mod, "_insert_run_start", lambda *a, **k: {"run_id": "r1"})
    finished = {"status": "Success", "records_processed": 1}
    monkeypatch.setattr(mod, "_finish_run", lambda *a, **k: finished)
    monkeypatch.setattr(
        mod,
        "extract_brasaland_data_flow",
        MagicMock(return_value=(telemetry, locations)),
    )
    monkeypatch.setattr(
        mod, "transform_brasaland_kpis_flow", MagicMock(return_value=kpis)
    )
    monkeypatch.setattr(mod, "load_brasaland_reporting_flow", MagicMock(return_value=1))

    def _failing_eval(*args, **kwargs):
        assert kwargs.get("return_state") is True
        return Failed(message="eval boom")

    monkeypatch.setattr(mod, "write_eval_snapshot", _failing_eval)

    result = mod.run_pipeline.fn("2026-09-21", "2026-09-28")
    assert result["status"] == "Success"
    mod.load_brasaland_reporting_flow.assert_called_once()


def test_optional_eval_success_path(monkeypatch):
    from data.pipelines import pipeline as mod

    telemetry = pd.DataFrame([{"id": "1"}])
    locations = pd.DataFrame()
    kpis = pd.DataFrame()

    monkeypatch.setattr(mod, "_insert_run_start", lambda *a, **k: {"run_id": "r2"})
    monkeypatch.setattr(
        mod, "_finish_run", lambda *a, **k: {"status": "Success", "records_processed": 0}
    )
    monkeypatch.setattr(
        mod,
        "extract_brasaland_data_flow",
        MagicMock(return_value=(telemetry, locations)),
    )
    monkeypatch.setattr(
        mod, "transform_brasaland_kpis_flow", MagicMock(return_value=kpis)
    )
    monkeypatch.setattr(mod, "load_brasaland_reporting_flow", MagicMock(return_value=0))

    def _ok_eval(*args, **kwargs):
        assert kwargs.get("return_state") is True
        return Completed(message="ok", data={"passed": True})

    monkeypatch.setattr(mod, "write_eval_snapshot", _ok_eval)
    result = mod.run_pipeline.fn("2026-09-21", "2026-09-28")
    assert result["status"] == "Success"
