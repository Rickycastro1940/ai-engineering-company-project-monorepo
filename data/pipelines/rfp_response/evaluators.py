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
    CEO_NAME,
    CEO_USD_THRESHOLD,
    CONTEXT_SECTION_5_RULES,
    EVAL_DIMENSIONS,
    FORBIDDEN_COMPETITOR_NAMES,
    MIN_SETUP_BUSINESS_DAYS,
    OFFER_VALIDITY_DAYS,
    OFFER_VALIDITY_PHRASE,
    SECTION_OWNERS,
    SECTION_REQUIRED_HEADINGS,
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


class UnstructuredEvaluationError(TypeError):
    """Raised when evaluation_results is prose instead of an EvaluationResult object."""


def assert_evaluation_result_shape(payload: object) -> dict[str, Any]:
    """CONTEXT §2.3: evaluation_results is (readability, relevance, compliance) objects.

    Rejects unstructured text such as a single narrative string, or dimension
    values that are paragraphs instead of ``{passed, score, ...}`` dicts.
    """
    if isinstance(payload, str):
        raise UnstructuredEvaluationError(
            "evaluation_results must be a structured EvaluationResult object, "
            "not unstructured text"
        )
    if not isinstance(payload, dict):
        raise UnstructuredEvaluationError(
            f"evaluation_results must be a dict, not {type(payload).__name__}"
        )
    for dim in EVAL_DIMENSIONS:
        value = payload.get(dim)
        if isinstance(value, str):
            raise UnstructuredEvaluationError(
                f"evaluation_results.{dim} must be a structured object "
                "(passed/score/notes/failures), not unstructured text"
            )
        if not isinstance(value, dict):
            raise UnstructuredEvaluationError(
                f"evaluation_results.{dim} must be a dict, not {type(value).__name__}"
            )
        if not isinstance(value.get("passed"), bool):
            raise UnstructuredEvaluationError(
                f"evaluation_results.{dim}.passed must be a bool"
            )
        score = value.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise UnstructuredEvaluationError(
                f"evaluation_results.{dim}.score must be a number"
            )
        for list_key in ("notes", "failures", "rule_ids"):
            if list_key in value and not isinstance(value[list_key], list):
                raise UnstructuredEvaluationError(
                    f"evaluation_results.{dim}.{list_key} must be a list, not prose"
                )
    feedback = payload.get("feedback")
    if feedback is not None and not isinstance(feedback, list):
        raise UnstructuredEvaluationError(
            "evaluation_results.feedback must be a list of items, not unstructured text"
        )
    return payload


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
        payload = {
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
        return assert_evaluation_result_shape(payload)


@dataclass(frozen=True)
class EvaluatorContext:
    department_id: str
    draft_content: str
    key_aspects: list[str]
    metadata: dict[str, Any]


# Setup/delivery promises under MIN_SETUP_BUSINESS_DAYS (CONTEXT §5)
_SETUP_TOO_SHORT = re.compile(
    r"\b(?:setup|delivery|instalaci[oó]n|lead\s*time|timeline)\b"
    r"[^\n.]{0,40}?"
    r"(?:in|within|under|en|of|than)?\s*"
    r"(\d+)\s*(?:business\s*)?days?",
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
    """Section must match CONTEXT §2.1 format and answer the Part 1 RFP summary.

    Generic vendor outlines are not a substitute for the department contribution
    headings in CONTEXT-company.md §2.1.
    """
    text = (draft or "").casefold()
    notes: list[str] = []
    failures: list[str] = []
    score = 1.0

    if department_id.casefold() not in text and department_id.replace("_", " ") not in text:
        failures.append(f"Draft does not reference department `{department_id}`.")
        score -= 0.4

    owner = SECTION_OWNERS.get(department_id, "")
    if owner and owner.casefold() not in text:
        failures.append(
            f"Section format (CONTEXT §2.1) missing owner {owner}."
        )
        score -= 0.3

    missing_headings = [
        heading
        for heading in SECTION_REQUIRED_HEADINGS.get(department_id, ())
        if heading.casefold() not in text
    ]
    if missing_headings:
        failures.append(
            "Section format (CONTEXT §2.1) missing required heading(s): "
            + ", ".join(missing_headings)
        )
        score -= 0.2 * min(3, len(missing_headings))
    else:
        notes.append("context_section_2_1_format_ok")

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


def _check_brand_pillars(text_cf: str, _meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    missing = [p for p in BRAND_PILLARS if p not in text_cf]
    if missing:
        return (
            ["[brand_pillars] Missing brand pillar(s): " + ", ".join(missing)],
            [],
        )
    return [], ["brand_pillars_ok"]


def _check_offer_validity(text_cf: str, _meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    validity_ok = (
        OFFER_VALIDITY_PHRASE.casefold() in text_cf
        or (
            f"{OFFER_VALIDITY_DAYS} days" in text_cf
            and ("issuance" in text_cf or "valid" in text_cf or "validity" in text_cf)
        )
        or "30 days from issuance" in text_cf
    )
    if not validity_ok:
        return (
            [
                f"[offer_validity] Offer validity period ({OFFER_VALIDITY_PHRASE}) not stated."
            ],
            [],
        )
    return [], ["offer_validity_ok"]


def _check_min_setup_business_days(
    text: str, _meta: dict[str, Any]
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []
    for match in _SETUP_TOO_SHORT.finditer(text):
        days = int(match.group(1))
        if days < MIN_SETUP_BUSINESS_DAYS:
            failures.append(
                f"[min_setup_business_days] Setup/delivery promise of {days} days is "
                f"below {MIN_SETUP_BUSINESS_DAYS} business days."
            )
    text_cf = text.casefold()
    if (
        not failures
        and "business days" in text_cf
        and str(MIN_SETUP_BUSINESS_DAYS) in text_cf
    ):
        notes.append("setup_sla_mentioned")
    return failures, notes


def _check_no_competitors(text_cf: str, _meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    for name in FORBIDDEN_COMPETITOR_NAMES:
        if name in text_cf:
            failures.append(f"[no_competitors] Mentions competitor {name!r} (forbidden).")
    return failures, []


def _check_dual_currency(text: str, _meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []
    text_cf = text.casefold()
    if _MONEY.search(text) or _HAS_USD.search(text) or _HAS_COP.search(text):
        if not (_HAS_USD.search(text) and _HAS_COP.search(text)):
            failures.append(
                "[dual_currency] Monetary figures must be expressed with both "
                "USD $ and COP $ labels."
            )
        else:
            notes.append("dual_currency_ok")
    if re.search(r"converted at|exchange rate of|usando trm", text_cf):
        failures.append(
            "[dual_currency] Do not invent currency conversion / TRM rates."
        )
    return failures, notes


def _check_ceo_threshold(text: str, meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Flag (and require mention of) CEO approval when value exceeds $50,000 USD/year."""
    notes: list[str] = []
    failures: list[str] = []
    text_cf = text.casefold()
    value = meta.get("estimated_contract_value_usd")
    requires = bool(meta.get("requires_ceo_approval"))
    over = requires
    parsed: float | None = None
    if value is not None:
        try:
            parsed = float(value)
            over = over or parsed > CEO_USD_THRESHOLD
        except (TypeError, ValueError):
            notes.append("ceo_threshold_value_unparseable")
    if not over:
        return [], notes
    amount = parsed if parsed is not None else CEO_USD_THRESHOLD
    notes.append(
        f"ceo_approval_required_part3 (value_usd={amount:.0f} > {CEO_USD_THRESHOLD:.0f})"
    )
    mentions_ceo = CEO_NAME.casefold() in text_cf or (
        "ceo" in text_cf and "approval" in text_cf
    )
    if not mentions_ceo:
        failures.append(
            f"[ceo_threshold] Estimated contracts above ${CEO_USD_THRESHOLD:,.0f} USD/year "
            f"must flag additional CEO approval ({CEO_NAME}) before the final document "
            "is generated."
        )
    return failures, notes


_COMPLIANCE_CHECKERS: Final[dict[str, Any]] = {
    "brand_pillars": _check_brand_pillars,
    "offer_validity": _check_offer_validity,
    "min_setup_business_days": _check_min_setup_business_days,
    "no_competitors": _check_no_competitors,
    "dual_currency": _check_dual_currency,
    "ceo_threshold": _check_ceo_threshold,
}


def evaluate_compliance(draft: str, *, metadata: dict[str, Any] | None = None) -> DimensionResult:
    """Validate CONTEXT-company.md §5 business constraints on a section draft.

    Each CONTEXT_SECTION_5_RULES entry is checked; failures are tagged with
    that rule's ``id`` so feedback maps 1:1 to company guidelines.
    """
    text = draft or ""
    text_cf = text.casefold()
    notes: list[str] = []
    failures: list[str] = []
    rule_ids: list[str] = []
    score = 1.0
    meta = metadata or {}

    for rule in CONTEXT_SECTION_5_RULES:
        rule_id = rule["id"]
        checker = _COMPLIANCE_CHECKERS[rule_id]
        # Checkers that scan raw text (setup regex, dual-currency, CEO) need `text`.
        if rule_id in {"min_setup_business_days", "dual_currency", "ceo_threshold"}:
            rule_failures, rule_notes = checker(text, meta)
        else:
            rule_failures, rule_notes = checker(text_cf, meta)
        notes.extend(rule_notes)
        if rule_failures:
            failures.extend(rule_failures)
            rule_ids.append(rule_id)
            score -= 0.25 if rule_id != "min_setup_business_days" else 0.4
            if rule_id == "no_competitors":
                score -= 0.25  # already 0.25; total 0.5 to match prior severity
            if rule_id == "brand_pillars":
                missing_n = max(1, len([p for p in BRAND_PILLARS if p not in text_cf]))
                score -= 0.25 * (missing_n - 1)
        elif rule_id == "ceo_threshold" and any(
            n.startswith("ceo_approval_required_part3") for n in rule_notes
        ):
            # Part 2 flags the guideline; Part 3 enforces the extra approval.
            rule_ids.append(rule_id)

    score = max(0.0, min(1.0, score))
    passed = not failures and score >= 0.7
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
    """Does the section match CONTEXT §2.1 format and answer the Part 1 RFP summary?"""

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
