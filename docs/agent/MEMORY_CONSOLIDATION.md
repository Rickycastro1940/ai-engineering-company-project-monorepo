# Memory consolidation (bounded semantic store)

Durable semantic memory must not grow without control. After each successful
durable write (user-confirmed), ``AgentMemory`` runs **consolidation**:

| Step | Behavior |
| ---- | -------- |
| **Near-deduplicate** | Same `kind`, token Jaccard ≥ **0.80** → keep the richer/newer fact, delete the peer |
| **Summarize clusters** | ≥ **3** same-kind facts with Jaccard ≥ **0.50** → replace with one extractive summary (no second LLM call) |
| **Discard low-relevance** | If count still exceeds **`AGENT_MEMORY_MAX_FACTS`** (default **40**) → drop lowest relevance (access_count + specificity + recency) |

Access counts are bumped on `MemoryInterface.read` / store search so frequently
recalled facts survive pruning.

## API

```python
memory.write(...)           # consolidates by default after a successful write
memory.consolidate()        # explicit run
consolidate_store(store)    # low-level
```

Report fields: `before_count`, `after_count`, `deduplicated_ids`,
`summarized_ids`, `summary_ids`, `discarded_low_relevance_ids`, `actions`.

## Configuration

| Env | Default | Meaning |
| --- | ------- | ------- |
| `AGENT_MEMORY_MAX_FACTS` | `40` | Hard cap after consolidation |
| `AGENT_MEMORY_DEDUP_JACCARD` | `0.80` | Near-duplicate threshold |
| `AGENT_MEMORY_SUMMARY_JACCARD` | `0.50` | Cluster membership for summarization |
| `AGENT_MEMORY_SUMMARY_MIN_CLUSTER` | `3` | Min cluster size to summarize |

Implementation: `services/agent/memory/consolidate.py`.

## Related

- Backend: [`MEMORY_BACKEND.md`](./MEMORY_BACKEND.md)
- Confirmation (when durable writes happen): [`MEMORY_CONFIRMATION.md`](./MEMORY_CONFIRMATION.md)
