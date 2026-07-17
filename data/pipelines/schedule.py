"""Schedule contract for the Brasaland weekly performance pipeline.

Cron (UTC): ``0 9 * * 1`` — every Monday at 09:00 UTC ("Monday morning").

This module is the single source of truth for the expression. Wire it into:
- GitHub Actions (``.github/workflows/brasaland-weekly-pipeline.yml``)
- Prefect serve / deploy (``scripts/serve_pipeline_schedule.py``)
- Design docs / PR description
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Union

# Monday 09:00 UTC — weekly business performance rollup
CRON_EXPRESSION = "0 9 * * 1"
CRON_TIMEZONE = "UTC"
CRON_DESCRIPTION = "Every Monday at 09:00 UTC (Monday morning)"

SCHEDULE_NAME = "brasaland-weekly-monday-0900-utc"


@dataclass(frozen=True)
class WeekWindow:
    """Inclusive start / exclusive end window for the prior ISO week (Mon–Sun)."""

    start_date: str  # YYYY-MM-DD (Monday)
    end_date: str  # YYYY-MM-DD (following Monday, exclusive upper bound)
    target_date: str  # business key — same as start_date (week_start)


def _as_utc_date(as_of: Optional[Union[date, datetime]] = None) -> date:
    if as_of is None:
        return datetime.now(timezone.utc).date()
    if isinstance(as_of, datetime):
        if as_of.tzinfo is None:
            return as_of.replace(tzinfo=timezone.utc).date()
        return as_of.astimezone(timezone.utc).date()
    return as_of


def previous_week_window(as_of: Optional[Union[date, datetime]] = None) -> WeekWindow:
    """Return the Monday–Sunday week *before* the week containing ``as_of`` (UTC).

    Scheduled Monday-morning runs therefore aggregate the week that just closed.
    """
    today = _as_utc_date(as_of)
    # ISO weekday: Monday=0 … Sunday=6
    this_monday = today - timedelta(days=today.weekday())
    prev_monday = this_monday - timedelta(days=7)
    next_monday = prev_monday + timedelta(days=7)
    start = prev_monday.isoformat()
    end = next_monday.isoformat()
    return WeekWindow(start_date=start, end_date=end, target_date=start)


def schedule_metadata() -> dict:
    """Serializable schedule metadata for docs, APIs, and PR evidence."""
    return {
        "name": SCHEDULE_NAME,
        "cron": CRON_EXPRESSION,
        "timezone": CRON_TIMEZONE,
        "description": CRON_DESCRIPTION,
    }
