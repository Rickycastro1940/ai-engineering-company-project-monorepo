# User confirmation and auditable memory log

After the agent proposes a memorable fact in its answer, durable writes wait
for an **explicit** user confirmation. This is not a second agent — the same
LangGraph turn resolves the pending proposal, then resumes normally.

## Rules

1. **Explicit intent classification** — `classify_confirmation_intent` labels the
   next user message as `approve` | `reject` | `edit` | `topic_change` |
   `ambiguous`. Approval is **not** inferred from the substring `"yes"` alone
   (e.g. “yesterday’s waste report?” does not approve).
2. **One pending proposal** — `PendingProposalStore` holds at most one open
   proposal. While it is unresolved, generate/`write_memory` will not open a
   second one.
3. **Default discard** — `topic_change` and `ambiguous` **discard** the pending
   proposal. Approval is never assumed from silence or unclear wording.
4. **Auditable log** — every decision appends a JSONL row with `proposal`,
   `outcome`, `originating_message`, and `timestamp` (plus intent metadata) to
   `data/process/agent-memory/memory_decisions.jsonl`.
5. **Resume conversation** — after resolve, residual questions in the same
   message continue through `decide_route` → tools/RAG as usual.

## Graph

```text
receive_question
    → resolve_memory_confirmation
         ├─ confirmation_done (approve/reject/edit only) → END
         └─ decide_route → recall_memory → … → generate → write_memory
```

`write_memory` may **open** a pending proposal (and ask in the answer) but does
not call `MemoryInterface.write`. Writes happen only inside
`resolve_memory_confirmation` on `approve` / `edit`.

## Intent examples

| User message (with a pending proposal) | Intent | Pending |
| -------------------------------------- | ------ | ------- |
| `yes` / `sure` / `please remember it` | `approve` | write + clear |
| `yes, and what is the waste protocol?` | `approve` + residual | write + clear, then answer residual |
| `no` / `skip` / `don't` | `reject` | discard |
| `actually, remember: emergency orders need Lucía over 500 USD` | `edit` | write edited fact + clear |
| `What is the status of ticket BRS-000002?` | `topic_change` | discard, continue |
| `maybe later?` / unclear | `ambiguous` | discard |

## Complete cycles (documented end-to-end)

At least two full flows are required: one **approved** update that appears in a
later turn, and one **rejected** update that leaves durable memory unchanged.

### Cycle A — approve, then recall in a future interaction

**Fact under proposal:**  
`Emergency orders over 500 USD require Procurement Manager approval.`

| Turn | User | Agent / system | Durable store |
| ---- | ---- | -------------- | ------------- |
| **A1 — ask** | “When do emergency orders need approval?” | RAG `generate` returns grounded answer + closing question: *Would you like me to remember this for later: "Emergency orders over 500 USD require Procurement Manager approval."?* · `write_memory` opens **one** pending proposal · `MemoryInterface.write` is **not** called | unchanged (empty or prior facts only) |
| **A2 — approve** | `yes` | `resolve_memory_confirmation` → intent=`approve` · durable `write` + consolidation · audit outcome=`approved` · short ack · pending cleared | **contains** the 500 USD approval fact |
| **A3 — future ask** | “Remind me of the emergency order approval rule.” | `recall_memory` → `MemoryInterface.read` returns the stored fact into `memory_hits` · generate may use it in-prompt | still contains the fact |

```text
A1  question → … → generate (answer + proposal Q) → write_memory (pending only)
A2  "yes" → resolve_memory_confirmation (approve → SQLite write) → END
A3  later question → resolve (no pending) → recall_memory (hit) → … → answer
```

Audit (A2) includes `proposal`, `outcome=approved`, `originating_message`, `timestamp`.

### Cycle B — reject, memory stays unchanged

**Same proposal text as Cycle A** (opened the same way in B1).

| Turn | User | Agent / system | Durable store |
| ---- | ---- | -------------- | ------------- |
| **B1 — ask** | “When do emergency orders need approval?” | Same as A1: answer + remember question · pending opened · no durable write | unchanged |
| **B2 — reject** | `no` | `resolve_memory_confirmation` → intent=`reject` · pending **discarded** · audit outcome=`rejected` · ack *Okay — I won't remember that.* · **no** `MemoryInterface.write` | **unchanged** (fact never inserted) |
| **B3 — future ask** | “Remind me of the emergency order approval rule.” | `recall_memory` does **not** return that proposed fact from semantic memory (it was never stored) · answer relies on RAG/tools only for that content | still unchanged |

```text
B1  question → … → generate (answer + proposal Q) → write_memory (pending only)
B2  "no"  → resolve_memory_confirmation (reject → clear pending, no write) → END
B3  later question → recall_memory (no hit for rejected fact) → … → answer
```

Audit (B2) includes `proposal`, `outcome=rejected`, `originating_message`, `timestamp`.

These two cycles are covered by
`tests/pipelines/test_agent_memory_confirmation_cycles.py`.

## Implementation

| Module | Role |
| ------ | ---- |
| `memory/intent.py` | Explicit classifier |
| `memory/pending.py` | Single pending slot |
| `memory/audit.py` | Append-only decision log |
| `memory/confirmation.py` | `resolve_memory_confirmation` node |

See also [`MEMORY_SELF_EVAL.md`](./MEMORY_SELF_EVAL.md),
[`MEMORY_CONSOLIDATION.md`](./MEMORY_CONSOLIDATION.md).
