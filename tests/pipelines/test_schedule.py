"""Tests for the Monday cron schedule contract."""
from __future__ import annotations

from datetime import date

from data.pipelines.schedule import (
    CRON_EXPRESSION,
    CRON_TIMEZONE,
    previous_week_window,
    schedule_metadata,
)


def test_cron_expression_is_monday_0900_utc():
    assert CRON_EXPRESSION == "0 9 * * 1"
    assert CRON_TIMEZONE == "UTC"
    meta = schedule_metadata()
    assert meta["cron"] == "0 9 * * 1"
    assert "Monday" in meta["description"]


def test_previous_week_window_on_monday_morning():
    # Monday 2026-07-13 → previous week Mon 2026-07-06 .. Mon 2026-07-13
    window = previous_week_window(date(2026, 7, 13))
    assert window.start_date == "2026-07-06"
    assert window.end_date == "2026-07-13"
    assert window.target_date == "2026-07-06"


def test_previous_week_window_midweek():
    # Wednesday 2026-07-15 → still previous closed week starting 2026-07-06
    window = previous_week_window(date(2026, 7, 15))
    assert window.start_date == "2026-07-06"
    assert window.end_date == "2026-07-13"
    assert window.target_date == window.start_date
