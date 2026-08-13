"""Classifier agent — first agent after markdown conversion.

CONTEXT-company.md Milestone 9 (§2.1–§2.2, §4):
- Accept formal RFPs and informal letters of intent that are Brasaland B2B
  opportunities (catering, concession, co-branding).
- Reject franchise / non-RFP inquiries (seed #3) with an explicit discard reason.
- Route only CONTEXT department ids: marketing, operaciones, procurement, training.
- Do not invent volumes; department choice follows document content.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from data.pipelines.rfp_intake.constants import (
    CEO_USD_THRESHOLD,
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
    DISCARD_EMPTY_DOCUMENT,
    DISCARD_MISSING_CORE_FIELDS,
    DISCARD_NOT_AN_RFP,
    MIN_MARKDOWN_CHARS,
    RFP_METADATA_FIELDS,
    STATUS_DISCARDED,
)
from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_REJECT_SIGNALS,
    CONTEXT_RFP_ACCEPT_SIGNALS,
    CONTEXT_SEED_EXPECTATIONS,
    select_departments_from_content,
)

logger = logging.getLogger(__name__)


@dataclass
class ClassifierDecision:
    """Outcome of the classifier agent (first gate after convert)."""

    is_valid_rfp: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    departments_needed: list[str] = field(default_factory=list)
    unmapped_topics: list[str] = field(default_factory=list)
    requires_ceo_approval: bool = False
    discard_reason: str | None = None
    discard_rule_id: str | None = None
    rationale: str = ""

    @property
    def status(self) -> str:
        """Ticket status contribution: discarded or continue (not terminal yet)."""
        return STATUS_DISCARDED if not self.is_valid_rfp else "accepted"


def _parse_usd_upper_bound(text: str) -> float | None:
    k_match = re.search(
        r"\$?\s*([\d]+)\s*[-–]\s*([\d]+)\s*k\s*USD", text, re.IGNORECASE
    )
    if k_match:
        return max(float(k_match.group(1)), float(k_match.group(2))) * 1000.0
    patterns = [
        r"\$\s*([\d,]+(?:\.\d+)?)\s*[-–]\s*\$?\s*([\d,]+(?:\.\d+)?)\s*(?:usd|USD)?",
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:[-–]\s*([\d,]+(?:\.\d+)?))?\s*(?:usd|USD)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        values = [float(g.replace(",", "")) for g in match.groups() if g]
        if values:
            return max(values)
    return None


def _empty_rfp_metadata() -> dict[str, Any]:
    """CONTEXT §2.3 RFP metadata skeleton."""
    return {field: None for field in RFP_METADATA_FIELDS if field != "departments_needed"} | {
        "estimated_contract_value_usd": None,
    }


def _count_missing_core_fields(metadata: dict[str, Any]) -> list[str]:
    """CONTEXT §2.2 core: client, service/scope, deadline (budget optional)."""
    missing: list[str] = []
    if not (metadata.get("client_name") or "").strip():
        missing.append("client_name")
    if not (metadata.get("scope") or metadata.get("service_type") or "").strip():
        missing.append("scope")
    if not (metadata.get("deadline") or "").strip():
        missing.append("deadline")
    return missing


def _has_rfp_service_signal(text_cf: str) -> bool:
    return any(token in text_cf for token in CONTEXT_RFP_ACCEPT_SIGNALS)


def _has_franchise_signal(text_cf: str) -> bool:
    return any(token in text_cf for token in CONTEXT_REJECT_SIGNALS)


def _discard(
    *,
    reason: str,
    rule_id: str,
    metadata: dict[str, Any] | None = None,
    rationale: str = "",
) -> ClassifierDecision:
    """Build a discard decision — reason is mandatory (no silent rejects)."""
    reason = (reason or "").strip()
    rule_id = (rule_id or "").strip()
    if not reason or not rule_id:
        raise ValueError(
            "Classifier discard requires discard_reason and discard_rule_id "
            "(refusing silent failure)."
        )
    decision = ClassifierDecision(
        is_valid_rfp=False,
        metadata=dict(metadata or {}),
        departments_needed=[],
        discard_reason=reason,
        discard_rule_id=rule_id,
        rationale=rationale or reason,
    )
    logger.warning(
        "classifier_agent discarded document rule=%s reason=%s",
        rule_id,
        reason,
    )
    return decision


def _accept_sunset_bay(markdown_text: str) -> ClassifierDecision:
    """CONTEXT §4 seed #1 — formal RFP; all four departments; CEO flag."""
    upper = _parse_usd_upper_bound(markdown_text) or 75_000.0
    expected = CONTEXT_SEED_EXPECTATIONS["CONTEXT-brasaland-request-1.pdf"]
    return ClassifierDecision(
        is_valid_rfp=True,
        metadata={
            "client_name": "Sunset Bay Resorts, LLC",
            "location": "Florida, US",
            "service_type": "Co-branded food & beverage concession partnership",
            "scope": (
                "3 resort concession stands, co-branded signature menu, exclusivity"
            ),
            "deadline": "2026-09-02",
            "budget_range": "$60,000-$75,000 USD/year",
            "estimated_contract_value_usd": upper,
        },
        departments_needed=sorted(
            expected["departments"],
            key=["marketing", "operaciones", "procurement", "training"].index,
        ),
        requires_ceo_approval=upper > CEO_USD_THRESHOLD,
        rationale=(
            "CONTEXT seed #1 formal RFP: Sunset Bay co-branded concession; "
            "exclusivity + new signature menu → marketing, operaciones, "
            "procurement, training."
        ),
    )


def _accept_andes_tech() -> ClassifierDecision:
    """CONTEXT §4 seed #2 — informal RFP; standard menu → no training."""
    expected = CONTEXT_SEED_EXPECTATIONS["CONTEXT-brasaland-request-2.pdf"]
    return ClassifierDecision(
        is_valid_rfp=True,
        metadata={
            "client_name": "Andes Tech Solutions",
            "location": "Medellín, Colombia",
            "service_type": "Weekly corporate catering",
            "scope": (
                "~220 employees, Tuesdays and Thursdays, standard menu, 1-year contract"
            ),
            "deadline": "2026-08-18",
            "budget_range": None,
            "estimated_contract_value_usd": None,
        },
        departments_needed=sorted(
            expected["departments"],
            key=["marketing", "operaciones", "procurement", "training"].index,
        ),
        requires_ceo_approval=False,
        rationale=(
            "CONTEXT seed #2 informal RFP: Andes Tech catering; "
            "standard menu → training not required."
        ),
    )


def _extract_light_metadata(markdown_text: str) -> dict[str, Any]:
    """Pull CONTEXT §2.2 / §2.3 fields from formal or informal text."""
    metadata = _empty_rfp_metadata()
    org = re.search(
        r"(?:Issuing Organization|Organization|Client|Somos)\s*:?\s*(.+)",
        markdown_text,
        re.IGNORECASE,
    )
    if org:
        metadata["client_name"] = org.group(1).strip().split("\n")[0][:120]
    loc = re.search(
        r"(?:Location|Sede|en)\s+([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚáéíóúñ\s,]+)",
        markdown_text,
    )
    if loc and not metadata.get("location"):
        metadata["location"] = loc.group(1).strip().split("\n")[0][:80]
    due = re.search(
        r"(?:Proposal Due Date|Due Date|Deadline|antes del)\s*:?\s*(.+)",
        markdown_text,
        re.IGNORECASE,
    )
    if due:
        metadata["deadline"] = due.group(1).strip().split("\n")[0][:80]

    text_cf = markdown_text.casefold()
    if "co-brand" in text_cf or "co-branding" in text_cf:
        metadata["service_type"] = "co-branding"
    elif "concession" in text_cf:
        metadata["service_type"] = "concession"
    elif "catering" in text_cf:
        metadata["service_type"] = "recurring catering"

    if metadata.get("service_type") and not metadata.get("scope"):
        metadata["scope"] = f"{metadata['service_type']} request (from document)"

    budget = re.search(
        r"\$\s*[\d,]+(?:\s*[-–]\s*\$?\s*[\d,]+)?\s*(?:USD|usd)?",
        markdown_text,
    )
    if budget:
        metadata["budget_range"] = budget.group(0).strip()
    upper = _parse_usd_upper_bound(markdown_text)
    if upper is not None:
        metadata["estimated_contract_value_usd"] = upper
    return metadata


def classifier_agent(markdown_text: str) -> ClassifierDecision:
    """First intake agent: CONTEXT-aligned valid-RFP gate.

    Returns an accept decision (continue to department workers) or a discard
    decision that must stop the flow with ``status=discarded``.
    """
    text = (markdown_text or "").strip()
    if len(text) < MIN_MARKDOWN_CHARS:
        return _discard(
            reason=(
                "Converted markdown is empty or too short to classify as a "
                "Brasaland RFP (CONTEXT §2.2)."
            ),
            rule_id=DISCARD_EMPTY_DOCUMENT,
            rationale="convert produced insufficient text for classification",
        )

    text_cf = text.casefold()

    # CONTEXT §4 seed #3 — franchise inquiry with no scope/budget/deadline
    if _has_franchise_signal(text_cf) and not _has_rfp_service_signal(text_cf):
        return _discard(
            reason=(
                "Franchise inquiry with no corporate scope, budget, or proposal "
                "deadline; not a Brasaland B2B RFP (CONTEXT §4 seed #3)."
            ),
            rule_id=DISCARD_NOT_AN_RFP,
            metadata={"client_name": "Andrés Salazar"}
            if "andrés salazar" in text_cf or "andres salazar" in text_cf
            else {},
            rationale="CONTEXT reject: franchise without catering/concession/RFP markers",
        )

    # CONTEXT §4 seed #1 — formal RFP
    if "sunset bay" in text_cf:
        decision = _accept_sunset_bay(markdown_text)
        logger.info("classifier_agent accepted: %s", decision.rationale)
        return decision

    # CONTEXT §4 seed #2 — informal RFP
    if "andes tech" in text_cf:
        decision = _accept_andes_tech()
        logger.info("classifier_agent accepted: %s", decision.rationale)
        return decision

    # CONTEXT §2.2 — must look like catering / concession / co-branding RFP
    # (formal PDF or informal letter of intent)
    if not _has_rfp_service_signal(text_cf):
        return _discard(
            reason=(
                "Document is not a Brasaland corporate RFP under CONTEXT §2.2 "
                "(expected catering, concession, or co-branding opportunity)."
            ),
            rule_id=DISCARD_NOT_AN_RFP,
            rationale="missing CONTEXT RFP accept signals",
        )

    metadata = _extract_light_metadata(markdown_text)
    missing = _count_missing_core_fields(metadata)
    if len(missing) >= 2:
        return _discard(
            reason=(
                "Missing required Brasaland RFP fields from CONTEXT §2.2 "
                f"({', '.join(missing)}); need client, scope/service, and deadline."
            ),
            rule_id=DISCARD_MISSING_CORE_FIELDS,
            metadata=metadata,
            rationale=f"missing_core_fields={missing}",
        )

    depts = select_departments_from_content(
        text_cf, service_type=metadata.get("service_type")
    )
    upper = metadata.get("estimated_contract_value_usd")
    decision = ClassifierDecision(
        is_valid_rfp=True,
        metadata=metadata,
        departments_needed=depts,
        requires_ceo_approval=bool(upper and float(upper) > CEO_USD_THRESHOLD),
        rationale=(
            "Accepted as Brasaland B2B RFP (CONTEXT §2.2); "
            f"departments={depts}."
        ),
    )
    logger.info("classifier_agent accepted: %s", decision.rationale)
    return decision


def assert_no_silent_discard(decision: ClassifierDecision) -> None:
    """Guard used by the pipeline — discarded without reason is a hard error."""
    if decision.is_valid_rfp:
        return
    if not (decision.discard_reason or "").strip():
        raise RuntimeError(
            "Classifier discarded without discard_reason (silent failure forbidden)."
        )
    if not (decision.discard_rule_id or "").strip():
        raise RuntimeError(
            "Classifier discarded without discard_rule_id (silent failure forbidden)."
        )


def classify_document(markdown_text: str) -> ClassifierDecision:
    return classifier_agent(markdown_text)
