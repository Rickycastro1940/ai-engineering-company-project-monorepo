"""Unit and route tests for the engineering telemetry technical report."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.telemetry import analysis  # noqa: E402
from services.telemetry.main import (  # noqa: E402
    CACHE_TTL_SECONDS,
    build_telemetry_report,
    clear_report_cache,
)


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_events_per_day_groups_by_utc_date():
    df = _df(
        [
            {"id": "1", "timestamp": "2026-10-01T10:00:00Z", "event_type": "sale_completed"},
            {"id": "2", "timestamp": "2026-10-01T23:00:00Z", "event_type": "api_error"},
            {"id": "3", "timestamp": "2026-10-02T01:00:00Z", "event_type": "user_login_succeeded"},
        ]
    )
    result = analysis.get_events_per_day(df)
    by_date = {row["date"]: row["event_count"] for row in result}
    assert by_date == {"2026-10-01": 2, "2026-10-02": 1}


def test_error_rate_by_type_only_technical_failures():
    df = _df(
        [
            {"id": "1", "timestamp": "2026-10-01T10:00:00Z", "event_type": "api_error"},
            {"id": "2", "timestamp": "2026-10-01T11:00:00Z", "event_type": "user_login_failed"},
            {"id": "3", "timestamp": "2026-10-01T12:00:00Z", "event_type": "user_login_failed"},
            {"id": "4", "timestamp": "2026-10-01T13:00:00Z", "event_type": "client_exception_caught"},
            {"id": "5", "timestamp": "2026-10-01T14:00:00Z", "event_type": "sale_completed"},
        ]
    )
    result = {row["event_type"]: row["error_count"] for row in analysis.get_error_rate_by_type(df)}
    assert result == {
        "user_login_failed": 2,
        "api_error": 1,
        "client_exception_caught": 1,
    }


def test_auth_failure_rate_rounded_to_4dp():
    df = _df(
        [
            {"id": "1", "timestamp": "2026-10-01T10:00:00Z", "event_type": "user_login_succeeded"},
            {"id": "2", "timestamp": "2026-10-01T11:00:00Z", "event_type": "user_login_succeeded"},
            {"id": "3", "timestamp": "2026-10-01T12:00:00Z", "event_type": "user_login_succeeded"},
            {"id": "4", "timestamp": "2026-10-01T13:00:00Z", "event_type": "user_login_failed"},
        ]
    )
    result = analysis.get_auth_failure_rate(df)
    assert len(result) == 1
    assert result[0]["date"] == "2026-10-01"
    assert result[0]["user_login_succeeded"] == 3
    assert result[0]["user_login_failed"] == 1
    assert result[0]["failure_rate"] == 0.25


def test_empty_dataframe_returns_empty_lists():
    empty = _df([])
    assert analysis.get_events_per_day(empty) == []
    assert analysis.get_error_rate_by_type(empty) == []
    assert analysis.get_api_latency_per_day(empty) == []
    assert analysis.get_auth_failure_rate(empty) == []


def test_build_report_uses_cache(monkeypatch):
    clear_report_cache()
    calls = {"n": 0}

    def fake_load(start: str, end: str) -> pd.DataFrame:
        calls["n"] += 1
        return _df(
            [
                {
                    "id": "1",
                    "timestamp": "2026-10-01T10:00:00Z",
                    "event_type": "user_login_failed",
                    "tags": {},
                }
            ]
        )

    monkeypatch.setattr(
        "services.telemetry.main.load_telemetry_from_supabase", fake_load
    )
    first = build_telemetry_report("2026-10-01T00:00:00+00:00", "2026-10-08T00:00:00+00:00")
    second = build_telemetry_report("2026-10-01T00:00:00+00:00", "2026-10-08T00:00:00+00:00")
    assert calls["n"] == 1
    assert first == second
    assert first["metrics"]["error_rate_by_type"][0]["event_type"] == "user_login_failed"
    assert CACHE_TTL_SECONDS == 60


def test_telemetry_report_route(monkeypatch):
    clear_report_cache()

    def fake_load(start: str, end: str) -> pd.DataFrame:
        return _df(
            [
                {
                    "id": "a",
                    "timestamp": datetime(2026, 10, 5, 12, tzinfo=timezone.utc).isoformat(),
                    "event_type": "api_error",
                    "tags": {},
                },
                {
                    "id": "b",
                    "timestamp": datetime(2026, 10, 5, 13, tzinfo=timezone.utc).isoformat(),
                    "event_type": "user_login_succeeded",
                    "tags": {},
                },
            ]
        )

    monkeypatch.setattr(
        "services.telemetry.main.load_telemetry_from_supabase", fake_load
    )

    from fastapi import FastAPI

    from services.telemetry.main import router as telemetry_router

    app = FastAPI()
    app.include_router(telemetry_router)
    client = TestClient(app)
    response = client.get(
        "/telemetry/report",
        params={
            "start_date": "2026-10-01T00:00:00+00:00",
            "end_date": "2026-10-08T00:00:00+00:00",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["period"]["from"] == "2026-10-01T00:00:00+00:00"
    assert body["metrics"]["events_per_day"][0]["event_count"] == 2
    assert body["metrics"]["error_rate_by_type"][0]["event_type"] == "api_error"
