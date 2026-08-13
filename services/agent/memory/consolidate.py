"""Consolidate semantic memory so the store cannot grow without control.

Strategies (deterministic; no second LLM call):

1. **Near-deduplicate** — same ``kind``, high token Jaccard → keep the richer /
   newer fact, delete the redundant peer.
2. **Summarize clusters** — when ≥N near-related same-kind facts remain after
   dedupe, replace the cluster with one extractive summary fact.
3. **Discard low-relevance** — if total count still exceeds ``MAX_SEMANTIC_FACTS``,
   drop the lowest-scoring entries (recency + access_count + specificity).

Runs after durable writes (user-confirmed) via ``AgentMemory.consolidate``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from services.agent.memory.self_evaluate import normalize_memory_text, token_jaccard
from services.agent.memory.store import MemoryRecord, MemoryStore

# Hard cap on durable semantic facts (env-overridable).
MAX_SEMANTIC_FACTS: Final[int] = max(
    5, int(os.getenv("AGENT_MEMORY_MAX_FACTS", "40"))
)
# Near-duplicate threshold (same kind).
DEDUP_JACCARD: Final[float] = float(os.getenv("AGENT_MEMORY_DEDUP_JACCARD", "0.80"))
# Cluster membership for summarization.
SUMMARY_JACCARD: Final[float] = float(os.getenv("AGENT_MEMORY_SUMMARY_JACCARD", "0.50"))
SUMMARY_MIN_CLUSTER: Final[int] = max(
    2, int(os.getenv("AGENT_MEMORY_SUMMARY_MIN_CLUSTER", "3"))
)


@dataclass
class ConsolidationReport:
    before_count: int
    after_count: int
    deduplicated_ids: list[str] = field(default_factory=list)
    summarized_ids: list[str] = field(default_factory=list)
    summary_ids: list[str] = field(default_factory=list)
    discarded_low_relevance_ids: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "before_count": self.before_count,
            "after_count": self.after_count,
            "deduplicated_ids": list(self.deduplicated_ids),
            "summarized_ids": list(self.summarized_ids),
            "summary_ids": list(self.summary_ids),
            "discarded_low_relevance_ids": list(self.discarded_low_relevance_ids),
            "actions": list(self.actions),
            "max_facts": MAX_SEMANTIC_FACTS,
        }


def _access_count(record: MemoryRecord) -> int:
    try:
        return int((record.metadata or {}).get("access_count") or 0)
    except (TypeError, ValueError):
        return 0


def _relevance_score(record: MemoryRecord) -> float:
    """Higher = more worth keeping. Combines recency, access, and specificity."""
    access = _access_count(record)
    # ISO timestamps sort lexicographically when Z-normalized.
    recency = record.updated_at or record.created_at or ""
    # Prefer longer, more specific facts slightly (capped).
    specificity = min(len(record.text.split()), 40) / 40.0
    # Recency as fractional weight via string order proxy — use length of
    # comparable key; callers sort by (score, updated_at).
    return access * 10.0 + specificity + (0.01 if recency else 0.0)


def _prefer_keep(a: MemoryRecord, b: MemoryRecord) -> MemoryRecord:
    """Choose which near-duplicate to retain."""
    sa, sb = _relevance_score(a), _relevance_score(b)
    if sa != sb:
        return a if sa > sb else b
    # Tie-break: longer text, then newer updated_at.
    if len(a.text) != len(b.text):
        return a if len(a.text) > len(b.text) else b
    return a if (a.updated_at or "") >= (b.updated_at or "") else b


def _extractive_summary(records: list[MemoryRecord]) -> str:
    """Merge unique sentences/clauses from a same-kind cluster (no LLM)."""
    seen_norms: set[str] = set()
    parts: list[str] = []
    # Prefer higher-relevance first so summary leads with strongest facts.
    ordered = sorted(records, key=_relevance_score, reverse=True)
    for rec in ordered:
        # Split on sentence-ish boundaries.
        chunks = [
            c.strip()
            for c in rec.text.replace(";", ".").split(".")
            if c.strip()
        ] or [rec.text.strip()]
        for chunk in chunks:
            norm = normalize_memory_text(chunk)
            if not norm or norm in seen_norms:
                continue
            # Skip near-identical fragments already kept.
            if any(token_jaccard(chunk, prev) >= 0.92 for prev in parts):
                continue
            seen_norms.add(norm)
            parts.append(chunk.rstrip(" ."))
            if len(parts) >= 4:
                break
        if len(parts) >= 4:
            break
    if not parts:
        return ordered[0].text
    summary = "; ".join(parts)
    if not summary.endswith("."):
        summary += "."
    return summary


def _cluster_same_kind(
    records: list[MemoryRecord], *, threshold: float
) -> list[list[MemoryRecord]]:
    """Greedy clusters by pairwise Jaccard within one kind."""
    unused = list(records)
    clusters: list[list[MemoryRecord]] = []
    while unused:
        seed = unused.pop(0)
        cluster = [seed]
        rest: list[MemoryRecord] = []
        for other in unused:
            if token_jaccard(seed.text, other.text) >= threshold or any(
                token_jaccard(member.text, other.text) >= threshold for member in cluster
            ):
                cluster.append(other)
            else:
                rest.append(other)
        unused = rest
        clusters.append(cluster)
    return clusters


def consolidate_store(store: MemoryStore) -> ConsolidationReport:
    """Run dedupe → summarize → low-relevance prune on ``store``."""
    records = store.list_records()
    report = ConsolidationReport(before_count=len(records), after_count=len(records))
    if not records:
        return report

    # --- 1) Near-deduplicate within each kind ---
    by_kind: dict[str, list[MemoryRecord]] = {}
    for rec in records:
        by_kind.setdefault(rec.kind, []).append(rec)

    survivors: list[MemoryRecord] = []
    for kind, group in by_kind.items():
        kept: list[MemoryRecord] = []
        removed: set[str] = set()
        for i, left in enumerate(group):
            if left.id in removed:
                continue
            for right in group[i + 1 :]:
                if right.id in removed:
                    continue
                if token_jaccard(left.text, right.text) >= DEDUP_JACCARD:
                    winner = _prefer_keep(left, right)
                    loser = right if winner.id == left.id else left
                    removed.add(loser.id)
                    store.delete(loser.id)
                    report.deduplicated_ids.append(loser.id)
                    report.actions.append(
                        {
                            "action": "deduplicate",
                            "kept_id": winner.id,
                            "removed_id": loser.id,
                            "kind": kind,
                            "jaccard": round(token_jaccard(left.text, right.text), 3),
                        }
                    )
                    if loser.id == left.id:
                        left = winner
            if left.id not in removed:
                kept.append(left)
        survivors.extend(kept)

    # Refresh after deletes.
    survivors = store.list_records()

    # --- 2) Summarize large near-related clusters per kind ---
    by_kind = {}
    for rec in survivors:
        by_kind.setdefault(rec.kind, []).append(rec)

    for kind, group in by_kind.items():
        clusters = _cluster_same_kind(group, threshold=SUMMARY_JACCARD)
        for cluster in clusters:
            if len(cluster) < SUMMARY_MIN_CLUSTER:
                continue
            summary_text = _extractive_summary(cluster)
            # Policy: summary must still look like a durable fact string.
            meta = {
                "consolidated": True,
                "consolidated_from": [c.id for c in cluster],
                "access_count": sum(_access_count(c) for c in cluster),
                "consolidated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
            for old in cluster:
                store.delete(old.id)
                report.summarized_ids.append(old.id)
            summary_rec = store.upsert(
                text=summary_text,
                kind=kind,
                source="consolidation_summary",
                metadata=meta,
            )
            report.summary_ids.append(summary_rec.id)
            report.actions.append(
                {
                    "action": "summarize",
                    "kind": kind,
                    "removed_ids": [c.id for c in cluster],
                    "summary_id": summary_rec.id,
                    "summary_text": summary_text,
                }
            )

    # --- 3) Discard low-relevance when over the hard cap ---
    current = store.list_records()
    if len(current) > MAX_SEMANTIC_FACTS:
        ranked = sorted(
            current,
            key=lambda r: (_relevance_score(r), r.updated_at or "", len(r.text)),
        )
        overflow = len(current) - MAX_SEMANTIC_FACTS
        for victim in ranked[:overflow]:
            store.delete(victim.id)
            report.discarded_low_relevance_ids.append(victim.id)
            report.actions.append(
                {
                    "action": "discard_low_relevance",
                    "removed_id": victim.id,
                    "kind": victim.kind,
                    "relevance_score": round(_relevance_score(victim), 3),
                    "access_count": _access_count(victim),
                }
            )

    report.after_count = len(store.list_records())
    return report
