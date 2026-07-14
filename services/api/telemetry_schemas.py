"""Standard telemetry event envelope (Phase 1 plan / capture contract).

Fields match ``docs/telemetry/telemetry-plan.md`` and the course brief:
``eventId``, ``timestamp``, ``sessionId``, ``userId``, ``event_type``,
``schemaVersion``, ``requestId``, ``properties``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TelemetryEvent(BaseModel):
    """Standard event envelope reused by the stub and Phase 3 persistence."""

    model_config = ConfigDict(extra="forbid")

    eventId: str = Field(..., min_length=1, description="UUID generated at capture time.")
    timestamp: datetime = Field(..., description="ISO 8601 capture time (UTC).")
    sessionId: str = Field(..., min_length=1, description="Browser / API session id.")
    userId: str = Field(..., min_length=1, description="Authenticated operator id.")
    event_type: str = Field(
        ...,
        min_length=1,
        description="entity_action taxonomy, e.g. inbound_order_created.",
    )
    schemaVersion: str = Field(..., min_length=1, description="Envelope schema version.")
    requestId: str = Field(..., min_length=1, description="Frontend–API–log correlation id.")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific payload (allowlist keys only).",
    )


class TelemetryBatch(BaseModel):
    """Batch body accepted by POST /telemetry/events."""

    model_config = ConfigDict(extra="forbid")

    events: list[TelemetryEvent]


class TelemetryBatchResponse(BaseModel):
    received: int
