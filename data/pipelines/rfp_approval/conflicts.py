"""Detect CONTEXT §7 contradictions in structured state (not LLM consensus).

Agents may *surface* a conflict; they must not resolve it. Resolution lives in
``arbitration.py`` (fixed arbiter table).
"""

from __future__ import annotations

import re
from typing import Any

from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_ARBITRATION_TRIGGER_IDS,
    CONTEXT_CEO_USD_THRESHOLD,
    CONTEXT_MIN_SETUP_BUSINESS_DAYS,
)
from data.pipelines.rfp_approval.approvers import (
    CEO_DEPARTMENT_ID,
    requires_ceo_approval,
)

# Same intent as Part 2 compliance: setup/delivery promises with a day count.
_SETUP_DAYS = re.compile(
    r"\b(?:setup|delivery|instalaci[oó]n|lead\s*time|timeline|go-live|golive)\b"
    r"[^\n.]{0,60}?"
    r"(?:in|within|under|en|of|than|as little as)?\s*"
    r"(\d+)\s*(?:business\s*)?days?",
    re.I,
)
_USD_AMOUNT = re.compile(
    r"(?:USD\s*\$?|\$)\s*([\d,]+(?:\.\d+)?)",
    re.I,
)

TRIGGER_COST_VS_FEASIBILITY = "cost-vs-feasibility"
TRIGGER_SETUP_SLA_BREACH = "setup-sla-breach"
TRIGGER_CEO_THRESHOLD = "ceo-threshold"

assert TRIGGER_COST_VS_FEASIBILITY in CONTEXT_ARBITRATION_TRIGGER_IDS
assert TRIGGER_SETUP_SLA_BREACH in CONTEXT_ARBITRATION_TRIGGER_IDS
assert TRIGGER_CEO_THRESHOLD in CONTEXT_ARBITRATION_TRIGGER_IDS


def extract_usd_amounts(text: str) -> list[float]:
    amounts: list[float] = []
    for match in _USD_AMOUNT.finditer(text or ""):
        raw = match.group(1).replace(",", "")
        try:
            amounts.append(float(raw))
        except ValueError:
            continue
    return amounts


def extract_setup_day_promises(text: str) -> list[int]:
    days: list[int] = []
    for match in _SETUP_DAYS.finditer(text or ""):
        try:
            days.append(int(match.group(1)))
        except ValueError:
            continue
    return days


def _section_map(sections: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in sections:
        dept = str(row.get("department_id") or "")
        if dept:
            out[dept] = row
    return out


def _draft(section: dict[str, Any] | None) -> str:
    if not section:
        return ""
    return str(section.get("draft_content") or "")


def detect_cost_vs_feasibility(sections: list[dict[str, Any]]) -> dict[str, Any] | None:
    """procurement ingredient/cost cannot support operaciones per-event price."""
    by_dept = _section_map(sections)
    ops = _draft(by_dept.get("operaciones"))
    proc = _draft(by_dept.get("procurement"))
    if not ops or not proc:
        return None
    ops_prices = extract_usd_amounts(ops)
    proc_costs = extract_usd_amounts(proc)
    if not ops_prices or not proc_costs:
        return None
    ops_price = max(ops_prices)
    proc_cost = min(proc_costs)
    if proc_cost <= ops_price:
        return None
    return {
        "trigger_id": TRIGGER_COST_VS_FEASIBILITY,
        "fired": True,
        "evidence": {
            "operaciones_implied_price_usd": ops_price,
            "procurement_ingredient_cost_usd": proc_cost,
        },
        "affected_departments": ["operaciones", "procurement"],
        "message": (
            f"Procurement ingredient/cost USD ${proc_cost:,.0f} cannot support "
            f"operaciones per-event/per-cover price USD ${ops_price:,.0f}"
        ),
    }


def detect_setup_sla_breach(sections: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Any section promises setup/delivery under 10 business days."""
    affected: list[str] = []
    evidence: dict[str, list[int]] = {}
    for row in sections:
        dept = str(row.get("department_id") or "")
        days = extract_setup_day_promises(_draft(row))
        too_short = [d for d in days if d < CONTEXT_MIN_SETUP_BUSINESS_DAYS]
        if too_short:
            affected.append(dept)
            evidence[dept] = too_short
    if not affected:
        return None
    return {
        "trigger_id": TRIGGER_SETUP_SLA_BREACH,
        "fired": True,
        "evidence": {"too_short_days_by_department": evidence},
        "affected_departments": affected,
        "message": (
            "Setup/delivery promise under "
            f"{CONTEXT_MIN_SETUP_BUSINESS_DAYS} business days in: {', '.join(affected)}"
        ),
    }


def detect_ceo_threshold(
    *,
    metadata: dict[str, Any],
    requires_ceo_flag: bool,
    ceo_approval: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Estimated annual value > $50k USD and CEO approval still pending."""
    needed = requires_ceo_approval(
        requires_ceo_flag=requires_ceo_flag, metadata=metadata
    )
    if not needed:
        return None
    status = str((ceo_approval or {}).get("approval_status") or "pending")
    if status == "approved":
        return None
    value = metadata.get("estimated_contract_value_usd")
    return {
        "trigger_id": TRIGGER_CEO_THRESHOLD,
        "fired": True,
        "evidence": {
            "estimated_contract_value_usd": value,
            "threshold_usd": CONTEXT_CEO_USD_THRESHOLD,
            "ceo_approval_status": status,
        },
        "affected_departments": [CEO_DEPARTMENT_ID],
        "message": (
            f"Estimated annual value exceeds USD ${CONTEXT_CEO_USD_THRESHOLD:,.0f}; "
            f"CEO approval is {status}"
        ),
    }


def conflict_surface_agent(
    *,
    sections: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    requires_ceo_flag: bool = False,
    ceo_approval: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Surface detectable contradictions. Does not resolve them."""
    meta = metadata or {}
    surfaced: list[dict[str, Any]] = []
    for detector in (
        lambda: detect_cost_vs_feasibility(sections),
        lambda: detect_setup_sla_breach(sections),
        lambda: detect_ceo_threshold(
            metadata=meta,
            requires_ceo_flag=requires_ceo_flag,
            ceo_approval=ceo_approval,
        ),
    ):
        hit = detector()
        if hit:
            surfaced.append(hit)
    return surfaced
