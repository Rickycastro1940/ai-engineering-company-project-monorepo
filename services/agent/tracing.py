"""Queryable run traces for the LangGraph support agent.

Every ``run_agent`` invoke writes a structured JSON file under
``data/process/agent-traces/<trace_id>.json``. The file records:

- which nodes ran
- in what order (``node_order`` / ``steps[].sequence``)
- what each node produced (``steps[].output``)

Traces are queryable after the run via ``load_trace`` / ``list_traces`` /
``query_traces``, or HTTP ``GET /agent/traces`` and ``GET /agent/traces/{id}``
— not just printed to the console.
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
    for path in files:
        if path.name.startswith("sample-"):
            continue
        try:
            traces.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
        if len(traces) >= limit:
            break
    return traces


def query_traces(
    *,
    node: str | None = None,
    status: str | None = None,
    question_contains: str | None = None,
    trace_dir: Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Filter persisted traces — proves traces are queryable after the run.

    Examples
    --------
    >>> query_traces(node="retrieve")           # runs where retrieve executed
    >>> query_traces(status="ok")               # successful runs
    >>> query_traces(question_contains="protein")
    """
    matches: list[dict[str, Any]] = []
    for trace in list_traces(trace_dir=trace_dir, limit=max(limit * 5, 50)):
        if status and trace.get("status") != status:
            continue
        if node and node not in (trace.get("node_order") or []):
            continue
        if question_contains and question_contains.casefold() not in (trace.get("question") or "").casefold():
            continue
        matches.append(trace)
        if len(matches) >= limit:
            break
    return matches
