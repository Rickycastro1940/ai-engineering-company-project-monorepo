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
| `recall_memory` | `memory.read(question, limit=5)` | Bounded retrieval into `state["memory_hits"]` |
| `write_memory` | `self_evaluate_worth_remembering` then optional `memory.write` | **Not always** — only `new` / `corrected` (see [`MEMORY_SELF_EVAL.md`](./MEMORY_SELF_EVAL.md)) |
| `generate` | uses **already-read** hits only | RAG `generate_answer` stays KB-grounded; memory notes are separate turn notes |

## What we refuse to do

- Append the **entire** semantic store into the model **system prompt**
- Grow `SYSTEM_PROMPT` across turns with conversation history or all memories
- Call `list_records()` / dump SQLite inside generation
- Treat LangGraph `MemorySaver` checkpoints as durable company memory

Working state for a turn lives in `AgentState` (`memory_hits`, tool results).
Durable company memory lives behind `read` / `write` only.
