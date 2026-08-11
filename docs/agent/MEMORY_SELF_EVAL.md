# Self-evaluation via structured `memory_proposal`

Self-evaluation and memory proposal use **one model call** on the existing
generate step. There is **no** second LLM call, separate memory agent, or
multi-agent architecture — only one extra structured field.

The agent must be able to dismiss **most** interactions as nothing to remember
(`memory_proposal.applicable = false`). A proposal is the exception, not the
default.

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
    "why": "nothing_to_remember: <short reason>"
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
| `why` | Why it is new or a correction (or why nothing to remember) |

## Examples that must NOT generate a proposal

These interactions are answered normally, but `memory_proposal.applicable`
must stay **false** (nothing durable / in-scope to store):

### 1. Live ticket status lookup

- **User:** “What is the status of ticket BRS-000002?”
- **Why dismiss:** Incident rows are live MCP/tool state, not a CONTEXT
  memorable domain (supplier / waste / loyalty / allergen / key people).
- **Expected proposal:** `applicable=false`,
  `why` ≈ `ticket_path_not_in_context_memorable_domains` (or equivalent).

### 2. Live inventory quantity lookup

- **User:** “How many kg of tomatoes are in stock?”
- **Why dismiss:** Inventory quantities change constantly; raw product rows are
  not listed as memorable topics in `CONTEXT-company.md`.
- **Expected proposal:** `applicable=false`,
  `why` ≈ `inventory_path_not_in_context_memorable_domains`.

### 3. Unknown / no-context answer

- **User:** “What is Brasaland’s secret sauce recipe?”
- **Agent answer:** *There is not enough information available.*
- **Why dismiss:** CONTEXT forbids learning the unknown-answer placeholder (and
  there is no grounded KB fact to store).
- **Expected proposal:** `applicable=false`,
  `why` ≈ `unknown_answer_must_not_be_learned`.

### 4. Duplicate of something already in memory (bonus)

- **User:** repeats a question whose durable fact is already in semantic memory
  (e.g. “3 days of protein stock” already stored).
- **Why dismiss:** Nothing **new** or **corrected** — proposing again would be
  “always write.”
- **Expected proposal:** `applicable=false`, `why` ≈ `duplicate_of_existing_memory`
  (write path also hard-skips exact duplicates if a stale proposal slips through).

Implementation: `services/agent/generation.py` → `generate_agent_turn`  
Schema: `services/agent/memory/proposal.py` → `AgentTurnOutput` / `MemoryProposal`  
Canonical dismissals: `NOTHING_TO_REMEMBER_EXAMPLES` in
`services/agent/memory/proposal.py` (kept in sync with this section).

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

Ticket / inventory / no-context answer paths set `applicable=false` without
calling the model again for memory.

## Related docs

- Policy: [`MEMORY_POLICY.md`](./MEMORY_POLICY.md)
- R/W API: [`MEMORY_INTERFACE.md`](./MEMORY_INTERFACE.md)
