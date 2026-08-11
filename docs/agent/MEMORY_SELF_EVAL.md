# Self-evaluation via structured `memory_proposal`

Self-evaluation and memory proposal use **one model call** on the existing
generate step. There is **no** second LLM call, separate memory agent, or
multi-agent architecture — only one extra structured field.

## Single-call output

```json
{
  "answer": "<user-facing response only>",
  "memory_proposal": {
    "applicable": true,
    "action": "add",
    "fact": "Locations must keep 3 days of main protein inventory.",
    "previous_fact": null,
    "why": "New durable supplier-ordering fact from grounded KB answer."
  }
}
```

When nothing is worth remembering:

```json
{
  "answer": "...",
  "memory_proposal": {
    "applicable": false,
    "action": null,
    "fact": null,
    "previous_fact": null,
    "why": "Duplicate of existing memory / not a CONTEXT domain / …"
  }
}
```

| Field | Role |
| ----- | ---- |
| `answer` | What the user sees (no proposal JSON inside) |
| `memory_proposal.applicable` | Self-eval gate — do **not** always write |
| `action` | `add` or `change` when applicable |
| `fact` | What would be added or the corrected wording |
| `previous_fact` | What changes (for `change`) |
| `why` | Why it is new or a correction |

Implementation: `services/agent/generation.py` → `generate_agent_turn`  
Schema: `services/agent/memory/proposal.py` → `AgentTurnOutput` / `MemoryProposal`

## After generate → `write_memory`

```text
generate (1× structured call)
   ├─ state["answer"]            ← user-facing
   └─ state["memory_proposal"]   ← self-eval field
         ↓
write_memory
   ├─ decide_from_memory_proposal (CONTEXT policy hard gate)
   ├─ applicable=false / policy deny / duplicate → skip
   └─ add | change → MemoryInterface.write
```

Ticket / inventory answer paths set `applicable=false` (not CONTEXT memorable
domains) without calling the model again.

## Related docs

- Policy: [`MEMORY_POLICY.md`](./MEMORY_POLICY.md)
- R/W API: [`MEMORY_INTERFACE.md`](./MEMORY_INTERFACE.md)
