"""Memory allow/deny rules derived from ``CONTEXT-company.md``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# --- Must NEVER enter agent memory (CONTEXT-company.md) -------------------

_CURRENCY_CONVERSION = re.compile(
    r"(convert(?:ed|ing)?|equals?|≈|~)\s*.{0,20}\b(usd|cop|\$)\b"
    r"|\b(usd|cop)\b.{0,20}(to|into|en)\s+(usd|cop|\$)",
    re.IGNORECASE,
)
_ABSOLUTE_ALLERGEN_SAFETY = re.compile(
    r"\b(zero\s+risk|100%\s*safe|completely\s+safe|no\s+cross[- ]contamination\s+risk"
    r"|guaranteed\s+safe|absolutely\s+safe)\b",
    re.IGNORECASE,
)
_SECRETS = re.compile(
    r"\b(api[_-]?key|access[_-]?token|bearer\s+[a-z0-9\-._~+/]+=*|password|secret[_-]?key)\b",
    re.IGNORECASE,
)
_PAYMENT_PII = re.compile(
    r"\b(?:\d[ -]*?){13,19}\b"  # crude PAN-like
    r"|\b(ssn|social\s+security|passport\s+number|cvv|cvc)\b",
    re.IGNORECASE,
)
_RAG_INTERNALS = re.compile(
    r"\b(_score|qdrant|payload|chunk_id|vector\s+id|embedding)\b",
    re.IGNORECASE,
)

_FORBIDDEN_CHECKS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("currency_conversion", _CURRENCY_CONVERSION),
    ("absolute_allergen_safety", _ABSOLUTE_ALLERGEN_SAFETY),
    ("secrets_or_tokens", _SECRETS),
    ("payment_or_gov_id_pii", _PAYMENT_PII),
    ("raw_rag_internals", _RAG_INTERNALS),
)

# --- Worth remembering (commercial / ops domains) -------------------------

ALLOWED_KINDS = frozenset(
    {
        "procurement",
        "waste",
        "loyalty",
        "allergen",
        "people",
        "ticket",
        "inventory",
    }
)

_KIND_HINTS: dict[str, tuple[str, ...]] = {
    "procurement": (
        "protein",
        "stock",
        "supplier",
        "emergency order",
        "lucía",
        "lucia",
        "procurement",
        "500 usd",
        "3 days",
    ),
    "waste": ("waste", "felipe", "escalation", "spoilage"),
    "loyalty": ("brasa points", "loyalty", "tier", "redemption"),
    "allergen": ("allergen", "gluten", "dairy", "soy", "peanut", "nut", "allergy"),
    "people": ("mariana", "felipe guerrero", "lucía fernández", "lucia fernandez", "ceo"),
    "ticket": ("brs-", "incident", "status=", "abierto", "cerrado", "descartado"),
    "inventory": ("product_id", "quantity", "inventory", "tomatoes", "mozzarella"),
}


@dataclass(frozen=True, slots=True)
class MemoryDecision:
    allowed: bool
    reason: str
    kind: str | None = None


def infer_kind(text: str, *, hinted_kind: str | None = None) -> str | None:
    if hinted_kind and hinted_kind in ALLOWED_KINDS:
        return hinted_kind
    lowered = text.casefold()
    for kind, hints in _KIND_HINTS.items():
        if any(h in lowered for h in hints):
            return kind
    return None


def evaluate_memory_candidate(
    text: str,
    *,
    kind: str | None = None,
    source: str | None = None,
) -> MemoryDecision:
    """Return whether a candidate fact may be persisted."""
    cleaned = (text or "").strip()
    if not cleaned:
        return MemoryDecision(False, "empty_text")

    if cleaned.casefold() == "there is not enough information available.":
        return MemoryDecision(False, "unknown_answer_must_not_be_learned")

    for code, pattern in _FORBIDDEN_CHECKS:
        if pattern.search(cleaned):
            return MemoryDecision(False, code)

    resolved = infer_kind(cleaned, hinted_kind=kind)
    if resolved is None:
        return MemoryDecision(False, "not_in_worth_remembering_domains")
    if resolved not in ALLOWED_KINDS:
        return MemoryDecision(False, "kind_not_allowed")

    # Allergen facts are allowed only without absolute-safety language (already checked).
    if source in {"rag_internals", "qdrant", "chunks"}:
        return MemoryDecision(False, "raw_rag_source_forbidden")

    return MemoryDecision(True, "ok", kind=resolved)


def sanitize_record_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop keys that look like RAG internals before persistence."""
    banned = {"_score", "score", "vector", "embedding", "payload", "qdrant_id"}
    return {k: v for k, v in payload.items() if k not in banned}
