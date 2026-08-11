# Explicit read / write memory interface

The Brasaland support agent uses an **explicit memory API** — not prompt stuffing.

## Interface

```python
class MemoryInterface(Protocol):
    def read(self, query: str, *, limit: int = 5) -> list[MemoryRecord]: ...
    def write(self, text: str, *, kind=None, source="agent", metadata=None) -> MemoryWriteResult: ...
```

Implementation: `services/agent/memory/interface.py` → `AgentMemory`
(wired to SQLite via `MemoryStore`, policy-gated on every `write`).

## Graph usage

| Node | API | Behavior |
| ---- | --- | -------- |
| `recall_memory` | `memory.read(question, limit=5)` | Bounded retrieval into `state["memory_hits"]` (fed into the generate prompt) |
| `generate` | `generate_agent_turn` → `answer` + `memory_proposal` | **One** model call; when applicable, answer ends with a remember/update **question** to the user |
| `write_memory` | records pending proposal only | **Never** calls `MemoryInterface.write` on this step — see [`MEMORY_SELF_EVAL.md`](./MEMORY_SELF_EVAL.md) |

## What we refuse to do

- Append the **entire** semantic store into the model **system prompt**
- Grow `SYSTEM_PROMPT` across turns with conversation history or all memories
- Call `list_records()` / dump SQLite inside generation
- Treat LangGraph `MemorySaver` checkpoints as durable company memory

Working state for a turn lives in `AgentState` (`memory_hits`, tool results).
Durable company memory lives behind `read` / `write` only.
