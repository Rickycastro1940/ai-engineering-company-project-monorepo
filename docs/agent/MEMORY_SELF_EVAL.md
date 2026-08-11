# Post-interaction memory self-evaluation

After each relevant answer path (`generate` / `answer_ticket` /
`answer_inventory` → `write_memory`), the agent **self-evaluates** whether
anything is worth remembering. It does **not** always write.

## Explicit criterion

Applied in order by `self_evaluate_worth_remembering`
(`services/agent/memory/self_evaluate.py`):

| Order | Verdict | Remember? | Rule |
| ----- | ------- | --------- | ---- |
| 0 | *(policy)* | no | CONTEXT-company.md allow/deny must already pass (`extract_memory_candidates`) |
| 1 | `skip_no_candidate` | no | No admitted candidate after this interaction |
| 2 | `skip_duplicate` | no | Same normalized text already stored for that kind |
| 3 | `skip_redundant` | no | Token Jaccard ≥ **0.90** with an existing same-kind fact and no conflicting substance |
| 4 | `corrected` | **yes** | Jaccard ≥ **0.35** with conflicting tokens (numbers, USD/COP, names, key phrases) → replace related id |
| 5 | `new` | **yes** | No sufficiently related same-kind fact |

Constants: `REDUNDANT_JACCARD = 0.90`, `CORRECTION_JACCARD = 0.35`.

## Graph behavior

```text
answer_* / generate → write_memory
                         │
                         ├─ extract CONTEXT-admitted candidates
                         ├─ self_evaluate_worth_remembering(...)
                         ├─ skip_*  → no MemoryInterface.write
                         └─ new | corrected → MemoryInterface.write
                                              (corrected replaces related_id)
```

Trace fields: `state["memory_self_evaluations"]` and the `write_memory` step
output (`always_write: false`, per-candidate verdicts).

## Related docs

- Policy (what may ever be stored): [`MEMORY_POLICY.md`](./MEMORY_POLICY.md)
- R/W API: [`MEMORY_INTERFACE.md`](./MEMORY_INTERFACE.md)
