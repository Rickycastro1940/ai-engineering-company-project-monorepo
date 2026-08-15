"""CONTEXT §7 arbitration — dedicated node, fixed arbiter, not an LLM.

Wire trigger ids into this module. Agents may surface a conflict; they must
not resolve it by free-form consensus.
"""

from __future__ import annotations

from typing import Any, Final

from data.pipelines.rfp_intake.context_rules import CONTEXT_ARBITRATION_RULES
from data.pipelines.rfp_approval.conflicts import (
    TRIGGER_CEO_THRESHOLD,
    TRIGGER_COST_VS_FEASIBILITY,
    TRIGGER_SETUP_SLA_BREACH,
)

RESOLUTION_ACTION_REQUEST_CHANGES: Final = "request_changes"
RESOLUTION_ACTION_BLOCK_SYNTHESIZER: Final = "block_synthesizer"


def _rule(trigger_id: str) -> dict[str, str]:
    rule = CONTEXT_ARBITRATION_RULES.get(trigger_id)
    if not rule:
        raise KeyError(f"No CONTEXT §7 arbitration rule for {trigger_id!r}")
    return rule


def apply_fixed_arbitration(conflicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve each surfaced conflict with the CONTEXT table (no LLM)."""
    resolutions: list[dict[str, Any]] = []
    for conflict in conflicts:
        trigger_id = str(conflict.get("trigger_id") or "")
        if not trigger_id:
            continue
        rule = _rule(trigger_id)
        affected = list(conflict.get("affected_departments") or [])
        action = rule["action"]
        if trigger_id == TRIGGER_COST_VS_FEASIBILITY:
            action = RESOLUTION_ACTION_REQUEST_CHANGES
        elif trigger_id == TRIGGER_SETUP_SLA_BREACH:
            action = RESOLUTION_ACTION_REQUEST_CHANGES
        elif trigger_id == TRIGGER_CEO_THRESHOLD:
            action = RESOLUTION_ACTION_BLOCK_SYNTHESIZER
        resolutions.append(
            {
                "trigger_id": trigger_id,
                "arbiter": rule["arbiter"],
                "arbiter_department_id": rule.get("arbiter_department_id"),
                "escalation_arbiter": rule.get("escalation_arbiter"),
                "action": action,
                "resolution_rule": rule["resolution"],
                "affected_departments": affected,
                "llm_resolved": False,
                "evidence": conflict.get("evidence") or {},
                "message": conflict.get("message"),
            }
        )
    return resolutions


def request_changes_departments(resolutions: list[dict[str, Any]]) -> list[str]:
    depts: list[str] = []
    for row in resolutions:
        if row.get("action") != RESOLUTION_ACTION_REQUEST_CHANGES:
            continue
        for dept in row.get("affected_departments") or []:
            if dept not in depts:
                depts.append(dept)
    return depts


def synthesizer_blocked_by_arbitration(
    resolutions: list[dict[str, Any]],
    *,
    ceo_approval_status: str | None,
) -> bool:
    """CEO threshold blocks synthesis until Mariana Restrepo approves."""
    for row in resolutions:
        if row.get("trigger_id") != TRIGGER_CEO_THRESHOLD:
            continue
        if (ceo_approval_status or "pending") != "approved":
            return True
    return False
