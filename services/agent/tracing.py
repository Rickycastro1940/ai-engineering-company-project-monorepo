"""In-memory trace store. Query a run after it finishes by ``trace_id``."""
from __future__ import annotations

from typing import Any

_TRACES: dict[str, dict[str, Any]] = {}


def save_trace(record: dict[str, Any]) -> dict[str, Any]:
    trace_id = str(record["trace_id"])
    stored = dict(record)
    _TRACES[trace_id] = stored
    return stored


def get_trace(trace_id: str) -> dict[str, Any] | None:
    found = _TRACES.get(trace_id)
    return dict(found) if found else None


def query_traces(*, node: str | None = None) -> list[dict[str, Any]]:
    """Return stored runs, optionally those whose trace includes ``node``."""
    records = [dict(item) for item in _TRACES.values()]
    if node is None:
        return records
    return [item for item in records if node in (item.get("nodes") or [])]


def clear_traces() -> None:
    _TRACES.clear()
