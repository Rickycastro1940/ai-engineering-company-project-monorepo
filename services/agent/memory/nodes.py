"""LangGraph nodes that extend the existing agent with recall + write memory."""

from __future__ import annotations

import time
from typing import Any

from services.agent.memory.candidates import extract_memory_candidates
from services.agent.memory.policy import evaluate_memory_candidate
from services.agent.memory.store import get_memory_store
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
    """Load durable semantic memories relevant to the question (before tools/RAG).

    Does not replace MCP ticket lookup or RAG — only supplements state.
    """
    started = time.perf_counter()
    question = state.get("question") or ""
    store = get_memory_store()
    hits = store.search(question, limit=5)
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
                notes=f"memory hits={len(payload)} (extends MCP+RAG agent)",
                output={
                    "source": "memory",
                    "hit_count": len(payload),
                    "kinds": [h.get("kind") for h in payload],
                    "ids": [h.get("id") for h in payload],
                },
            )
        ],
    }


def write_memory_node(state: AgentState) -> dict[str, Any]:
    """Persist policy-approved facts after a successful answer path.

    Rejects CONTEXT-forbidden content. Keeps MCP/RAG as sources of truth.
    """
    started = time.perf_counter()
    store = get_memory_store()
    raw_candidates = extract_memory_candidates(state)
    written: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    # Re-check policy at write time (defense in depth).
    for item in raw_candidates:
        decision = evaluate_memory_candidate(
            item.get("text") or "",
            kind=item.get("kind"),
            source=item.get("source"),
        )
        if not decision.allowed or not decision.kind:
            rejected.append(
                {
                    "text": item.get("text"),
                    "reason": decision.reason,
                    "source": item.get("source"),
                }
            )
            continue
        record = store.upsert(
            text=str(item["text"]),
            kind=decision.kind,
            source=str(item.get("source") or "agent"),
            metadata=dict(item.get("metadata") or {}),
        )
        written.append(record.as_dict())

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
                    f"wrote={len(written)} rejected={len(rejected)} "
                    "(policy from CONTEXT-company.md)"
                ),
                output={
                    "source": "memory",
                    "written_count": len(written),
                    "rejected_count": len(rejected),
                    "written_ids": [w.get("id") for w in written],
                    "rejected": rejected[:5],
                },
            )
        ],
    }


def memory_context_chunks(state: AgentState) -> list[dict[str, Any]]:
    """Format recalled memories as generation context (no RAG scores/payloads)."""
    chunks: list[dict[str, Any]] = []
    for hit in state.get("memory_hits") or []:
        if not isinstance(hit, dict):
            continue
        text = str(hit.get("text") or "").strip()
        if not text:
            continue
        chunks.append(
            {
                "source_document": "agent_memory",
                "section": str(hit.get("kind") or "semantic"),
                "text": text,
            }
        )
    return chunks
