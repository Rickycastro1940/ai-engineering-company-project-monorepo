"""HTTP shell tests: reporting routes call data/pipelines helpers (no ETL in routes)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def test_weekly_performance_route_delegates_to_pipeline():
    from services.reporting.main import app

    payload = {
        "week_start": "2026-09-21",
        "locations": [
            {
                "location_id": "us-mia-downtown",
                "country": "United States",
                "currency": "USD",
                "total_purchase_cost": 1000,
                "total_waste_cost": 150,
                "waste_ratio": 0.15,
                "stockout_events_count": 1,
                "price_alert_events_count": 1,
            }
        ],
    }
    with patch(
        "services.reporting.main.get_weekly_location_performance",
        return_value=payload,
    ) as mock_get:
        client = TestClient(app)
        response = client.get(
            "/reporting/weekly-location-performance",
            params={"week_start": "2026-09-21"},
        )
    assert response.status_code == 200
    assert response.json()["locations"][0]["location_id"] == "us-mia-downtown"
    mock_get.assert_called_once_with(week_start="2026-09-21")


def test_latest_run_route_delegates_to_pipeline():
    from services.reporting.main import app

    with patch(
        "services.reporting.main.get_latest_pipeline_run",
        return_value={
            "run_id": "abc",
            "status": "Success",
            "window_start": "2026-09-21",
            "window_end": "2026-09-28",
            "records_processed": 4,
        },
    ):
        client = TestClient(app)
        response = client.get("/reporting/pipeline-runs/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Success"
    assert body["records_processed"] == 4


def test_trigger_route_enqueues_celery_without_etl():
    from services.reporting.main import app

    delayed = MagicMock()
    delayed.id = "task-123"
    with patch("services.reporting.main.run_weekly_pipeline.delay", return_value=delayed) as delay:
        client = TestClient(app)
        response = client.post(
            "/reporting/pipeline-runs",
            json={"start_date": "2026-09-21", "end_date": "2026-09-28"},
        )
    assert response.status_code == 202
    assert response.json() == {"task_id": "task-123"}
    delay.assert_called_once_with("2026-09-21", "2026-09-28")
