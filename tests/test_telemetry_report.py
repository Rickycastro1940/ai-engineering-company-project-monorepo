"""Route + window tests for GET /telemetry/report."""

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
    result = analysis.get_events_per_day(
        df, "2026-10-01T00:00:00Z", "2026-10-03T00:00:00Z"
    )
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
    result = {
        row["event_type"]: row["error_count"]
        for row in analysis.get_error_rate_by_type(
            df, "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z"
        )
    }
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
    result = analysis.get_auth_failure_rate(
        df, "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z"
    )
    assert len(result) == 1
    assert result[0]["date"] == "2026-10-01"
    assert result[0]["user_login_succeeded"] == 3
    assert result[0]["user_login_failed"] == 1
    assert result[0]["failure_rate"] == 0.25


def test_empty_dataframe_returns_empty_lists():
    empty = _df([])
    start, end = "2026-10-01T00:00:00Z", "2026-10-08T00:00:00Z"
    assert analysis.get_events_per_day(empty, start, end) == []
    assert analysis.get_error_rate_by_type(empty, start, end) == []
    assert analysis.get_api_latency_per_day(empty, start, end) == []
    assert analysis.get_auth_failure_rate(empty, start, end) == []


def test_resolve_report_window_defaults_to_last_seven_utc_days():
    from services.telemetry.main import resolve_report_window

    fixed_now = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
    start, end = resolve_report_window(None, None, now=fixed_now)
    assert start == "2026-10-01T12:00:00+00:00"
    assert end == "2026-10-08T12:00:00+00:00"


def test_resolve_report_window_accepts_iso_query_params():
    from services.telemetry.main import resolve_report_window

    start, end = resolve_report_window(
        "2026-09-01T00:00:00Z",
        "2026-09-08T00:00:00Z",
    )
    assert start == "2026-09-01T00:00:00+00:00"
    assert end == "2026-09-08T00:00:00+00:00"


def test_build_report_passes_window_to_every_metric(monkeypatch):
    clear_report_cache()
    calls: list[tuple[str, str, str]] = []

    def fake_load(start: str, end: str) -> pd.DataFrame:
        return _df(
            [
                {
                    "id": "1",
                    "timestamp": "2026-10-01T10:00:00Z",
                    "event_type": "user_login_failed",
                    "value": None,
                    "tags": {},
                }
            ]
        )

    def track(name: str):
        def _fn(df, start_date, end_date):
            calls.append((name, start_date, end_date))
            return [{"ok": name}]

        return _fn

    monkeypatch.setattr(
        "services.telemetry.main.load_telemetry_from_supabase", fake_load
    )
    monkeypatch.setattr("services.telemetry.main.get_events_per_day", track("events"))
    monkeypatch.setattr("services.telemetry.main.get_error_rate_by_type", track("errors"))
    monkeypatch.setattr(
        "services.telemetry.main.get_api_latency_per_day", track("latency")
    )
    monkeypatch.setattr("services.telemetry.main.get_auth_failure_rate", track("auth"))

    start = "2026-10-01T00:00:00+00:00"
    end = "2026-10-08T00:00:00+00:00"
    report = build_telemetry_report(start, end, use_cache=False)
    assert report["period"] == {"from": start, "to": end}
    assert report["metrics"]["events_per_day"] == [{"ok": "events"}]
    assert report["metrics"]["error_rate_by_type"] == [{"ok": "errors"}]
    assert {name for name, _, _ in calls} == {"events", "errors", "latency", "auth"}
    assert all(s == start and e == end for _, s, e in calls)


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
                    "value": None,
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
    seen: dict[str, str] = {}

    def fake_load(start: str, end: str) -> pd.DataFrame:
        seen["start"] = start
        seen["end"] = end
        return _df(
            [
                {
                    "id": "a",
                    "timestamp": datetime(2026, 10, 5, 12, tzinfo=timezone.utc).isoformat(),
                    "event_type": "api_error",
                    "value": None,
                    "tags": {},
                },
                {
                    "id": "b",
                    "timestamp": datetime(2026, 10, 5, 13, tzinfo=timezone.utc).isoformat(),
                    "event_type": "user_login_succeeded",
                    "value": None,
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
            "start_date": "2026-10-01T00:00:00Z",
            "end_date": "2026-10-08T00:00:00Z",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["period"]["from"] == "2026-10-01T00:00:00+00:00"
    assert body["period"]["to"] == "2026-10-08T00:00:00+00:00"
    assert "events_per_day" in body["metrics"]
    assert "error_rate_by_type" in body["metrics"]
    assert seen["start"] == "2026-10-01T00:00:00+00:00"
    assert seen["end"] == "2026-10-08T00:00:00+00:00"
    assert body["metrics"]["events_per_day"][0]["event_count"] == 2
    assert body["metrics"]["error_rate_by_type"][0]["event_type"] == "api_error"


def test_telemetry_report_rejects_invalid_iso(monkeypatch):
    monkeypatch.setattr(
        "services.telemetry.main.load_telemetry_from_supabase",
        lambda start, end: _df([]),
    )
    from fastapi import FastAPI

    from services.telemetry.main import router as telemetry_router

    app = FastAPI()
    app.include_router(telemetry_router)
    client = TestClient(app)
    response = client.get(
        "/telemetry/report",
        params={"start_date": "not-a-date", "end_date": "2026-10-08T00:00:00Z"},
    )
    assert response.status_code == 422
