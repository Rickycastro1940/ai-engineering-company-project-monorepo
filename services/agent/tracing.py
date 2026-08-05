"""Queryable run traces for the LangGraph support agent.

Each invoke writes a JSON file under ``data/process/agent-traces/`` keyed by
``trace_id``. Evals and operators can load traces after the run without
re-executing the graph.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE_DIR = REPO_ROOT / "data" / "process" / "agent-traces"


@dataclass
class TraceRecord:
    """One complete agent run — queryable after the fact."""

    trace_id: str
    status: str
    question: str
    answer: str | None
    error: str | None
    steps: list[dict[str, Any]]
    started_at: str
    ended_at: str
    duration_ms: int
    node_order: list[str] = field(default_factory=list)
    retrieved_count: int = 0
    route: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def save_trace(record: TraceRecord, *, trace_dir: Path | None = None) -> Path:
    """Persist a trace as JSON and return the file path."""
    directory = trace_dir or DEFAULT_TRACE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record.trace_id}.json"
    path.write_text(json.dumps(record.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_trace(trace_id: str, *, trace_dir: Path | None = None) -> dict[str, Any]:
    """Load a previously saved trace by id. Raises ``FileNotFoundError`` if missing."""
    directory = trace_dir or DEFAULT_TRACE_DIR
    path = directory / f"{trace_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No trace found for id={trace_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_traces(*, trace_dir: Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent traces (newest first), truncated to ``limit``."""
    directory = trace_dir or DEFAULT_TRACE_DIR
    if not directory.exists():
        return []
    files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    traces: list[dict[str, Any]] = []
    for path in files[:limit]:
        try:
            traces.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return traces
