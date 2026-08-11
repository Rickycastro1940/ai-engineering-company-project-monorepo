"""Explicit read/write memory interface for the Brasaland LangGraph agent.

Durable company memory is accessed only through ``read`` / ``write``.
The agent must **not** accumulate state by appending the full memory store
(or unbounded history) into the model system prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from services.agent.memory.policy import MemoryDecision, evaluate_memory_candidate
from services.agent.memory.store import MemoryRecord, MemoryStore, get_memory_store

# Hard cap on how many facts may enter a single turn's generation context.
DEFAULT_READ_LIMIT = 5


@dataclass(frozen=True, slots=True)
class MemoryWriteResult:
    ok: bool
    record: MemoryRecord | None
    decision: MemoryDecision


@runtime_checkable
class MemoryInterface(Protocol):
    """Minimal explicit memory API (read + write only)."""

    def read(self, query: str, *, limit: int = DEFAULT_READ_LIMIT) -> list[MemoryRecord]:
        """Retrieve a bounded set of relevant facts for this turn."""

    def write(
        self,
        text: str,
        *,
        kind: str | None = None,
        source: str = "agent",
        metadata: dict[str, Any] | None = None,
    ) -> MemoryWriteResult:
        """Persist one fact if policy allows; otherwise reject without storing."""


class AgentMemory:
    """Policy-gated read/write façade over the SQLite semantic store.

    - ``read`` — selective retrieval (never “return everything for the prompt”)
    - ``write`` — single-fact upsert after CONTEXT-company policy checks
    """

    def __init__(self, store: MemoryStore | None = None) -> None:
        self._store = store or get_memory_store()

    def read(self, query: str, *, limit: int = DEFAULT_READ_LIMIT) -> list[MemoryRecord]:
        capped = max(0, min(int(limit), DEFAULT_READ_LIMIT))
        return self._store.search(query, limit=capped)

    def write(
        self,
        text: str,
        *,
        kind: str | None = None,
        source: str = "agent",
        metadata: dict[str, Any] | None = None,
    ) -> MemoryWriteResult:
        decision = evaluate_memory_candidate(text, kind=kind, source=source)
        if not decision.allowed or not decision.kind:
            return MemoryWriteResult(ok=False, record=None, decision=decision)
        record = self._store.upsert(
            text=text,
            kind=decision.kind,
            source=source,
            metadata=metadata,
        )
        return MemoryWriteResult(ok=True, record=record, decision=decision)

    def format_turn_notes(self, records: list[MemoryRecord]) -> str:
        """Format **already-read** facts for this turn (bounded list only).

        Used as a separate user-turn note — never written into the system prompt.
        """
        if not records:
            return ""
        lines = [
            "Retrieved agent memory (via MemoryInterface.read — not system prompt):",
        ]
        for rec in records[:DEFAULT_READ_LIMIT]:
            lines.append(f"- [{rec.kind}] {rec.text}")
        return "\n".join(lines)


_MEMORY: AgentMemory | None = None


def get_agent_memory(*, path: Path | None = None) -> AgentMemory:
    """Process-wide memory interface (injectable store path for tests)."""
    global _MEMORY
    if path is not None:
        return AgentMemory(get_memory_store(path))
    if _MEMORY is None:
        _MEMORY = AgentMemory()
    return _MEMORY
