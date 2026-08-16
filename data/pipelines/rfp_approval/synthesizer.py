"""Part 3 ultimate synthesizer — FinalDocument (CONTEXT §2.3).

**Completion:** once every active department owner has approved (and Mariana
Restrepo when the $50k USD/year threshold applies), this module consolidates
the *approved* section drafts into one FinalDocument. It does not invent
commercial figures absent from intake metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_BRAND_PILLARS,
    CONTEXT_DEPARTMENT_LABELS,
    CONTEXT_FINAL_DOCUMENT_FIELDS,
    CONTEXT_OFFER_VALIDITY_PHRASE,
)
from data.pipelines.rfp_approval.approvers import CEO_DEPARTMENT_ID, CEO_NAME

FINAL_DOCUMENT_CONTEXT_FIELDS = CONTEXT_FINAL_DOCUMENT_FIELDS


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def assert_final_document_context_shape(document: dict[str, Any]) -> dict[str, Any]:
    """Require CONTEXT §2.3 FinalDocument fields (reject generic/incomplete payloads)."""
    missing = [f for f in FINAL_DOCUMENT_CONTEXT_FIELDS if f not in document]
    if missing:
        raise ValueError(
            f"FinalDocument missing CONTEXT §2.3 fields: {missing}; "
            f"required={list(FINAL_DOCUMENT_CONTEXT_FIELDS)}"
        )
    if not isinstance(document.get("sections"), list):
        raise ValueError("FinalDocument.sections must be a list")
    if not str(document.get("ticket_id") or "").strip():
        raise ValueError("FinalDocument.ticket_id is required")
    if not str(document.get("generated_at") or "").strip():
        raise ValueError("FinalDocument.generated_at is required")
    return document

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


def consolidate_approved_sections(
    *,
    sections: list[dict[str, Any]],
    departments_needed: list[str],
    approvals: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge Part 2 drafts with approval rows; keep only ``approved`` sections.

    Completion consolidates approved department sections — rejected /
    pending / request_changes drafts are excluded from the FinalDocument body.
    """
    by_dept = {
        str(row.get("department_id") or ""): dict(row)
        for row in sections
        if row.get("department_id")
    }
    approval_map = {
        str(dept): dict(payload)
        for dept, payload in dict(approvals or {}).items()
        if dept
    }
    consolidated: list[dict[str, Any]] = []
    for dept in departments_needed:
        row = dict(by_dept.get(dept) or {"department_id": dept})
        if dept in approval_map:
            row.update(approval_map[dept])
        status = str(row.get("approval_status") or "pending")
        if status != "approved":
            continue
        label = CONTEXT_DEPARTMENT_LABELS.get(dept, dept)
        consolidated.append(
            {
                "department_id": dept,
                "label": label,
                "owner": row.get("owner") or row.get("approver"),
                "approver": row.get("approver"),
                "approval_status": "approved",
                "approved_at": row.get("approved_at"),
                "draft_content": str(row.get("draft_content") or "").strip(),
            }
        )
    return consolidated


def build_final_document(
    *,
    ticket_id: str,
    sections: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    departments_needed: list[str] | None = None,
    approvals: list[dict[str, Any]] | dict[str, dict[str, Any]] | None = None,
    ceo_approval: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble CONTEXT §2.3 FinalDocument from approved sections only.

    Fields: ``ticket_id``, ``sections``, ``total_estimated_value``, ``generated_at``.
    """
    meta = dict(metadata or {})
    needed = list(
        departments_needed
        or [s.get("department_id") for s in sections if s.get("department_id")]
    )
    stamp = generated_at or _now()
    total = _total_estimated_value(meta)

    if isinstance(approvals, dict):
        approval_map = dict(approvals)
        approval_rows = [
            approval_map[d] for d in needed if d in approval_map
        ]
    else:
        approval_rows = list(approvals or [])
        approval_map = {
            str(row.get("department_id")): dict(row)
            for row in approval_rows
            if row.get("department_id")
        }

    body_sections = consolidate_approved_sections(
        sections=sections,
        departments_needed=needed,
        approvals=approval_map,
    )

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
    for row in approval_rows:
        if str(row.get("approval_status") or "") != "approved":
            continue
        markdown_parts.append(
            f"- `{row.get('department_id')}` — {row.get('approver')} "
            f"({row.get('approval_status')}"
            + (f" at {row.get('approved_at')}" if row.get("approved_at") else "")
            + ")"
        )
    if ceo_approval and str(ceo_approval.get("approval_status") or "") == "approved":
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

    for row in body_sections:
        markdown_parts.append(f"## {row['label']}")
        markdown_parts.append("")
        markdown_parts.append(row.get("draft_content") or "_(no draft)_")
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
    document = {
        "ticket_id": ticket_id,
        "sections": body_sections,
        "total_estimated_value": total,
        "generated_at": stamp,
        # Convenience / UI (not substitutes for the CONTEXT §2.3 fields above)
        "markdown": markdown,
        "client_name": meta.get("client_name"),
        "location": meta.get("location"),
        "offer_validity": CONTEXT_OFFER_VALIDITY_PHRASE,
        "brand_pillars": list(CONTEXT_BRAND_PILLARS),
        "completion": "consolidated_approved_sections",
    }
    return assert_final_document_context_shape(document)
