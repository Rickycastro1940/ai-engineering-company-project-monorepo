"""Skill-side pointer — the live router is ``services.telemetry.main``."""

from services.telemetry.main import (  # noqa: F401
    CACHE_TTL_SECONDS,
    REPORT_CACHE,
    TelemetryReportResponse,
    build_telemetry_report,
    get_telemetry_report,
    load_telemetry_from_supabase,
    router,
)
