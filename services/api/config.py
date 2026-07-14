"""Environment-driven settings for the company API."""

from __future__ import annotations

import os


TELEMETRY_ENDPOINT = os.getenv(
    "TELEMETRY_ENDPOINT",
    "http://localhost:8000/telemetry/events",
)
