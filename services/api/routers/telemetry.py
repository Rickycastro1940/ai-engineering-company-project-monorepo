"""Temporary telemetry ingest stub for frontend capture verification."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from config import TELEMETRY_ENDPOINT
from telemetry_schemas import TelemetryBatch, TelemetryBatchResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telemetry"])


@router.post("/telemetry/events", response_model=TelemetryBatchResponse)
def ingest_telemetry_events(batch: TelemetryBatch) -> TelemetryBatchResponse:
    """Validate envelope format, log event types, return received count.

    Persistence is intentionally omitted — Phase 3 replaces this stub.
    ``TELEMETRY_ENDPOINT`` is read at import/startup to establish the env pattern.
    """
    _ = TELEMETRY_ENDPOINT  # establish env-driven pattern from day one
    count = len(batch.events)
    event_types = [event.event_type for event in batch.events]
    logger.info(
        "Telemetry stub received %s event(s) via %s: %s",
        count,
        TELEMETRY_ENDPOINT,
        event_types,
    )
    for event_type in event_types:
        logger.info("telemetry event_type=%s", event_type)
    return TelemetryBatchResponse(received=count)
