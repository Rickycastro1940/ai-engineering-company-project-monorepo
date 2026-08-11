"""Queryable run traces for the LangGraph support agent.

Every ``run_agent`` invoke writes a structured JSON file under
``data/process/agent-traces/<trace_id>.json``. Each file makes it clear
**whether the RAG, a tool, or both were used, and in what order**:

- ``sources_order`` — ordered list of sources that actually ran
  (``ticket`` / ``inventory`` / ``rag``)
- ``sources_used`` — same list (compatibility alias)
- ``source_summary`` — e.g. ``ticket_only``, ``rag_only``, ``ticket_then_rag``
- ``node_order`` / ``steps[].sequence`` — full node sequence
- ``steps[].output.source`` — per-node source tag when applicable

Traces are queryable after the run via ``load_trace`` / ``list_traces`` /
``query_traces`` (filter by ``node`` or ``source``), or HTTP
``GET /agent/traces`` — not just printed to the console.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE_DIR = REPO_ROOT / "data" / "process" / "agent-traces"

# Nodes that prove a source ran (order in node_order = order sources ran).
_SOURCE_BY_NODE: dict[str, str] = {
    "lookup_ticket": "ticket",
    "lookup_inventory": "inventory",
    "retrieve": "rag",
    # recall_memory / write_memory extend the agent but are not primary answer sources
}


def derive_sources_order(node_order: list[str] | None) -> list[str]:
    """Return ordered unique sources from the nodes that actually executed.

    Example: ``["receive_question", "decide_route", "lookup_ticket", "retrieve",
    "generate"]`` → ``["ticket", "rag"]``.
    """
    order: list[str] = []
    for node in node_order or []:
        source = _SOURCE_BY_NODE.get(node)
        if source and source not in order:
            order.append(source)
    return order


def summarize_sources(sources_order: list[str] | None) -> str:
    """Human-readable summary of which source(s) ran."""
    sources = list(sources_order or [])
    if not sources:
        return "none"
    if len(sources) == 1:
        return f"{sources[0]}_only"
    return "_then_".join(sources)


@dataclass
class TraceRecord:
    """One complete agent run — queryable after the fact.

    ``sources_order`` / ``source_summary`` are the Part 2 acceptance fields that
    show whether RAG, a tool, or both were used and in what order.
    """

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
    sources_used: list[str] = field(default_factory=list)
    sources_order: list[str] = field(default_factory=list)
    source_summary: str = "none"
    needs_ticket: bool = False
    needs_inventory: bool = False
    needs_rag: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def enrich_trace_sources(
    *,
    node_order: list[str],
    sources_used: list[str] | None = None,
) -> dict[str, Any]:
    """Build the source-order fields reviewers look for on every run."""
    # Prefer order derived from nodes that actually ran (authoritative).
    derived = derive_sources_order(node_order)
    ordered = derived or list(sources_used or [])
    return {
        "sources_order": ordered,
        "sources_used": ordered,
        "source_summary": summarize_sources(ordered),
    }


def save_trace(record: TraceRecord, *, trace_dir: Path | None = None) -> Path:
    """Persist a trace as JSON and return the file path."""
    # Guarantee source-order fields even if the caller omitted them.
    enriched = enrich_trace_sources(
        node_order=record.node_order,
        sources_used=record.sources_used,
    )
    record.sources_order = enriched["sources_order"]
    record.sources_used = enriched["sources_used"]
    record.source_summary = enriched["source_summary"]

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
    source: str | None = None,
    status: str | None = None,
    question_contains: str | None = None,
    trace_dir: Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Filter persisted traces — proves traces are queryable after the run.

    Examples
    --------
    >>> query_traces(node="retrieve")
    >>> query_traces(source="ticket")          # runs that used the ticket tool
    >>> query_traces(source="rag")             # runs that used the RAG
    >>> query_traces(status="ok")
    """
    matches: list[dict[str, Any]] = []
    for trace in list_traces(trace_dir=trace_dir, limit=max(limit * 5, 50)):
        if status and trace.get("status") != status:
            continue
        if node and node not in (trace.get("node_order") or []):
            continue
        if source:
            used = trace.get("sources_order") or trace.get("sources_used") or []
            if source not in used:
                continue
        if question_contains and question_contains.casefold() not in (trace.get("question") or "").casefold():
            continue
        matches.append(trace)
        if len(matches) >= limit:
            break
    return matches
