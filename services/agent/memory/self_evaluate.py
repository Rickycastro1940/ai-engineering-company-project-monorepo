"""Post-interaction self-evaluation: write memory only when worth it.

After each relevant answer path the agent must decide whether a candidate is
**new** or a **correction** — not simply always persist.

Criterion (explicit; applied in order):

1. **Policy gate** — candidate must already pass CONTEXT-company.md allow/deny
   (handled before this module is called).
2. **Duplicate** — same normalized text already stored for that kind → skip.
3. **Redundant** — high token overlap with an existing same-kind fact and no
   conflicting tokens → skip (paraphrase / subset restatement).
4. **Corrected** — meaningful overlap with an existing same-kind fact but the
   candidate introduces conflicting tokens (numbers, names, or key phrases)
   → remember and replace the related record.
5. **New** — no sufficiently related same-kind fact → remember as insert.

If there is no candidate after the interaction, the verdict is skip (nothing
worth evaluating) — never invent a write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final, Iterable, Literal

from services.agent.memory.store import MemoryRecord

SelfEvalVerdict = Literal[
    "new",
    "corrected",
    "skip_duplicate",
    "skip_redundant",
    "skip_no_candidate",
]

# Token Jaccard thresholds (explicit criterion constants).
REDUNDANT_JACCARD: Final[float] = 0.90
CORRECTION_JACCARD: Final[float] = 0.35

_TOKEN_RE = re.compile(r"[a-z0-9áéíóúñü+#.-]+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SelfEvaluation:
    """Result of the post-interaction remember / skip decision."""

    remember: bool
    verdict: SelfEvalVerdict
    reason: str
    related_id: str | None = None
    related_text: str | None = None
    jaccard: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "remember": self.remember,
            "verdict": self.verdict,
            "reason": self.reason,
            "related_id": self.related_id,
            "related_text": self.related_text,
            "jaccard": self.jaccard,
        }


def normalize_memory_text(text: str) -> str:
    # Collapse whitespace and strip trailing sentence punctuation so
    # "…approval." and "…approval" compare as the same fact.
    collapsed = " ".join((text or "").split()).casefold()
    return collapsed.rstrip(" .,;:!?")


def _tokens(text: str) -> set[str]:
    raw = _TOKEN_RE.findall((text or "").casefold())
    cleaned: set[str] = set()
    for t in raw:
        # Strip leading/trailing punctuation noise (e.g. "approval." → "approval")
        tok = t.strip(".-#+")
        if len(tok) > 2:
            cleaned.add(tok)
    return cleaned


def token_jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _conflicting_tokens(candidate: str, existing: str) -> set[str]:
    """Tokens present in only one side — signal a correction vs paraphrase."""
    return _tokens(candidate) ^ _tokens(existing)


def _is_meaningful_correction(candidate: str, existing: str) -> bool:
    """True when overlap is real but the texts disagree on substance."""
    xor = _conflicting_tokens(candidate, existing)
    if not xor:
        return False
    # Numeric / money / id-like disagreements always count as corrections.
    if any(re.fullmatch(r"\d+[a-z%]*", t) or t in {"usd", "cop"} for t in xor):
        return True
    # Named-role / person shifts (enough distinct content tokens).
    if len(xor) >= 2:
        return True
    return False


def self_evaluate_worth_remembering(
    text: str,
    *,
    kind: str | None,
    existing: Iterable[MemoryRecord],
) -> SelfEvaluation:
    """Decide whether ``text`` is new/corrected and worth a memory write.

    This is the explicit criterion — callers must not write when
    ``remember`` is False.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return SelfEvaluation(
            remember=False,
            verdict="skip_no_candidate",
            reason="empty_candidate",
        )

    cand_norm = normalize_memory_text(cleaned)
    same_kind = [
        rec
        for rec in existing
        if kind is None or not rec.kind or rec.kind == kind
    ]

    for rec in same_kind:
        if normalize_memory_text(rec.text) == cand_norm:
            return SelfEvaluation(
                remember=False,
                verdict="skip_duplicate",
                reason="exact_normalized_text_already_stored",
                related_id=rec.id,
                related_text=rec.text,
                jaccard=1.0,
            )

    best: tuple[float, MemoryRecord] | None = None
    for rec in same_kind:
        score = token_jaccard(cleaned, rec.text)
        if best is None or score > best[0]:
            best = (score, rec)

    if best is None:
        return SelfEvaluation(
            remember=True,
            verdict="new",
            reason="no_related_same_kind_memory",
        )

    score, related = best
    if score >= REDUNDANT_JACCARD and not _is_meaningful_correction(cleaned, related.text):
        return SelfEvaluation(
            remember=False,
            verdict="skip_redundant",
            reason=(
                f"jaccard={score:.2f}>={REDUNDANT_JACCARD} with existing "
                "same-kind fact and no conflicting substance"
            ),
            related_id=related.id,
            related_text=related.text,
            jaccard=score,
        )

    if score >= CORRECTION_JACCARD and _is_meaningful_correction(cleaned, related.text):
        return SelfEvaluation(
            remember=True,
            verdict="corrected",
            reason=(
                f"jaccard={score:.2f}>={CORRECTION_JACCARD} with conflicting "
                "tokens vs existing same-kind fact"
            ),
            related_id=related.id,
            related_text=related.text,
            jaccard=score,
        )

    if score >= REDUNDANT_JACCARD:
        # High overlap but also "meaningful" — treat as correction.
        return SelfEvaluation(
            remember=True,
            verdict="corrected",
            reason=f"high_overlap_with_substance_change jaccard={score:.2f}",
            related_id=related.id,
            related_text=related.text,
            jaccard=score,
        )

    return SelfEvaluation(
        remember=True,
        verdict="new",
        reason=(
            "insufficient_overlap_with_existing "
            f"(best_jaccard={score:.2f}<{CORRECTION_JACCARD})"
        ),
        related_id=related.id if score > 0 else None,
        related_text=related.text if score > 0 else None,
        jaccard=score,
    )
