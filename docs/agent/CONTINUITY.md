# Continuity — secured agent = prior-sprint Brasaland agent

Part 2 (harness / guardrails) **wraps** the same LangGraph support agent built
in prior sprints. It does **not** introduce a second company agent.

## Same agent (identity)

| Prior sprint | Still on `feature/agent-guardrails` |
| ------------ | ----------------------------------- |
| LangGraph Part 1 | `receive_question` → `decide_route` → `retrieve` → `generate` |
| Tools (MCP + inventory) | `lookup_ticket` → `lookup_ticket_via_mcp`; `lookup_inventory` (read-only) |
| Memory (Part 1 of 2) | `resolve_memory_confirmation`, `recall_memory`, `write_memory` |
| Guardrails (Part 2) | `input_guardrail` / `output_guardrail` **around** the graph above |

Evidence: `REQUIRED_NODES` in `services/agent/graph.py` and
`tests/pipelines/test_agent_continuity_context.py`.

## Tools

| Tool | Transport | CONTEXT role |
| ---- | --------- | ------------ |
| Ticket status | Company-tools **MCP** (`langchain-mcp-adapters`) | Live incidents (agent capability; not a KB doc) |
| Inventory | Read-only HTTP against inventory manager | Live stock (agent capability; not a KB doc) |
| RAG | `data.pipelines.rag.retrieve` → collection `brasaland_kb` | Four CONTEXT KB documents |

Direct HTTP `lookup_ticket` remains deprecated and is **not** wired into the graph.

## Knowledge base (CONTEXT-company.md)

Indexed from `docs/company-knowledge-base/`:

1. `brasaland-supplier-ordering.en.md` — weekly orders, lead times, protein stock, emergency orders
2. `brasaland-waste-protocol.en.md` — waste categories, logging, escalation
3. `brasaland-loyalty-program.en.md` — Brasa Points
4. `brasaland-menu-allergens.en.md` — allergens / gluten-free

Collection: `brasaland_kb`. Company slug: `brasaland`.

## Domain (CONTEXT-company.md)

- Company: **Brasaland** (grilled-food chain, **Colombia** + **Florida**)
- Audience: commercial / operations (**salesperson perspective**)
- Key people: Mariana (CEO); Felipe Guerrero (Ops — waste); Lucía Fernández (Procurement — emergency orders > 500 USD)
- Restrictions: never convert USD↔COP; never “zero risk” / “100% safe”; unknown → *There is not enough information available.*; never leak chunks/scores/Qdrant payloads

The harness system prompt and guardrail reason codes are derived from this
file — a generic prompt is not accepted.

## Eval command

```bash
uv run pytest tests/pipelines/test_agent_continuity_context.py -q
```
