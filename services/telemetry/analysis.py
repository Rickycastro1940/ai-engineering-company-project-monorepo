"""Phase one — pandas analysis pipeline for engineering telemetry.

Each function answers one technical/operational question from the Brasaland
event catalogue in ``docs/telemetry/telemetry-plan.md``, using rows that were
actually captured in Supabase ``telemetry_events``:

| Function | Dimension | Captured ``event_type`` inputs |
| --- | --- | --- |
| ``get_events_per_day`` | Volume | all rows in the window |
| ``get_error_count_by_type`` | Errors | ``api_error``, ``client_exception_caught``, ``user_login_failed``, ``direct_stock_edit_rejected`` |
| ``get_api_latency_per_day`` | Latency | ``api_latency_recorded`` (``value`` = ms) |
| ``get_auth_failure_rate`` | Availability / auth health | ``user_login_succeeded``, ``user_login_failed`` |

Rules: independent, side-effect free, deterministic. Metrics use only pandas
ops (``.groupby()``, ``.agg()``, ``count``, ``sum``, ``mean``) — no Python
loops over rows. Business metrics (sales, conversion, revenue) are out of scope.
"""

from __future__ import annotations

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


def _parse_timestamps(series: pd.Series) -> pd.Series:
    """Parse Supabase timestamptz strings (with or without fractional seconds)."""
    return pd.to_datetime(series, utc=True, format="ISO8601")


def _with_utc_date(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with parsed ``timestamp`` and string UTC ``date`` columns."""
    working = df.copy()
    working["timestamp"] = _parse_timestamps(working["timestamp"])
    working["date"] = working["timestamp"].dt.date.astype(str)
    return working


def get_events_per_day(df: pd.DataFrame) -> list[dict]:
    """Volume: how many telemetry events hit the platform each UTC day?

    Formula: ``COUNT(id)`` grouped by UTC date.
    """
    if df.empty:
        return []

    working = _with_utc_date(df)
    summary = (
        working.groupby("date", as_index=False)
        .agg(event_count=("id", "count"))
        .sort_values("date")
    )
    return summary.to_dict(orient="records")


def get_error_count_by_type(df: pd.DataFrame) -> list[dict]:
    """Errors: which technical failure types occurred, and how often?

    Formula: ``COUNT(id)`` for catalogue error ``event_type`` values, grouped
    by ``event_type``. Ignores business events (e.g. ``sale_completed``).
    """
    if df.empty:
        return []

    working = df.copy()
    errors = working.loc[working["event_type"].isin(TECHNICAL_ERROR_TYPES)]
    if errors.empty:
        return []

    summary = (
        errors.groupby("event_type", as_index=False)
        .agg(error_count=("id", "count"))
        .sort_values("error_count", ascending=False)
    )
    return summary.to_dict(orient="records")


# Back-compat alias used by the report endpoint / earlier syllabus wording.
def get_error_rate_by_type(df: pd.DataFrame) -> list[dict]:
    """Alias of ``get_error_count_by_type`` (count of errors by type)."""
    return get_error_count_by_type(df)


def get_api_latency_per_day(df: pd.DataFrame) -> list[dict]:
    """Latency: what is the daily staff-API latency profile?

    Uses captured ``api_latency_recorded`` rows where ``value`` is duration ms.
    Formula per UTC date: ``count``, ``mean``, and ``sum`` of ``value``.
    """
    if df.empty or "value" not in df.columns:
        return []

    working = _with_utc_date(df)
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


def get_auth_failure_rate(df: pd.DataFrame) -> list[dict]:
    """Availability / auth health: what share of login attempts fail each day?

    Formula: ``user_login_failed / (user_login_failed + user_login_succeeded)``
    per UTC date, rounded to 4 decimal places.
    """
    if df.empty:
        return []

    working = _with_utc_date(df)
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
