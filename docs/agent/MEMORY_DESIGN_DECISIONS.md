# Design decisions — Agent Memory (Part 1)

As part of the challenge, these decisions are resolved in code (and justified
here) without a separate checklist hand-hold. Each answer points at the
implementation that enforces it.

## 1. Memory type selection

**What Brasaland uses**

| Layer | Kind | Implementation |
| ----- | ---- | -------------- |
| Durable ops/commercial facts | **Semantic** (structured documents) | SQLite `MemoryStore` / `MemoryInterface` — kinds from CONTEXT (`supplier_ordering`, `waste`, `loyalty`, `allergen`, `people`) |
| What happened this run | **Episodic** (already present) | Agent traces under `data/process/agent-traces/` |
| In-flight turn | Working / short-term | LangGraph `MemorySaver` checkpoints only |

**Why semantic + episodic traces (not the other options alone)**

- Brasaland needs a **small, exact, policy-gated** set of reusable facts
  (“emergency orders over 500 USD need Lucía’s approval”), not millions of
  similarity hits. SQLite upserts + `kind` filters match that profile without
  a new service dependency.
- Episodic “what the agent did” (MCP ticket lookups, RAG outcomes) already
  lives in traces — reusing them avoids a second transcript store.

**Ruled out as the primary durable store**

| Option | Why not for Brasaland Part 1 |
| ------ | ---------------------------- |
| **Vector / embedding memory alone** | Overkill for low-volume exact ops rules; adds embedding infra; weaker guarantees for identity facts (ticket IDs, USD amounts kept as written). RAG already covers semantic search over the KB. |
| **Knowledge graph** | CONTEXT domains are procedure/policy text + a few named people — not a dense entity–relation graph that would justify graph ETL, traversal APIs, and maintenance cost. |
| **Redis alone** | Fine for sessions/cache, not a durable company-fact store without extra conventions and a running Redis + dependency. |

See also [`MEMORY_BACKEND.md`](./MEMORY_BACKEND.md).

## 2. Privacy and restricted information

**Source of truth:** [`CONTEXT-company.md`](../../CONTEXT-company.md) only —
do **not** invent generic PII/secret rules beyond that file.

**Must never enter durable semantic memory** (enforced in
`services/agent/memory/policy.py`):

| Restriction | CONTEXT basis |
| ----------- | ------------- |
| Currency conversion between USD/COP | “Keep USD $ and COP $ exactly as written — never convert.” |
| Absolute allergen claims (`zero risk`, `100% safe`) | “Never claim …; follow source wording.” |
| The unknown-answer placeholder as a “fact” | “There is not enough information available.” |
| RAG internals (chunks, scores, Qdrant payloads) | Knowledge API returns the answer string only |

**Also out of scope for semantic memory** (not listed as CONTEXT memory topics;
keep in live tools / traces):

- Raw MCP incident-ticket rows
- Raw inventory product rows

Anything outside the five memorable kinds is rejected as
`not_in_context_company_memorable_domains`.

Docs: [`MEMORY_POLICY.md`](./MEMORY_POLICY.md).

## 3. Forgetting and unresponsive proposals

### What the agent forgets (durable store)

**Policy:** capacity- and relevance-based clean-up — **not** calendar TTL on
confirmed facts. Ops rules stay true until corrected or superseded.

After each successful durable write, `consolidate_store`:

1. Near-dedupe (Jaccard ≥ 0.80)
2. Extractive summarize (≥ 3 related facts, Jaccard ≥ 0.50)
3. Prune under `AGENT_MEMORY_MAX_FACTS` (default 40) by access / specificity /
   recency

Docs: [`MEMORY_CONSOLIDATION.md`](./MEMORY_CONSOLIDATION.md).

### Pending proposal when the user never responds

**Silence ≠ consent.** A pending proposal **never auto-writes**.

- Default discard on `topic_change` / `ambiguous` (next message).
- Explicit reject clears without write.
- If the user simply never answers: **`AGENT_MEMORY_PENDING_TTL_SECONDS`**
  (default **86400** = 24h) abandons the pending file with audit outcome
  `discarded_pending_ttl` (`PendingProposalStore.take_expired`, wired in
  `resolve_memory_confirmation` and `write_memory`).

Docs: [`MEMORY_CONFIRMATION.md`](./MEMORY_CONFIRMATION.md).

## 4. Security and poisoning prevention

A malicious user cannot freely inject arbitrary “corrections” into durable
memory. Guards (in order):

1. **Propose-only generate** — the model may open a pending proposal; that step
   never calls `MemoryInterface.write`.
2. **Agent-grounded origin** — pending records are created only via
   `new_pending_from_proposal` with `metadata.opened_by =
   agent_grounded_proposal`. Users cannot invent a pending JSON out of band
   through the graph path.
3. **Explicit confirmation intent** — approve is not inferred from the
   substring `"yes"` inside unrelated questions
   (`classify_confirmation_intent`).
4. **CONTEXT policy re-check on write** — `check_approve_write` /
   `check_edit_write` in `services/agent/memory/poisoning.py` re-run
   `evaluate_memory_candidate` before any durable write.
5. **Edit similarity bound** — edited text must stay related to the
   agent-proposed fact (token Jaccard ≥ **0.45**); unrelated substitutions
   (e.g. swapping in a forbidden “zero risk” claim or an off-topic lie) are
   blocked with audit outcome `blocked_poisoning`.

## 5. Why this does not require a multi-agent architecture

Self-evaluation and memory proposal run **inside the same generate model
call** as the user-facing answer:

- Structured output: `answer` + `memory_proposal`
  (`applicable`, `action` add|change, `fact`, `previous_fact`, `why`)
- Deterministic post-gates in-process: CONTEXT policy, one-pending limit,
  attach “Would you like me to remember…?”, confirmation intent classifier,
  poisoning checks, consolidation

There is **no** second LLM, no “memory agent”, and no debate/critique loop
between agents. Justification: Brasaland Part 1 needs a **policy-bounded
propose → confirm → write** pipeline on the existing LangGraph + MCP agent.
A multi-agent split would add orchestration cost without improving the hard
constraints (CONTEXT allow/deny, explicit user consent, audit), which are
already enforced as code after a single structured generation.

Docs: [`MEMORY_SELF_EVAL.md`](./MEMORY_SELF_EVAL.md),
[`MEMORY_INTERFACE.md`](./MEMORY_INTERFACE.md).

## Code map

| Concern | Primary modules |
| ------- | --------------- |
| Policy (CONTEXT-exact) | `services/agent/memory/policy.py` |
| Structured self-eval | `services/agent/generation.py`, `proposal.py` |
| Pending + TTL | `services/agent/memory/pending.py` |
| Confirmation + audit | `confirmation.py`, `intent.py`, `audit.py` |
| Poisoning guards | `poisoning.py` |
| Consolidation / forget | `consolidate.py` |
| Graph wiring | `services/agent/graph.py`, `memory/nodes.py` |
