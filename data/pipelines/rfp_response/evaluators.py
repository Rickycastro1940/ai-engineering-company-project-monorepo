"""Part 2 evaluators — readability, relevance, and CONTEXT §5 compliance.

Compliance checks map 1:1 to CONTEXT-company.md §5 via
`compliance_rules.CONTEXT_SECTION_5_RULES`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from data.pipelines.rfp_response.compliance_rules import (
    BRAND_PILLARS,
    CEO_USD_THRESHOLD,
    EVAL_DIMENSIONS,
    FORBIDDEN_COMPETITOR_NAMES,
    MIN_SETUP_BUSINESS_DAYS,
    OFFER_VALIDITY_DAYS,
    OFFER_VALIDITY_PHRASE,
)


@dataclass
class DimensionResult:
    name: str
    passed: bool
    score: float
    notes: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)


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
                "rule_ids": list(d.rule_ids),
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


# Setup/delivery promises under MIN_SETUP_BUSINESS_DAYS (CONTEXT §5)
_SETUP_TOO_SHORT = re.compile(
    r"(?:setup|delivery|deliver|instalaci[oó]n|lead\s*time|timeline)"
    r"[^\n.]{0,40}?"
    r"(?:in|within|under|en|of)?\s*"
    r"([1-9]|10)\s*(?:business\s*)?days?",
    re.I,
)
_MONEY = re.compile(
    r"(?:USD\s*\$|\$)\s*[\d,]+(?:\.\d+)?|\b[\d,]+\s*USD\b|\bCOP\s*\$?\s*[\d,]+",
    re.I,
)
_HAS_USD = re.compile(r"\bUSD\b|\$\s*[\d,]", re.I)
_HAS_COP = re.compile(r"\bCOP\b", re.I)


def evaluate_readability(draft: str) -> DimensionResult:
    """Sales-facing readability (CONTEXT §3: sales-facing readability check).

    Uses ``py-readability-metrics`` (TextStat / Flesch) when available; falls back
    to structural heuristics so the pipeline stays offline-friendly.
    """
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
    if "## " not in text and "# " not in text:
        notes.append("Consider markdown headings for Sales readability.")
        score -= 0.1

    caps = sum(1 for w in words if len(w) > 3 and w.isupper())
    if words and caps / max(len(words), 1) > 0.35:
        failures.append("Excessive ALL-CAPS reduces readability.")
        score -= 0.3

    # Use py-readability-metrics (TextStat / Flesch) when available — advisory for
    # sales-facing copy. Formal RFP sections often score low on Flesch; do not fail
    # solely on the metric. Hard gates remain length / CAPS / structure above.
    try:
        from readability import Readability  # type: ignore

        if len(words) >= 100:
            r = Readability(text)
            flesch_score = float(r.flesch().score)
            notes.append(f"flesch_reading_ease={flesch_score:.1f}")
            if flesch_score < 30:
                notes.append(
                    "Flesch score low for sales-facing copy; prefer shorter sentences."
                )
                score -= 0.05
    except Exception as exc:  # noqa: BLE001 — optional metric path
        notes.append(f"textstat_skipped={type(exc).__name__}")

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
    """Ground the draft in Part 1 handoff (key_aspects + metadata), not the PDF."""
    text = (draft or "").casefold()
    notes: list[str] = []
    failures: list[str] = []
    score = 1.0

    if department_id.casefold() not in text and department_id.replace("_", " ") not in text:
        failures.append(f"Draft does not reference department `{department_id}`.")
        score -= 0.4

    client = str(metadata.get("client_name") or "").strip()
    if client and client.casefold() not in text:
        failures.append("Draft missing client_name from intake metadata.")
        score -= 0.3

    hits = 0
    for aspect in key_aspects or []:
        token = aspect.casefold()[:48].strip()
        if len(token) >= 12 and token[:24] in text:
            hits += 1
    if key_aspects and hits == 0:
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
    """Validate CONTEXT-company.md §5 business constraints on a section draft.

    Each failure is tagged with a ``rule_id`` from CONTEXT_SECTION_5_RULES.
    """
    text = draft or ""
    text_cf = text.casefold()
    notes: list[str] = []
    failures: list[str] = []
    rule_ids: list[str] = []
    score = 1.0
    meta = metadata or {}

    # --- brand_pillars -------------------------------------------------------
    missing_pillars = [p for p in BRAND_PILLARS if p not in text_cf]
    if missing_pillars:
        failures.append(
            "[brand_pillars] Missing brand pillar(s): " + ", ".join(missing_pillars)
        )
        rule_ids.append("brand_pillars")
        score -= 0.25 * len(missing_pillars)
    else:
        notes.append("brand_pillars_ok")

    # --- offer_validity ------------------------------------------------------
    validity_ok = (
        OFFER_VALIDITY_PHRASE.casefold() in text_cf
        or (
            f"{OFFER_VALIDITY_DAYS} days" in text_cf
            and ("issuance" in text_cf or "valid" in text_cf or "validity" in text_cf)
        )
        or "30 days from issuance" in text_cf
    )
    if not validity_ok:
        failures.append(
            f"[offer_validity] Offer validity period ({OFFER_VALIDITY_PHRASE}) not stated."
        )
        rule_ids.append("offer_validity")
        score -= 0.25
    else:
        notes.append("offer_validity_ok")

    # --- min_setup_business_days ---------------------------------------------
    for match in _SETUP_TOO_SHORT.finditer(text):
        days = int(match.group(1))
        if days < MIN_SETUP_BUSINESS_DAYS:
            failures.append(
                f"[min_setup_business_days] Setup/delivery promise of {days} days is "
                f"below {MIN_SETUP_BUSINESS_DAYS} business days."
            )
            rule_ids.append("min_setup_business_days")
            score -= 0.4

    if (
        "business days" in text_cf
        and str(MIN_SETUP_BUSINESS_DAYS) in text_cf
        and "min_setup_business_days" not in rule_ids
    ):
        notes.append("setup_sla_mentioned")

    # --- no_competitors ------------------------------------------------------
    for name in FORBIDDEN_COMPETITOR_NAMES:
        if name in text_cf:
            failures.append(f"[no_competitors] Mentions competitor {name!r} (forbidden).")
            rule_ids.append("no_competitors")
            score -= 0.5

    # --- dual_currency -------------------------------------------------------
    if _MONEY.search(text) or _HAS_USD.search(text) or _HAS_COP.search(text):
        if not (_HAS_USD.search(text) and _HAS_COP.search(text)):
            failures.append(
                "[dual_currency] Monetary figures must be expressed with both "
                "USD $ and COP $ labels."
            )
            rule_ids.append("dual_currency")
            score -= 0.3
        else:
            notes.append("dual_currency_ok")

    # Never invent FX / TRM (supports honest dual-currency labeling)
    if re.search(r"converted at|exchange rate of|usando trm", text_cf):
        failures.append(
            "[dual_currency] Do not invent currency conversion / TRM rates."
        )
        if "dual_currency" not in rule_ids:
            rule_ids.append("dual_currency")
        score -= 0.3

    # --- ceo_threshold (Part 2 flags; Part 3 enforces approval) --------------
    value = meta.get("estimated_contract_value_usd")
    if value is not None:
        try:
            if float(value) > CEO_USD_THRESHOLD:
                notes.append(
                    f"ceo_approval_required_part3 "
                    f"(value_usd={float(value):.0f} > {CEO_USD_THRESHOLD:.0f})"
                )
                rule_ids.append("ceo_threshold")
        except (TypeError, ValueError):
            notes.append("ceo_threshold_value_unparseable")

    score = max(0.0, min(1.0, score))
    passed = not failures and score >= 0.7
    # Deduplicate rule_ids while preserving order
    seen: set[str] = set()
    ordered_rules: list[str] = []
    for rid in rule_ids:
        if rid not in seen:
            seen.add(rid)
            ordered_rules.append(rid)
    return DimensionResult(
        name="compliance",
        passed=passed,
        score=score,
        notes=notes,
        failures=failures,
        rule_ids=ordered_rules,
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
