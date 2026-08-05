# `services/agent` — Brasaland Support Agent (LangGraph Part 1)

LangGraph migration of the existing Brasaland RAG flow. Retrieval and generation
stay in `data/pipelines/rag.py`; this service only orchestrates them as an
explicit, checkpointed, traceable graph.

## Course checklist — Agent graph (`services/`)

- [x] **State** (`state.py`) — minimal: `question`, `retrieved`, `answer` (+ route/error/steps). No full conversation history.
- [x] **Nodes** (`nodes.py`)
  - `receive_question` — receives/normalizes the question
  - `retrieve` — calls `data.pipelines.rag.retrieve` (reuse, not duplicate)
  - `generate` — calls `generate_answer(question, context)` with already-retrieved chunks
  - `no_context` / `empty_question` — honest / error terminals
  - **Node contract:** never calls monolithic `query()` inside a node
- [x] **Edges** (`graph.py`) — conditional, not a fixed sequence:
  - empty question → `empty_question` → END (skip retrieve)
  - retrieve with no chunks above threshold → `no_context` → END (skip generate)
  - otherwise → `generate` → END
- [x] **Compile before execution** — `compile_agent_graph()` / `get_compiled_graph()` at startup; `validate_graph_structure()` fails clearly on missing nodes
- [x] **Checkpointing** — `MemorySaver` on every compiled graph; inspect via `graph.get_state(thread_id)`

## Graph

```text
START → receive_question ──(empty?)──► empty_question → END
                 │
                 └──(ok)──► retrieve ──(no chunks)──► no_context → END
                                 │
                                 └──(chunks)──► generate → END
```

## API

```bash
# Preferred — standalone agent service
uv run uvicorn services.agent.app:app --reload --port 8000

# Or via the main company API (agent router is mounted there too)
uv run uvicorn api.app:app --reload --port 8000

# Query the agent
curl -s -X POST http://127.0.0.1:8000/agent/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the minimum stock rule for proteins?"}'

# Load a saved trace
curl -s http://127.0.0.1:8000/agent/traces/<trace_id>
```

Traces are also written to `data/process/agent-traces/<trace_id>.json`.

## Evals

```bash
uv run pytest tests/pipelines/test_agent_graph.py -q
```
