"""Part 3 ultimate synthesizer — FinalDocument (CONTEXT §2.3).

Blocked until every active department owner has approved independently, and
until Mariana Restrepo (CEO) has approved when the $50k USD/year threshold
applies. Does not invent commercial figures absent from intake metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_BRAND_PILLARS,
    CONTEXT_DEPARTMENT_LABELS,
    CONTEXT_OFFER_VALIDITY_PHRASE,
)
from data.pipelines.rfp_approval.approvers import CEO_DEPARTMENT_ID, CEO_NAME


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _total_estimated_value(metadata: dict[str, Any]) -> float | None:
    value = metadata.get("estimated_contract_value_usd")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def synthesizer_ready(
    *,
    department_approvals: dict[str, str],
    departments_needed: list[str],
    requires_ceo: bool,
    ceo_approval_status: str | None,
    request_changes: list[str] | None = None,
) -> tuple[bool, str]:
    """Return (ready, blocker). Synthesis runs only after independent sign-off."""
    pending_changes = [d for d in (request_changes or []) if d in departments_needed]
    if pending_changes:
        return False, f"request_changes outstanding: {', '.join(pending_changes)}"
    for dept in departments_needed:
        status = department_approvals.get(dept) or "pending"
        if status != "approved":
            return False, f"{dept} approval_status={status}"
    if requires_ceo and (ceo_approval_status or "pending") != "approved":
        return False, f"CEO {CEO_NAME} approval_status={ceo_approval_status or 'pending'}"
    if requires_ceo is False and (ceo_approval_status or "") == "rejected":
        return False, f"CEO {CEO_NAME} rejected"
    if (ceo_approval_status or "") == "rejected":
        return False, f"CEO {CEO_NAME} rejected"
    return True, ""


def build_final_document(
    *,
    ticket_id: str,
    sections: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    departments_needed: list[str] | None = None,
    approvals: list[dict[str, Any]] | None = None,
    ceo_approval: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble CONTEXT §2.3 FinalDocument: ticket_id, sections, total, generated_at."""
    meta = dict(metadata or {})
    needed = list(departments_needed or [s.get("department_id") for s in sections if s.get("department_id")])
    stamp = generated_at or _now()
    total = _total_estimated_value(meta)
    body_sections: list[dict[str, Any]] = []
    markdown_parts: list[str] = [
        "# Brasaland pricing proposal",
        "",
        f"**Ticket:** `{ticket_id}`",
        f"**Client:** {meta.get('client_name') or '—'}",
        f"**Location:** {meta.get('location') or '—'}",
        f"**Service:** {meta.get('service_type') or meta.get('scope') or '—'}",
        f"**Generated at:** {stamp}",
        f"**Offer validity:** {CONTEXT_OFFER_VALIDITY_PHRASE}.",
        "",
        (
            "Brasaland delivers on our three pillars — "
            + ", ".join(CONTEXT_BRAND_PILLARS)
            + " — in every corporate engagement."
        ),
        "",
        "## Sign-off",
    ]
    for row in approvals or []:
        markdown_parts.append(
            f"- `{row.get('department_id')}` — {row.get('approver')} "
            f"({row.get('approval_status')}"
            + (f" at {row.get('approved_at')}" if row.get("approved_at") else "")
            + ")"
        )
    if ceo_approval:
        markdown_parts.append(
            f"- `{CEO_DEPARTMENT_ID}` — {ceo_approval.get('approver') or CEO_NAME} "
            f"({ceo_approval.get('approval_status')}"
            + (
                f" at {ceo_approval.get('approved_at')}"
                if ceo_approval.get("approved_at")
                else ""
            )
            + ")"
        )
    markdown_parts.append("")

    by_dept = {str(s.get("department_id")): s for s in sections}
    for dept in needed:
        row = by_dept.get(dept) or {}
        label = CONTEXT_DEPARTMENT_LABELS.get(dept, dept)
        draft = str(row.get("draft_content") or "").strip()
        body_sections.append(
            {
                "department_id": dept,
                "label": label,
                "owner": row.get("owner") or row.get("approver"),
                "approval_status": row.get("approval_status"),
                "draft_content": draft,
            }
        )
        markdown_parts.append(f"## {label}")
        markdown_parts.append("")
        markdown_parts.append(draft or "_(no draft)_")
        markdown_parts.append("")

    if total is not None:
        markdown_parts.extend(
            [
                "## Commercial envelope",
                "",
                f"Total estimated value (from intake, not invented): USD ${total:,.0f}/year. "
                "Any matching COP $ figure is kept as written — no FX conversion.",
                "",
            ]
        )

    markdown = "\n".join(markdown_parts).strip() + "\n"
    return {
        "ticket_id": ticket_id,
        "sections": body_sections,
        "total_estimated_value": total,
        "generated_at": stamp,
        "markdown": markdown,
        "client_name": meta.get("client_name"),
        "location": meta.get("location"),
        "offer_validity": CONTEXT_OFFER_VALIDITY_PHRASE,
        "brand_pillars": list(CONTEXT_BRAND_PILLARS),
    }
