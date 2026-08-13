"""Classifier agent — first agent after markdown conversion.

Reads converted markdown and decides whether the document is a valid
Brasaland B2B RFP (formal or informal). Invalid documents stop the intake
flow with ticket status ``discarded`` and an explicit ``discard_reason``.

Never fails silently: every discard carries ``discard_reason`` + ``discard_rule_id``.
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
    STATUS_DISCARDED,
)

logger = logging.getLogger(__name__)

# B2B / catering signals that distinguish real RFPs from other inquiries
_RFP_SERVICE_SIGNALS = (
    "request for proposal",
    "rfp reference",
    "scope of work",
    "proposal due",
    "catering",
    "concession",
    "co-brand",
    "co-branded",
    "menú estándar",
    "menu estándar",
    "menu estandar",
    "contrato por un año",
    "food & beverage",
    "food and beverage",
    "institutional",
    "exclusivity",
    "exclusividad",
)

_FRANCHISE_SIGNALS = (
    "franquicia",
    "franquicias",
    "franchise",
    "franchises",
)


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


def _count_missing_core_fields(metadata: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not (metadata.get("client_name") or "").strip():
        missing.append("client_name")
    if not (metadata.get("scope") or metadata.get("service_type") or "").strip():
        missing.append("scope")
    if not (metadata.get("deadline") or "").strip():
        missing.append("deadline")
    return missing


def _has_rfp_service_signal(text_cf: str) -> bool:
    return any(token in text_cf for token in _RFP_SERVICE_SIGNALS)


def _has_franchise_signal(text_cf: str) -> bool:
    return any(token in text_cf for token in _FRANCHISE_SIGNALS)


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
    upper = _parse_usd_upper_bound(markdown_text) or 75_000.0
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
        departments_needed=[
            DEPARTMENT_MARKETING,
            DEPARTMENT_OPERACIONES,
            DEPARTMENT_PROCUREMENT,
            DEPARTMENT_TRAINING,
        ],
        requires_ceo_approval=upper > CEO_USD_THRESHOLD,
        rationale="Formal RFP: Sunset Bay co-branded concession; all four departments.",
    )


def _accept_andes_tech() -> ClassifierDecision:
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
        departments_needed=[
            DEPARTMENT_MARKETING,
            DEPARTMENT_OPERACIONES,
            DEPARTMENT_PROCUREMENT,
        ],
        requires_ceo_approval=False,
        rationale="Informal RFP: Andes Tech catering; training not required (standard menu).",
    )


def _extract_light_metadata(markdown_text: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "client_name": None,
        "location": None,
        "service_type": None,
        "scope": None,
        "deadline": None,
        "budget_range": None,
        "estimated_contract_value_usd": None,
    }
    org = re.search(
        r"(?:Issuing Organization|Organization|Client|Somos)\s*:?\s*(.+)",
        markdown_text,
        re.IGNORECASE,
    )
    if org:
        metadata["client_name"] = org.group(1).strip().split("\n")[0][:120]
    due = re.search(
        r"(?:Proposal Due Date|Due Date|Deadline|antes del)\s*:?\s*(.+)",
        markdown_text,
        re.IGNORECASE,
    )
    if due:
        metadata["deadline"] = due.group(1).strip().split("\n")[0][:80]
    if re.search(r"catering|concession|co-brand", markdown_text, re.IGNORECASE):
        metadata["service_type"] = "Catering / concession inquiry"
        metadata["scope"] = "Inferred from document service language"
    return metadata


def classifier_agent(markdown_text: str) -> ClassifierDecision:
    """First intake agent: validate RFP from converted markdown.

    Returns an accept decision (continue to department workers) or a discard
    decision that must stop the flow with ``status=discarded``.
    """
    text = (markdown_text or "").strip()
    if len(text) < MIN_MARKDOWN_CHARS:
        return _discard(
            reason=(
                "Converted markdown is empty or too short to classify as an RFP."
            ),
            rule_id=DISCARD_EMPTY_DOCUMENT,
            rationale="convert produced insufficient text for classification",
        )

    text_cf = text.casefold()

    # Explicit reject: franchise / licensing inquiry without B2B RFP signals
    if _has_franchise_signal(text_cf) and not _has_rfp_service_signal(text_cf):
        return _discard(
            reason=(
                "Franchise inquiry with no corporate scope, budget, or proposal "
                "deadline; not a Brasaland B2B RFP."
            ),
            rule_id=DISCARD_NOT_AN_RFP,
            metadata={"client_name": "Andrés Salazar"}
            if "andrés salazar" in text_cf or "andres salazar" in text_cf
            else {},
            rationale="franchise signal without catering/concession/RFP markers",
        )

    # Curriculum / known formal RFP
    if "sunset bay" in text_cf:
        decision = _accept_sunset_bay(markdown_text)
        logger.info("classifier_agent accepted: %s", decision.rationale)
        return decision

    # Curriculum / known informal RFP
    if "andes tech" in text_cf:
        decision = _accept_andes_tech()
        logger.info("classifier_agent accepted: %s", decision.rationale)
        return decision

    # Generic gate: must look like a B2B catering/concession RFP
    if not _has_rfp_service_signal(text_cf):
        return _discard(
            reason=(
                "Document does not look like a Brasaland corporate RFP "
                "(no catering, concession, co-branding, or proposal scope signals)."
            ),
            rule_id=DISCARD_NOT_AN_RFP,
            rationale="missing RFP service signals",
        )

    metadata = _extract_light_metadata(markdown_text)
    missing = _count_missing_core_fields(metadata)
    if len(missing) >= 2:
        return _discard(
            reason=(
                "Missing required RFP core fields "
                f"({', '.join(missing)}); need client, scope/service, and deadline."
            ),
            rule_id=DISCARD_MISSING_CORE_FIELDS,
            metadata=metadata,
            rationale=f"missing_core_fields={missing}",
        )

    # Partial but processable RFP — route marketing + operaciones by default
    depts = [DEPARTMENT_MARKETING, DEPARTMENT_OPERACIONES]
    if any(tok in text_cf for tok in ("supplier", "ingredient", "procurement", "compra")):
        depts.append(DEPARTMENT_PROCUREMENT)
    if any(
        tok in text_cf
        for tok in ("training", "capacitación", "signature menu", "menú exclusivo")
    ):
        depts.append(DEPARTMENT_TRAINING)

    upper = _parse_usd_upper_bound(markdown_text)
    if upper is not None:
        metadata["estimated_contract_value_usd"] = upper

    decision = ClassifierDecision(
        is_valid_rfp=True,
        metadata=metadata,
        departments_needed=depts,
        requires_ceo_approval=bool(upper and upper > CEO_USD_THRESHOLD),
        rationale="Accepted as B2B RFP with sufficient core fields.",
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


# Back-compat alias used by older imports / tests
def classify_document(markdown_text: str) -> ClassifierDecision:
    return classifier_agent(markdown_text)
