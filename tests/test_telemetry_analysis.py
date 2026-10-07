"""Phase one — pure pandas metric functions (no loops, deterministic)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.telemetry import analysis  # noqa: E402


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


SAMPLE = _df(
    [
        {"id": "1", "timestamp": "2026-10-06T10:00:00Z", "event_type": "flow_step_recorded", "value": None},
        {"id": "2", "timestamp": "2026-10-06T11:00:00Z", "event_type": "api_latency_recorded", "value": 100},
        {"id": "3", "timestamp": "2026-10-06T12:00:00Z", "event_type": "api_latency_recorded", "value": 200},
        {"id": "4", "timestamp": "2026-10-06T13:00:00Z", "event_type": "api_error", "value": None},
        {"id": "5", "timestamp": "2026-10-06T14:00:00Z", "event_type": "client_exception_caught", "value": None},
        {"id": "6", "timestamp": "2026-10-06T15:00:00Z", "event_type": "user_login_failed", "value": None},
        {"id": "7", "timestamp": "2026-10-06T16:00:00Z", "event_type": "user_login_succeeded", "value": None},
        {"id": "8", "timestamp": "2026-10-07T09:00:00Z", "event_type": "api_latency_recorded", "value": 50},
        {"id": "9", "timestamp": "2026-10-07T10:00:00Z", "event_type": "sale_completed", "value": None},
    ]
)


def test_volume_metric_uses_groupby_count():
    result = analysis.get_events_per_day(SAMPLE)
    by_date = {row["date"]: row["event_count"] for row in result}
    assert by_date == {"2026-10-06": 7, "2026-10-07": 2}


def test_error_metric_uses_captured_technical_types_only():
    result = {
        row["event_type"]: row["error_count"]
        for row in analysis.get_error_count_by_type(SAMPLE)
    }
    assert result == {
        "api_error": 1,
        "client_exception_caught": 1,
        "user_login_failed": 1,
    }
    assert "sale_completed" not in result
    assert "api_latency_recorded" not in result


def test_latency_metric_mean_count_sum_per_day():
    result = {row["date"]: row for row in analysis.get_api_latency_per_day(SAMPLE)}
    assert result["2026-10-06"]["sample_count"] == 2
    assert result["2026-10-06"]["mean_ms"] == 150.0
    assert result["2026-10-06"]["total_ms"] == 300.0
    assert result["2026-10-07"]["sample_count"] == 1
    assert result["2026-10-07"]["mean_ms"] == 50.0


def test_auth_failure_rate_availability():
    result = analysis.get_auth_failure_rate(SAMPLE)
    assert len(result) == 1
    assert result[0]["failure_rate"] == 0.5


def test_metrics_are_deterministic():
    """Calling twice with the same frame must yield the same result."""
    for fn in (
        analysis.get_events_per_day,
        analysis.get_error_count_by_type,
        analysis.get_api_latency_per_day,
        analysis.get_auth_failure_rate,
    ):
        assert fn(SAMPLE.copy()) == fn(SAMPLE.copy())


def test_metrics_do_not_mutate_input():
    original = SAMPLE.copy()
    before = original.copy()
    analysis.get_events_per_day(original)
    analysis.get_error_count_by_type(original)
    analysis.get_api_latency_per_day(original)
    analysis.get_auth_failure_rate(original)
    pd.testing.assert_frame_equal(original, before)


def test_empty_inputs_return_empty_lists():
    empty = _df([])
    assert analysis.get_events_per_day(empty) == []
    assert analysis.get_error_count_by_type(empty) == []
    assert analysis.get_api_latency_per_day(empty) == []
    assert analysis.get_auth_failure_rate(empty) == []
