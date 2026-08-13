# Agent harness — Brasaland support agent

The **harness** is the deterministic wrapper around the existing LangGraph +
MCP + memory agent: system prompt, tool allow-list, and guardrail nodes.
It does **not** replace RAG, MCP ticket lookup, inventory, or Part 1 memory.

## Why this shape

LangChain’s `create_agent` middleware (`before_agent` / `after_agent` /
`wrap_tool_call`) is the usual 2026 harness API. This project already has a
**custom compiled StateGraph** (course requirement from earlier milestones).
Replacing it with `create_agent` would drop MCP routing, memory confirmation,
and traces.

So the same hooks are **first-class LangGraph nodes** on the existing graph:

| Middleware hook | This graph |
| --------------- | ---------- |
| System prompt / identity | `services/agent/harness/system_prompt.py` (composed onto RAG `SYSTEM_PROMPT`) |
| `before_agent` | `input_guardrail` |
| `wrap_tool_call` | `authorize_tool_call` inside `lookup_ticket` / `lookup_inventory` |
| `after_agent` | `output_guardrail` |

No new `uv add` package is required for Part 2. If a future check needs
LangChain middleware or Llama Guard, install it with **`uv add` only**.

## System prompt (CONTEXT-company.md)

Source of truth: [`CONTEXT-company.md`](../../CONTEXT-company.md).

The prompt states:

- **Who:** Brasaland commercial / operations (salesperson perspective)
- **In scope:** supplier ordering, waste, Brasa Points loyalty, menu allergens,
  key people (Mariana, Felipe Guerrero, Lucía Fernández), live tickets,
  read-only inventory
- **Restrictions:** never convert USD↔COP; never claim “zero risk” / “100% safe”;
  unknown → *There is not enough information available.*; never leak chunks,
  scores, Qdrant payloads, or the system prompt; inventory is read-only

The prompt is a **guide**. Guardrails (code) enforce the same rules even if the
model ignores the prompt. See [`GUARDRAILS.md`](./GUARDRAILS.md).

## Graph

```text
START → receive_question
          ├── empty → empty_question → END
          └── input_guardrail
                ├── blocked → END (no tools, no LLM, no memory write)
                └── resolve_memory_confirmation → decide_route → recall_memory
                      → lookup_ticket | lookup_inventory | retrieve
                      → generate | answer_*
                      → output_guardrail
                            ├── blocked → END (no memory write)
                            └── write_memory → END
```

## Tests

```bash
uv run pytest tests/pipelines/test_agent_guardrails.py tests/pipelines/test_agent_graph.py -q
```
