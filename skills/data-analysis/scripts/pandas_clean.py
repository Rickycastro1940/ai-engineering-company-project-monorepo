"""Re-export engineering telemetry analysis (single source: services.telemetry)."""

from services.telemetry.analysis import (  # noqa: F401
    get_auth_failure_rate,
    get_error_rate_by_type,
    get_events_per_day,
)
