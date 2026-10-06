"""Pandas analysis for the engineering telemetry technical report.

Technical / operational dimensions only (not sales, conversion, or revenue).
Formulas match ``docs/telemetry/telemetry-plan.md`` engineering readers and
``data/pipelines/PIPELINE_DESIGN.md`` Phase 1 current state.
"""

from __future__ import annotations

import pandas as pd


def _parse_timestamps(series: pd.Series) -> pd.Series:
    """Parse Supabase timestamptz strings (with or without fractional seconds)."""
    return pd.to_datetime(series, utc=True, format="ISO8601")


def get_events_per_day(df: pd.DataFrame) -> list[dict]:
    """Traffic: COUNT(id) grouped by UTC date."""
    if df.empty:
        return []

    working = df.copy()
    working["timestamp"] = _parse_timestamps(working["timestamp"])
    working["date"] = working["timestamp"].dt.date.astype(str)
    summary = working.groupby("date").size().reset_index(name="event_count")
    return summary.to_dict(orient="records")


def get_error_rate_by_type(df: pd.DataFrame) -> list[dict]:
    """Failures: COUNT of api_error and user_login_failed, grouped by event_type."""
    if df.empty:
        return []

    working = df.copy()
    working["timestamp"] = _parse_timestamps(working["timestamp"])
    error_df = working[
        working["event_type"].isin(["api_error", "user_login_failed"])
    ].copy()
    if error_df.empty:
        return []

    summary = error_df.groupby("event_type").size().reset_index(name="error_count")
    return summary.to_dict(orient="records")


def get_auth_failure_rate(df: pd.DataFrame) -> list[dict]:
    """Sign-in health: failed / (failed + succeeded) per UTC day, 4 dp."""
    if df.empty:
        return []

    working = df.copy()
    working["timestamp"] = _parse_timestamps(working["timestamp"])
    working["date"] = working["timestamp"].dt.date.astype(str)
    auth_df = working[
        working["event_type"].isin(["user_login_succeeded", "user_login_failed"])
    ].copy()
    if auth_df.empty:
        return []

    grouped = auth_df.groupby(["date", "event_type"]).size().unstack(fill_value=0)
    if "user_login_failed" not in grouped.columns:
        grouped["user_login_failed"] = 0
    if "user_login_succeeded" not in grouped.columns:
        grouped["user_login_succeeded"] = 0

    grouped["total_attempts"] = (
        grouped["user_login_succeeded"] + grouped["user_login_failed"]
    )
    grouped["failure_rate"] = (
        grouped["user_login_failed"] / grouped["total_attempts"]
    ).round(4)
    return grouped.reset_index().to_dict(orient="records")
