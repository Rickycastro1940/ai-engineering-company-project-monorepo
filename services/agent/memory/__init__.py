"""Durable semantic memory for the Brasaland LangGraph agent.

Extends the existing MCP + RAG agent — does not replace tools or retrieval.
Backend: SQLite semantic store (+ agent traces for episodic) — see
``docs/agent/MEMORY_BACKEND.md``.

Access is **only** through the explicit ``MemoryInterface`` (``read`` / ``write``).
The agent must not accumulate state by appending the full store to the system prompt.
"""

from services.agent.memory.interface import (
    DEFAULT_READ_LIMIT,
    AgentMemory,
    MemoryInterface,
    MemoryWriteResult,
    get_agent_memory,
)
from services.agent.memory.policy import MemoryDecision, evaluate_memory_candidate
from services.agent.memory.store import MemoryRecord, MemoryStore, get_memory_store

__all__ = [
    "DEFAULT_READ_LIMIT",
    "AgentMemory",
    "MemoryDecision",
    "MemoryInterface",
    "MemoryRecord",
    "MemoryStore",
    "MemoryWriteResult",
    "evaluate_memory_candidate",
    "get_agent_memory",
    "get_memory_store",
]
