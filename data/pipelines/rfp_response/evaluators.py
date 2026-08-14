"""Part 2 evaluators — readability, relevance, and CONTEXT §5 compliance."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from data.pipelines.rfp_response.compliance_rules import (
    BRAND_PILLARS,
    EVAL_DIMENSIONS,
    FORBIDDEN_COMPETITOR_NAMES,
    MIN_SETUP_BUSINESS_DAYS,
    OFFER_VALIDITY_DAYS,
)


@dataclass
class DimensionResult:
    name: str
    passed: bool
    score: float
    notes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


@dataclass
class EvaluationResult:
    department_id: str
    passed: bool
    readability: DimensionResult
    relevance: DimensionResult
    compliance: DimensionResult
    feedback: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _dim(d: DimensionResult) -> dict[str, Any]:
            return {
                "name": d.name,
                "passed": d.passed,
                "score": d.score,
                "notes": list(d.notes),
                "failures": list(d.failures),
            }

        return {
            "department_id": self.department_id,
            "passed": self.passed,
            "dimensions": {name: _dim(getattr(self, name)) for name in EVAL_DIMENSIONS},
            "readability": _dim(self.readability),
            "relevance": _dim(self.relevance),
            "compliance": _dim(self.compliance),
            "feedback": list(self.feedback),
        }


_SETUP_TOO_SHORT = re.compile(
    r"(?:setup|delivery|deliver|instalaci[oó]n)\s*(?:in|within|under|en)?\s*"
    r"([1-9])\s*(?:business\s*)?days?",
    re.I,
)
_MONEY = re.compile(
    r"(?:USD\s*\$|\$)\s*[\d,]+(?:\.\d+)?|\b[\d,]+\s*USD\b|\bCOP\s*\$?\s*[\d,]+",
    re.I,
)
_HAS_USD = re.compile(r"\bUSD\b|\$\s*[\d,]", re.I)
_HAS_COP = re.compile(r"\bCOP\b", re.I)


def evaluate_readability(draft: str) -> DimensionResult:
    text = draft or ""
    words = re.findall(r"\b\w+\b", text)
    notes: list[str] = []
    failures: list[str] = []
    score = 1.0
    if len(words) < 40:
        failures.append("Draft too short for a proposal section (<40 words).")
        score -= 0.5
    if len(text) > 12_000:
        failures.append("Draft excessively long (>12k chars).")
        score -= 0.3
    # Prefer structured markdown headings
    if "## " not in text and "# " not in text:
        notes.append("Consider markdown headings for Sales readability.")
        score -= 0.1
    # Avoid ALL CAPS walls
    caps = sum(1 for w in words if len(w) > 3 and w.isupper())
    if words and caps / max(len(words), 1) > 0.35:
        failures.append("Excessive ALL-CAPS reduces readability.")
        score -= 0.3
    score = max(0.0, min(1.0, score))
    passed = not failures and score >= 0.6
    if passed:
        notes.append(f"word_count={len(words)}")
    return DimensionResult(
        name="readability", passed=passed, score=score, notes=notes, failures=failures
    )


def evaluate_relevance(
    draft: str,
    *,
    department_id: str,
    key_aspects: list[str],
    metadata: dict[str, Any],
) -> DimensionResult:
    text = (draft or "").casefold()
    notes: list[str] = []
    failures: list[str] = []
    score = 1.0

    if department_id.casefold() not in text and department_id.replace("_", " ") not in text:
        # Owner label / department mention
        failures.append(f"Draft does not reference department `{department_id}`.")
        score -= 0.4

    client = str(metadata.get("client_name") or "").strip()
    if client and client.casefold() not in text:
        failures.append("Draft missing client_name from intake metadata.")
        score -= 0.3

    # At least one key aspect fragment should appear (grounding)
    hits = 0
    for aspect in key_aspects or []:
        token = aspect.casefold()[:48].strip()
        if len(token) >= 12 and token[:24] in text:
            hits += 1
    if key_aspects and hits == 0:
        # Fall back: look for "key aspects" section header as weak pass
        if "key aspects" not in text:
            failures.append("Draft not grounded in Part 1 key_aspects.")
            score -= 0.4
        else:
            notes.append("Key aspects section present; weak token overlap.")
            score -= 0.1
    else:
        notes.append(f"key_aspect_hits={hits}")

    score = max(0.0, min(1.0, score))
    passed = not failures and score >= 0.6
    return DimensionResult(
        name="relevance", passed=passed, score=score, notes=notes, failures=failures
    )


def evaluate_compliance(draft: str, *, metadata: dict[str, Any] | None = None) -> DimensionResult:
    """Validate CONTEXT §5 business constraints on a section draft."""
    text = draft or ""
    text_cf = text.casefold()
    notes: list[str] = []
    failures: list[str] = []
    score = 1.0
    meta = metadata or {}

    # Brand pillars — section should carry them so parallel sections stay independently compliant
    missing_pillars = [p for p in BRAND_PILLARS if p not in text_cf]
    if missing_pillars:
        failures.append(
            "Missing brand pillar(s): " + ", ".join(missing_pillars)
        )
        score -= 0.25 * len(missing_pillars)

    # Offer validity
    if "30 days" not in text_cf and str(OFFER_VALIDITY_DAYS) not in text_cf:
        failures.append("Offer validity period (30 days from issuance) not stated.")
        score -= 0.25
    else:
        notes.append("offer_validity_ok")

    # Setup / delivery shorter than 10 business days
    for match in _SETUP_TOO_SHORT.finditer(text):
        days = int(match.group(1))
        if days < MIN_SETUP_BUSINESS_DAYS:
            failures.append(
                f"Setup/delivery promise of {days} days is below "
                f"{MIN_SETUP_BUSINESS_DAYS} business days."
            )
            score -= 0.4

    # Explicit ≥10 confirmation preferred for operaciones-heavy text
    if "business days" in text_cf and str(MIN_SETUP_BUSINESS_DAYS) in text_cf:
        notes.append("setup_sla_mentioned")

    # Competitor names
    for name in FORBIDDEN_COMPETITOR_NAMES:
        if name in text_cf:
            failures.append(f"Mentions competitor {name!r} (forbidden).")
            score -= 0.5

    # Prices must show both COP and USD when money appears
    if _MONEY.search(text) or _HAS_USD.search(text):
        if not (_HAS_USD.search(text) and _HAS_COP.search(text)):
            failures.append(
                "Monetary figures must be expressed with both USD $ and COP $ labels."
            )
            score -= 0.3
        else:
            notes.append("dual_currency_ok")

    # Never invent FX — flag invented conversion language
    if re.search(r"converted at|exchange rate of|usando trm", text_cf):
        failures.append("Do not invent currency conversion / TRM rates.")
        score -= 0.3

    # CEO flag when value high (informational for Part 3)
    value = meta.get("estimated_contract_value_usd")
    if value is not None and float(value) > 50_000:
        notes.append("ceo_approval_required_part3")

    score = max(0.0, min(1.0, score))
    passed = not failures and score >= 0.7
    return DimensionResult(
        name="compliance", passed=passed, score=score, notes=notes, failures=failures
    )


def evaluate_section(
    *,
    department_id: str,
    draft_content: str,
    key_aspects: list[str],
    metadata: dict[str, Any],
) -> EvaluationResult:
    readability = evaluate_readability(draft_content)
    relevance = evaluate_relevance(
        draft_content,
        department_id=department_id,
        key_aspects=key_aspects,
        metadata=metadata,
    )
    compliance = evaluate_compliance(draft_content, metadata=metadata)
    feedback: list[str] = []
    for dim in (readability, relevance, compliance):
        feedback.extend(dim.failures)
    passed = readability.passed and relevance.passed and compliance.passed
    return EvaluationResult(
        department_id=department_id,
        passed=passed,
        readability=readability,
        relevance=relevance,
        compliance=compliance,
        feedback=feedback,
    )
