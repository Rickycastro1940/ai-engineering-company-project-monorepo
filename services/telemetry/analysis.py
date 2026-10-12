"""Phase one — pandas analysis pipeline for engineering telemetry.

Each function answers one technical/operational question from the Brasaland
event catalogue in ``docs/telemetry/telemetry-plan.md``, using rows that were
actually captured in Supabase ``telemetry_events``.

Contract (syllabus report endpoint):
- The FastAPI handler resolves ``start_date`` / ``end_date`` **once**.
- Every metric function receives that same window as required arguments.
- Metric functions do **not** invent their own default time window.

| Function | Dimension | Captured ``event_type`` inputs |
| --- | --- | --- |
| ``get_events_per_day`` | Volume | all rows in the window |
| ``get_error_count_by_type`` | Errors | ``api_error``, ``client_exception_caught``, ``user_login_failed``, … |
| ``get_api_latency_per_day`` | Latency | ``api_latency_recorded`` (``value`` = ms) |
| ``get_auth_failure_rate`` | Availability / auth health | ``user_login_succeeded``, ``user_login_failed`` |

Rules: independent, side-effect free, deterministic. Metrics use only pandas
ops (``.groupby()``, ``.agg()``, ``count``, ``sum``, ``mean``) — no Python
loops over rows. Business metrics (sales, conversion, revenue) are out of scope.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

# Technical / operational error types present (or named) in the catalogue.
TECHNICAL_ERROR_TYPES: tuple[str, ...] = (
    "api_error",
    "api_error_raised",
    "client_exception_caught",
    "user_login_failed",
    "direct_stock_edit_rejected",
    "inventory_validation_failed",
)


def _parse_bound(value: str) -> pd.Timestamp:
    """Parse an ISO 8601 bound to a UTC Timestamp (no defaulting)."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return pd.Timestamp(parsed.astimezone(timezone.utc))


def _frame_in_window(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    """Copy ``df``, parse timestamps, keep rows in ``[start_date, end_date)``."""
    if df.empty:
        return df.copy()

    working = df.copy()
    working["timestamp"] = pd.to_datetime(
        working["timestamp"], utc=True, format="ISO8601"
    )
    start = _parse_bound(start_date)
    end = _parse_bound(end_date)
    in_window = working.loc[
        (working["timestamp"] >= start) & (working["timestamp"] < end)
    ].copy()
    in_window["date"] = in_window["timestamp"].dt.date.astype(str)
    return in_window


def get_events_per_day(
    df: pd.DataFrame, start_date: str, end_date: str
) -> list[dict]:
    """Volume: how many telemetry events hit the platform each UTC day?

    Formula: ``COUNT(id)`` grouped by UTC date inside ``[start_date, end_date)``.
    """
    working = _frame_in_window(df, start_date, end_date)
    if working.empty:
        return []

    summary = (
        working.groupby("date", as_index=False)
        .agg(event_count=("id", "count"))
        .sort_values("date")
    )
    return summary.to_dict(orient="records")


def get_error_count_by_type(
    df: pd.DataFrame, start_date: str, end_date: str
) -> list[dict]:
    """Errors: which technical failure types occurred, and how often?

    Formula: ``COUNT(id)`` for catalogue error ``event_type`` values, grouped
    by ``event_type``, inside ``[start_date, end_date)``.
    """
    working = _frame_in_window(df, start_date, end_date)
    if working.empty:
        return []

    errors = working.loc[working["event_type"].isin(TECHNICAL_ERROR_TYPES)]
    if errors.empty:
        return []

    summary = (
        errors.groupby("event_type", as_index=False)
        .agg(error_count=("id", "count"))
        .sort_values("error_count", ascending=False)
    )
    return summary.to_dict(orient="records")


def get_error_rate_by_type(
    df: pd.DataFrame, start_date: str, end_date: str
) -> list[dict]:
    """Alias of ``get_error_count_by_type`` (syllabus metric name)."""
    return get_error_count_by_type(df, start_date, end_date)


def get_api_latency_per_day(
    df: pd.DataFrame, start_date: str, end_date: str
) -> list[dict]:
    """Latency: daily staff-API latency from ``api_latency_recorded.value`` (ms).

    Formula per UTC date: ``count``, ``mean``, and ``sum`` of ``value``.
    """
    if "value" not in df.columns:
        return []

    working = _frame_in_window(df, start_date, end_date)
    if working.empty:
        return []

    latency = working.loc[
        working["event_type"].eq("api_latency_recorded") & working["value"].notna()
    ].copy()
    if latency.empty:
        return []

    latency["value"] = pd.to_numeric(latency["value"], errors="coerce")
    latency = latency.dropna(subset=["value"])
    if latency.empty:
        return []

    summary = (
        latency.groupby("date", as_index=False)
        .agg(
            sample_count=("value", "count"),
            mean_ms=("value", "mean"),
            total_ms=("value", "sum"),
        )
        .sort_values("date")
    )
    summary["mean_ms"] = summary["mean_ms"].round(2)
    summary["total_ms"] = summary["total_ms"].round(2)
    return summary.to_dict(orient="records")


def get_auth_failure_rate(
    df: pd.DataFrame, start_date: str, end_date: str
) -> list[dict]:
    """Availability: login failure share per UTC day inside the given window.

    Formula: ``user_login_failed / (user_login_failed + user_login_succeeded)``,
    rounded to 4 decimal places.
    """
    working = _frame_in_window(df, start_date, end_date)
    if working.empty:
        return []

    auth = working.loc[
        working["event_type"].isin(["user_login_succeeded", "user_login_failed"])
    ]
    if auth.empty:
        return []

    counts = (
        auth.groupby(["date", "event_type"], as_index=False)
        .agg(attempts=("id", "count"))
        .pivot(index="date", columns="event_type", values="attempts")
        .fillna(0)
    )
    if "user_login_failed" not in counts.columns:
        counts["user_login_failed"] = 0
    if "user_login_succeeded" not in counts.columns:
        counts["user_login_succeeded"] = 0

    counts["total_attempts"] = (
        counts["user_login_succeeded"] + counts["user_login_failed"]
    )
    counts["failure_rate"] = (
        counts["user_login_failed"] / counts["total_attempts"]
    ).round(4)
    return counts.reset_index().sort_values("date").to_dict(orient="records")
