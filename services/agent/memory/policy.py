"""Memory allow/deny rules — **exactly** as specified in ``CONTEXT-company.md``.

Source of truth: repository root ``CONTEXT-company.md``.
Do not add generic privacy/security rules that are not listed there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

# Path to the company context file this module mirrors.
CONTEXT_COMPANY_PATH: Final[Path] = Path(__file__).resolve().parents[3] / "CONTEXT-company.md"

# ---------------------------------------------------------------------------
# STRICTLY FORBIDDEN to store — from CONTEXT-company.md "RAG constraints"
# ---------------------------------------------------------------------------
# - Currency: Keep USD $ and COP $ exactly as written — never convert.
# - Allergens: Never claim "zero risk" or "100% safe"; follow source wording.
# - Unknown answers: Respond with "There is not enough information available."
# - API response: model-generated string only — never chunks, scores, or
#   Qdrant payloads.

FORBIDDEN_CURRENCY_CONVERSION = "context_forbidden_currency_conversion"
FORBIDDEN_ALLERGEN_ABSOLUTE_SAFETY = "context_forbidden_allergen_absolute_safety"
FORBIDDEN_UNKNOWN_ANSWER = "context_forbidden_unknown_answer"
FORBIDDEN_RAG_INTERNALS = "context_forbidden_rag_chunks_scores_or_qdrant_payloads"

_CURRENCY_CONVERSION = re.compile(
    r"\b(convert(?:ed|ing)?|conversion)\b.{0,40}\b(usd|cop|\$)\b"
    r"|\b(usd|cop)\b.{0,40}\b(to|into)\s+(usd|cop)\b"
    r"|\b(usd|cop)\b.{0,20}(≈|equals?)\s*.{0,10}\b(usd|cop|\$)\b",
    re.IGNORECASE,
)
# CONTEXT literal phrases: "zero risk" or "100% safe"
_ABSOLUTE_ALLERGEN_SAFETY = re.compile(
    r"\bzero\s+risk\b|\b100%\s*safe\b",
    re.IGNORECASE,
)
_UNKNOWN_ANSWER = "there is not enough information available."
# CONTEXT: never chunks, scores, or Qdrant payloads
_RAG_INTERNALS = re.compile(
    r"\b(chunks?|scores?|qdrant(\s+payloads?)?|payloads?)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# MEMORABLE facts — from CONTEXT-company.md KB topics + Key people + Audience
# ---------------------------------------------------------------------------
# Knowledge base source documents (topics column) + Key people section.
# Audience: Commercial and operations teams (salesperson perspective).

ALLOWED_KINDS: Final[frozenset[str]] = frozenset(
    {
        "supplier_ordering",  # Weekly orders, delivery lead times, min protein stock, emergency orders
        "waste",  # Waste categories, daily logging, escalation thresholds, operational targets
        "loyalty",  # Brasa Points tiers, redemption rules, FAQ
        "allergen",  # Dish allergens, customer allergy protocol, gluten-free limitations
        "people",  # Mariana, Felipe Guerrero, Lucía Fernández (+ roles from CONTEXT)
    }
)

# Topic hints tied to CONTEXT table + key people (not generic ticket/inventory).
_KIND_HINTS: Final[dict[str, tuple[str, ...]]] = {
    "supplier_ordering": (
        "weekly order",
        "delivery lead",
        "lead time",
        "protein stock",
        "minimum stock",
        "3 days",
        "emergency order",
        "supplier",
        "procurement",
        "500 usd",
    ),
    "waste": (
        "waste",
        "daily logging",
        "escalation",
        "operational target",
        "spoilage",
    ),
    "loyalty": (
        "brasa points",
        "loyalty",
        "tier",
        "redemption",
    ),
    "allergen": (
        "allergen",
        "allergy",
        "gluten-free",
        "gluten free",
        "dairy",
        "soy",
        "peanut",
        "nut",
        "cross-contamination",
        "cross contamination",
    ),
    "people": (
        "mariana",
        "felipe guerrero",
        "lucía fernández",
        "lucia fernandez",
        "ceo",
        "operations director",
        "procurement manager",
    ),
}

# CONTEXT key people — roles that may be remembered.
CONTEXT_KEY_PEOPLE: Final[tuple[str, ...]] = (
    "Mariana — CEO",
    "Felipe Guerrero — Operations Director (waste escalation)",
    "Lucía Fernández — Procurement Manager (emergency order approval > 500 USD)",
)


@dataclass(frozen=True, slots=True)
class MemoryDecision:
    allowed: bool
    reason: str
    kind: str | None = None


def infer_kind(text: str, *, hinted_kind: str | None = None) -> str | None:
    """Map text to a CONTEXT-company memorable domain, or None if out of scope."""
    # Normalize legacy alias used before CONTEXT-exact kinds.
    if hinted_kind == "procurement":
        hinted_kind = "supplier_ordering"
    if hinted_kind and hinted_kind in ALLOWED_KINDS:
        return hinted_kind
    lowered = text.casefold()
    # Key people names from CONTEXT take priority over overlapping topic hints
    # (e.g. Felipe Guerrero + waste escalation → people).
    _person_names = (
        "mariana",
        "felipe guerrero",
        "lucía fernández",
        "lucia fernandez",
    )
    if any(name in lowered for name in _person_names):
        return "people"
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
    """Return whether a candidate may be persisted under CONTEXT-company.md."""
    cleaned = (text or "").strip()
    if not cleaned:
        return MemoryDecision(False, "empty_text")

    # Unknown-answer placeholder must never be learned as a fact.
    if cleaned.casefold().rstrip(".") == _UNKNOWN_ANSWER.rstrip("."):
        return MemoryDecision(False, FORBIDDEN_UNKNOWN_ANSWER)

    if _CURRENCY_CONVERSION.search(cleaned):
        return MemoryDecision(False, FORBIDDEN_CURRENCY_CONVERSION)

    if _ABSOLUTE_ALLERGEN_SAFETY.search(cleaned):
        return MemoryDecision(False, FORBIDDEN_ALLERGEN_ABSOLUTE_SAFETY)

    # Reject candidates that are or contain RAG internals (chunks/scores/payloads).
    if source in {"rag_internals", "qdrant", "chunks", "scores", "payload"}:
        return MemoryDecision(False, FORBIDDEN_RAG_INTERNALS)
    if _RAG_INTERNALS.search(cleaned) and any(
        marker in cleaned.casefold()
        for marker in ("_score", "qdrant", "chunk_id", "payload", "embedding")
    ):
        return MemoryDecision(False, FORBIDDEN_RAG_INTERNALS)

    resolved = infer_kind(cleaned, hinted_kind=kind)
    if resolved is None or resolved not in ALLOWED_KINDS:
        return MemoryDecision(False, "not_in_context_company_memorable_domains")

    return MemoryDecision(True, "ok", kind=resolved)


def sanitize_record_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip CONTEXT-forbidden RAG internal keys before persistence."""
    banned = {"_score", "score", "vector", "embedding", "payload", "qdrant_id", "chunks"}
    return {k: v for k, v in payload.items() if k not in banned}


def context_company_text() -> str:
    """Load CONTEXT-company.md for tests / documentation checks."""
    return CONTEXT_COMPANY_PATH.read_text(encoding="utf-8")
