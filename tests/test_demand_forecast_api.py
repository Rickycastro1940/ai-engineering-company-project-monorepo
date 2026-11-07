"""GET /forecasts/demand on the central API (Bearer JWT)."""
from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.app import app  # noqa: E402

users = importlib.import_module("users")


def _client() -> tuple[TestClient, dict[str, str], tempfile.TemporaryDirectory]:
    temp_dir = tempfile.TemporaryDirectory()
    users.DATABASE_PATH = Path(temp_dir.name) / "company_api.db"
    client = TestClient(app)
    created = client.post(
        "/auth/register",
        json={"email": "forecast@brasaland.test", "password": "secret-password"},
    )
    assert created.status_code == 201, created.text
    token = client.post(
        "/auth/token",
        data={"username": "forecast@brasaland.test", "password": "secret-password"},
    )
    assert token.status_code == 200, token.text
    headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    return client, headers, temp_dir


def test_demand_requires_jwt_and_returns_both_markets() -> None:
    client, headers, temp_dir = _client()
    try:
        anonymous = client.get("/forecasts/demand", params={"date": "2026-11-09"})
        assert anonymous.status_code == 401
        response = client.get("/forecasts/demand", params={"date": "2026-11-09"}, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["company"] == "Brasaland"
        assert body["forecast_date"] == "2026-11-09"
        assert body["history_source"] == "mocked"
        assert body["location_count"] == 14
        assert "local_holiday" in body["features"]
        assert "rain" in body["features"]
        currencies = {row["currency"] for row in body["locations"]}
        assert currencies == {"COP", "USD"}
        assert body["procurement"]["estimated_purchase_cop"] > 0
        assert body["procurement"]["estimated_purchase_usd"] > 0
        medellin = next(row for row in body["locations"] if row["location_id"] == "co-med-centro")
        assert medellin["peak_hour"] == 19
        assert medellin["protein_kg"]["beef_kg"] > 0
        assert medellin["loyalty"]["digital_loyalty"] is False
    finally:
        temp_dir.cleanup()


def test_demand_filters_one_location_and_rejects_unknown() -> None:
    client, headers, temp_dir = _client()
    try:
        response = client.get(
            "/forecasts/demand",
            params={"date": "2026-07-20", "location_id": "co-cartagena"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["location_count"] == 1
        row = body["locations"][0]
        assert row["currency"] == "COP"
        assert row["holiday"] == "Independence Day"
        assert body["procurement"]["estimated_purchase_usd"] == 0

        florida = client.get(
            "/forecasts/demand",
            params={"date": "2026-07-04", "location_id": "us-orlando"},
            headers=headers,
        )
        assert florida.status_code == 200
        assert florida.json()["locations"][0]["holiday"] == "Independence Day"
        assert florida.json()["locations"][0]["currency"] == "USD"

        missing = client.get(
            "/forecasts/demand",
            params={"date": "2026-11-09", "location_id": "not-a-location"},
            headers=headers,
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "not_found"
    finally:
        temp_dir.cleanup()


def test_openapi_lists_the_forecast_route() -> None:
    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/forecasts/demand" in paths
    assert "get" in paths["/forecasts/demand"]
