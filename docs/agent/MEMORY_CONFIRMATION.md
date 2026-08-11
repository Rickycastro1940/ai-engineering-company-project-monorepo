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

## Implementation

| Module | Role |
| ------ | ---- |
| `memory/intent.py` | Explicit classifier |
| `memory/pending.py` | Single pending slot |
| `memory/audit.py` | Append-only decision log |
| `memory/confirmation.py` | `resolve_memory_confirmation` node |

See also [`MEMORY_SELF_EVAL.md`](./MEMORY_SELF_EVAL.md).
