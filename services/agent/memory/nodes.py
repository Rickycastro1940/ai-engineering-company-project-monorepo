"""LangGraph nodes that extend the existing agent with recall + write memory."""

from __future__ import annotations

import time
from typing import Any

from services.agent.memory.candidates import extract_memory_candidates
from services.agent.memory.interface import DEFAULT_READ_LIMIT, get_agent_memory
from services.agent.state import AgentState


def _step(
    state: AgentState,
    node_name: str,
    status: str,
    started: float,
    *,
    notes: str | None = None,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "node_name": node_name,
        "sequence": len(state.get("steps") or []) + 1,
        "status": status,
        "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
        "notes": notes,
        "output": output or {},
    }


def recall_memory_node(state: AgentState) -> dict[str, Any]:
    """Explicit ``memory.read`` before tools/RAG (bounded; does not dump the store).

    Does not replace MCP ticket lookup or RAG — only supplements state.
    """
    started = time.perf_counter()
    question = state.get("question") or ""
    memory = get_agent_memory()
    hits = memory.read(question, limit=DEFAULT_READ_LIMIT)
    payload = [h.as_dict() for h in hits]
    return {
        "memory_hits": payload,
        "sources_used": ["memory"] if payload else [],
        "steps": [
            _step(
                state,
                "recall_memory",
                "ok",
                started,
                notes=(
                    f"memory.read hits={len(payload)} "
                    f"limit={DEFAULT_READ_LIMIT} (explicit R/W interface)"
                ),
                output={
                    "source": "memory",
                    "api": "MemoryInterface.read",
                    "hit_count": len(payload),
                    "limit": DEFAULT_READ_LIMIT,
                    "kinds": [h.get("kind") for h in payload],
                    "ids": [h.get("id") for h in payload],
                    "dumped_full_store": False,
                },
            )
        ],
    }


def write_memory_node(state: AgentState) -> dict[str, Any]:
    """Explicit ``memory.write`` after a successful answer path (policy-gated)."""
    started = time.perf_counter()
    memory = get_agent_memory()
    raw_candidates = extract_memory_candidates(state)
    written: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for item in raw_candidates:
        result = memory.write(
            str(item.get("text") or ""),
            kind=item.get("kind"),
            source=str(item.get("source") or "agent"),
            metadata=dict(item.get("metadata") or {}),
        )
        if result.ok and result.record is not None:
            written.append(result.record.as_dict())
        else:
            rejected.append(
                {
                    "text": item.get("text"),
                    "reason": result.decision.reason,
                    "source": item.get("source"),
                }
            )

    return {
        "memory_writes": written,
        "sources_used": ["memory"] if written else [],
        "route": "done",
        "steps": [
            _step(
                state,
                "write_memory",
                "ok",
                started,
                notes=(
                    f"memory.write wrote={len(written)} rejected={len(rejected)} "
                    "(policy from CONTEXT-company.md)"
                ),
                output={
                    "source": "memory",
                    "api": "MemoryInterface.write",
                    "written_count": len(written),
                    "rejected_count": len(rejected),
                    "written_ids": [w.get("id") for w in written],
                    "rejected": rejected[:5],
                },
            )
        ],
    }


def recalled_records_from_state(state: AgentState) -> list[Any]:
    """Rebuild MemoryRecord-like dicts already loaded by ``recall_memory`` (no re-dump)."""
    from services.agent.memory.store import MemoryRecord

    out: list[MemoryRecord] = []
    for hit in state.get("memory_hits") or []:
        if not isinstance(hit, dict):
            continue
        text = str(hit.get("text") or "").strip()
        if not text:
            continue
        out.append(
            MemoryRecord(
                id=str(hit.get("id") or ""),
                kind=str(hit.get("kind") or ""),
                text=text,
                source=str(hit.get("source") or ""),
                created_at=str(hit.get("created_at") or ""),
                updated_at=str(hit.get("updated_at") or ""),
                metadata=dict(hit.get("metadata") or {}),
            )
        )
    return out[:DEFAULT_READ_LIMIT]
