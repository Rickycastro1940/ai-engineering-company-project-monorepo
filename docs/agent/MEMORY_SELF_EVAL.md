# Self-evaluation via structured `memory_proposal`

Self-evaluation and memory proposal use **one model call** on the existing
generate step. There is **no** second LLM call, separate memory agent, or
multi-agent architecture — only one extra structured field.

The agent must be able to dismiss **most** interactions as nothing to remember
(`memory_proposal.applicable = false`). A proposal is the exception, not the
default.

When something **is** memorable, the agent proposes it **to the user inside the
same response** (typically a closing question). It **never writes** to durable
memory on this step.

## Single-call output

```json
{
  "answer": "<grounded answer>\n\nWould you like me to remember this for later: \"Locations must keep 3 days of main protein inventory.\"?",
  "memory_proposal": {
    "applicable": true,
    "action": "add",
    "fact": "Locations must keep 3 days of main protein inventory.",
    "previous_fact": null,
    "why": "New durable supplier-ordering fact from grounded KB answer."
  }
}
```

Example closing questions:

- Add: `Would you like me to remember this for later: "<fact>"?`
- Change: `Would you like me to update what I remember from "<previous>" to "<fact>"?`

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
| `answer` | What the user sees — includes the remember/update **question** when applicable |
| `memory_proposal.applicable` | Self-eval gate — do **not** always propose |
| `action` | `add` or `change` when applicable |
| `fact` | What would be added or the corrected wording |
| `previous_fact` | What changes (for `change`) |
| `why` | Why it is new or a correction (or why nothing to remember) |

## Propose to user — never write on this step

```text
generate (1× structured call)
   ├─ state["answer"]            ← user-facing (+ proposal question if applicable)
   └─ state["memory_proposal"]   ← structured self-eval field
         ↓
write_memory (name kept for graph continuity)
   ├─ decide_from_memory_proposal (CONTEXT policy)
   ├─ record pending proposal / skip
   └─ MemoryInterface.write  →  NEVER on this step (wrote_to_memory=false)
```

Durable writes wait for an explicit user confirmation in a later turn (Part 2+).

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
  “always propose.”
- **Expected proposal:** `applicable=false`, `why` ≈ `duplicate_of_existing_memory`.

Implementation: `services/agent/generation.py` → `generate_agent_turn`  
Schema / question helper: `services/agent/memory/proposal.py`  
Canonical dismissals: `NOTHING_TO_REMEMBER_EXAMPLES` in
`services/agent/memory/proposal.py` (kept in sync with this section).

## Related docs

- Confirmation + audit: [`MEMORY_CONFIRMATION.md`](./MEMORY_CONFIRMATION.md)
- Policy: [`MEMORY_POLICY.md`](./MEMORY_POLICY.md)
- R/W API: [`MEMORY_INTERFACE.md`](./MEMORY_INTERFACE.md)
