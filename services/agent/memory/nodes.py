"""LangGraph nodes that extend the existing agent with recall + write memory."""

from __future__ import annotations

import time
from typing import Any

from services.agent.memory.candidates import extract_memory_candidates
from services.agent.memory.interface import DEFAULT_READ_LIMIT, get_agent_memory
from services.agent.memory.self_evaluate import self_evaluate_worth_remembering
from services.agent.memory.store import MemoryRecord
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


def _records_from_hits(
    hits: list[Any],
    *,
    kind: str | None,
) -> list[MemoryRecord]:
    out: list[MemoryRecord] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        if kind and hit.get("kind") and hit.get("kind") != kind:
            continue
        text = str(hit.get("text") or "").strip()
        if not text:
            continue
        out.append(
            MemoryRecord(
                id=str(hit.get("id") or ""),
                kind=str(hit.get("kind") or kind or ""),
                text=text,
                source=str(hit.get("source") or ""),
                created_at=str(hit.get("created_at") or ""),
                updated_at=str(hit.get("updated_at") or ""),
                metadata=dict(hit.get("metadata") or {}),
            )
        )
    return out


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
    """Self-evaluate then optionally ``memory.write`` after a relevant interaction.

    Does **not** always persist. For each CONTEXT-admitted candidate the
    explicit criterion in ``self_evaluate_worth_remembering`` decides
    ``new`` / ``corrected`` (write) vs ``skip_*`` (no write).
    """
    started = time.perf_counter()
    memory = get_agent_memory()
    raw_candidates = extract_memory_candidates(state)
    written: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []

    if not raw_candidates:
        evaluations.append(
            {
                "remember": False,
                "verdict": "skip_no_candidate",
                "reason": "no_policy_admitted_candidates_after_interaction",
                "text": None,
            }
        )
    else:
        for item in raw_candidates:
            text = str(item.get("text") or "")
            kind = item.get("kind")
            related = list(memory.related_for_self_eval(text, kind=kind))
            seen_ids = {r.id for r in related if r.id}
            for hit_rec in _records_from_hits(state.get("memory_hits") or [], kind=kind):
                if hit_rec.id and hit_rec.id in seen_ids:
                    continue
                related.append(hit_rec)
                if hit_rec.id:
                    seen_ids.add(hit_rec.id)

            decision = self_evaluate_worth_remembering(
                text, kind=kind, existing=related
            )
            evaluations.append(
                {
                    **decision.as_dict(),
                    "text": text,
                    "kind": kind,
                    "source": item.get("source"),
                }
            )

            if not decision.remember:
                rejected.append(
                    {
                        "text": text,
                        "reason": f"self_eval:{decision.verdict}",
                        "detail": decision.reason,
                        "source": item.get("source"),
                    }
                )
                continue

            result = memory.write(
                text,
                kind=kind,
                source=str(item.get("source") or "agent"),
                metadata={
                    **dict(item.get("metadata") or {}),
                    "self_eval_verdict": decision.verdict,
                    "self_eval_reason": decision.reason,
                },
                replace_id=(
                    decision.related_id if decision.verdict == "corrected" else None
                ),
            )
            if result.ok and result.record is not None:
                written.append(result.record.as_dict())
            else:
                rejected.append(
                    {
                        "text": text,
                        "reason": result.decision.reason,
                        "source": item.get("source"),
                    }
                )

    return {
        "memory_writes": written,
        "memory_self_evaluations": evaluations,
        "sources_used": ["memory"] if written else [],
        "route": "done",
        "steps": [
            _step(
                state,
                "write_memory",
                "ok",
                started,
                notes=(
                    f"self_eval then memory.write wrote={len(written)} "
                    f"skipped={len(rejected)} "
                    f"verdicts={[e.get('verdict') for e in evaluations]}"
                ),
                output={
                    "source": "memory",
                    "api": "self_evaluate_worth_remembering+MemoryInterface.write",
                    "always_write": False,
                    "written_count": len(written),
                    "rejected_count": len(rejected),
                    "written_ids": [w.get("id") for w in written],
                    "self_evaluations": evaluations,
                    "rejected": rejected[:5],
                },
            )
        ],
    }


def recalled_records_from_state(state: AgentState) -> list[Any]:
    """Rebuild MemoryRecord-like dicts already loaded by ``recall_memory`` (no re-dump)."""
    return _records_from_hits(state.get("memory_hits") or [], kind=None)[
        :DEFAULT_READ_LIMIT
    ]
