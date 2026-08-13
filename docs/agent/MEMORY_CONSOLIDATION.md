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

## Expiration / clean-up policy (chosen)

**Policy name:** capacity- and relevance-based clean-up (not calendar TTL).

Brasaland semantic memory is a **small set of durable ops/commercial facts**
(CONTEXT domains: supplier ordering, waste, loyalty, allergens, key people).
Those facts do not expire on a clock the way session caches do — “Lucía
approves emergency orders over 500 USD” stays true until corrected or
superseded. So this agent does **not** apply a time-to-live (e.g. delete after
N days).

Instead, clean-up is:

1. **Continuous hygiene on every durable write** — near-dedupe + extractive
   summarize so paraphrases and overlapping same-kind notes do not pile up.
2. **Hard capacity cap** — at most `AGENT_MEMORY_MAX_FACTS` (default **40**)
   retained facts after consolidation.
3. **Relevance eviction when over cap** — discard the lowest-scoring entries
   first, where score prefers:
   - higher `access_count` (fact was recalled in later turns),
   - higher specificity (somewhat longer, more precise wording),
   - newer `updated_at` (recent corrections beat stale peers).

Episodic “what happened” remains in **agent traces** (separate from semantic
SQLite) and is already file-based / queryable — consolidation does not invent
a second transcript TTL.

### Why this policy (and not TTL)

| Option | Verdict for Brasaland agent memory |
| ------ | ---------------------------------- |
| **Fixed TTL (e.g. 30 days)** | Rejected as primary clean-up. CONTEXT facts are procedural/role truths, not hot cache keys. Expiring them by age would force the agent to re-learn stable rules and fight user-confirmed memory. |
| **Unbounded append-only store** | Rejected. Even low-volume ops memory drifts (near-duplicates, overlapping notes) and would eventually bloat reads/evals. |
| **Capacity + relevance + dedupe/summarize (chosen)** | Matches low-volume structured memory: keep what is still used and specific, collapse redundancy, enforce a clear upper bound without deleting fresh truths solely because time passed. |
| **LLM re-summarize on a schedule** | Not used here. Consolidation is deterministic and runs in-process after writes — no second model call / separate memory agent. |

### Operational defaults

| Knob | Default | Role in the policy |
| ---- | ------- | ------------------ |
| `AGENT_MEMORY_MAX_FACTS` | `40` | Expiration substitute: hard ceiling |
| `AGENT_MEMORY_DEDUP_JACCARD` | `0.80` | Clean-up of near-duplicates |
| `AGENT_MEMORY_SUMMARY_JACCARD` | `0.50` | When related facts may be summarized |
| `AGENT_MEMORY_SUMMARY_MIN_CLUSTER` | `3` | Minimum cluster size before summarizing |

A fact is removed only when it is (a) near-duplicate of a kept peer, (b) folded
into a same-kind summary, or (c) among the lowest-relevance survivors after the
cap is exceeded. User-confirmed writes still go through CONTEXT allow/deny
before any of this runs.

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
