"""Part 2 evaluator agents — readability, relevance, and CONTEXT §5 compliance.

Three agents run **in parallel** over each generated section (ThreadPoolExecutor).
Compliance checks map 1:1 to CONTEXT-company.md §5 via
`compliance_rules.CONTEXT_SECTION_5_RULES`.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Final

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
    evaluator_agent: str = ""


@dataclass
class EvaluationResult:
    """Structured per-section evaluation (CONTEXT §2.3 ``evaluation_results``).

    Shape is equivalent to DepartmentSection.evaluation_results:
    readability + relevance + compliance scores, pass flags, and feedback.
    """

    department_id: str
    passed: bool
    readability: DimensionResult
    relevance: DimensionResult
    compliance: DimensionResult
    feedback: list[str] = field(default_factory=list)
    feedback_for_generator: list[str] = field(default_factory=list)
    parallel: bool = True
    evaluator_agents: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _dim(d: DimensionResult) -> dict[str, Any]:
            return {
                "name": d.name,
                "passed": d.passed,
                "score": d.score,
                "notes": list(d.notes),
                "failures": list(d.failures),
                "rule_ids": list(d.rule_ids),
                "evaluator_agent": d.evaluator_agent,
            }

        scores = {
            "readability": self.readability.score,
            "relevance": self.relevance.score,
            "compliance": self.compliance.score,
        }
        return {
            "department_id": self.department_id,
            "passed": self.passed,
            "scores": scores,
            "dimensions": {name: _dim(getattr(self, name)) for name in EVAL_DIMENSIONS},
            "readability": _dim(self.readability),
            "relevance": _dim(self.relevance),
            "compliance": _dim(self.compliance),
            "feedback": list(self.feedback),
            "feedback_for_generator": list(self.feedback_for_generator or self.feedback),
            "parallel": self.parallel,
            "evaluator_agents": list(self.evaluator_agents),
        }


@dataclass(frozen=True)
class EvaluatorContext:
    department_id: str
    draft_content: str
    key_aspects: list[str]
    metadata: dict[str, Any]


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

    # Required library path: py-readability-metrics (``readability.Readability``).
    # Formal proposal copy often scores low on Flesch; do not fail solely on it.
    notes.append("library=py-readability-metrics")
    try:
        from readability import Readability  # type: ignore

        r = Readability(text)
        try:
            flesch = r.flesch()
            flesch_score = float(flesch.score)
            notes.append(f"flesch_reading_ease={flesch_score:.1f}")
            if flesch_score < 30:
                notes.append(
                    "Flesch score low for sales-facing copy; prefer shorter sentences."
                )
                score -= 0.05
        except Exception as exc:  # noqa: BLE001 — library needs enough sentences
            notes.append(f"flesch_skipped={type(exc).__name__}")
        try:
            fog = r.gunning_fog()
            notes.append(f"gunning_fog={float(fog.score):.1f}")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"gunning_fog_skipped={type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"py-readability-metrics_skipped={type(exc).__name__}")

    score = max(0.0, min(1.0, score))
    passed = not failures and score >= 0.6
    if passed:
        notes.append(f"word_count={len(words)}")
    return DimensionResult(
        name="readability",
        passed=passed,
        score=score,
        notes=notes,
        failures=failures,
        evaluator_agent="readability_evaluator_agent",
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

    # Does this section answer what the RFP asked (location / service type)?
    location = str(metadata.get("location") or "").strip()
    if location and location.casefold() not in text:
        notes.append("RFP location not restated in this section.")
        score -= 0.05
    service = str(metadata.get("service_type") or metadata.get("scope") or "").strip()
    if service and service.casefold() not in text:
        notes.append("RFP service_type/scope weakly covered.")
        score -= 0.05

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
        name="relevance",
        passed=passed,
        score=score,
        notes=notes,
        failures=failures,
        evaluator_agent="relevance_evaluator_agent",
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
        evaluator_agent="compliance_evaluator_agent",
    )


class EvaluatorAgent(ABC):
    """One evaluator agent for one dimension of a generated section."""

    agent_name: str
    dimension: str

    @abstractmethod
    def evaluate(self, ctx: EvaluatorContext) -> DimensionResult:
        raise NotImplementedError


class ReadabilityEvaluatorAgent(EvaluatorAgent):
    """Sales-facing readability via py-readability-metrics + structure checks."""

    agent_name = "readability_evaluator_agent"
    dimension = "readability"

    def evaluate(self, ctx: EvaluatorContext) -> DimensionResult:
        return evaluate_readability(ctx.draft_content)


class RelevanceEvaluatorAgent(EvaluatorAgent):
    """Does the section answer what the RFP asked (Part 1 key_aspects + metadata)?"""

    agent_name = "relevance_evaluator_agent"
    dimension = "relevance"

    def evaluate(self, ctx: EvaluatorContext) -> DimensionResult:
        return evaluate_relevance(
            ctx.draft_content,
            department_id=ctx.department_id,
            key_aspects=list(ctx.key_aspects),
            metadata=dict(ctx.metadata),
        )


class ComplianceEvaluatorAgent(EvaluatorAgent):
    """CONTEXT-company.md §5 business constraints."""

    agent_name = "compliance_evaluator_agent"
    dimension = "compliance"

    def evaluate(self, ctx: EvaluatorContext) -> DimensionResult:
        return evaluate_compliance(ctx.draft_content, metadata=dict(ctx.metadata))


EVALUATOR_AGENTS: Final[tuple[EvaluatorAgent, ...]] = (
    ReadabilityEvaluatorAgent(),
    RelevanceEvaluatorAgent(),
    ComplianceEvaluatorAgent(),
)


def run_evaluators_parallel(ctx: EvaluatorContext) -> dict[str, DimensionResult]:
    """Run all evaluator agents concurrently over the same generated section."""
    agents = list(EVALUATOR_AGENTS)
    results: dict[str, DimensionResult] = {}
    workers = max(1, len(agents))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rfp-eval") as pool:
        futures = {pool.submit(agent.evaluate, ctx): agent for agent in agents}
        for fut in as_completed(futures):
            agent = futures[fut]
            dim = fut.result()
            dim.evaluator_agent = agent.agent_name
            results[agent.dimension] = dim
    return results


def evaluate_section(
    *,
    department_id: str,
    draft_content: str,
    key_aspects: list[str],
    metadata: dict[str, Any],
) -> EvaluationResult:
    """Fan-out readability / relevance / compliance agents in parallel."""
    ctx = EvaluatorContext(
        department_id=department_id,
        draft_content=draft_content,
        key_aspects=list(key_aspects or []),
        metadata=dict(metadata or {}),
    )
    dims = run_evaluators_parallel(ctx)
    readability = dims["readability"]
    relevance = dims["relevance"]
    compliance = dims["compliance"]
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
        feedback_for_generator=list(feedback),
        parallel=True,
        evaluator_agents=[a.agent_name for a in EVALUATOR_AGENTS],
    )
