"""Reproducible Part 3 fixtures — simulated named-owner approvals (no UI).

Use these payloads with ``run_approval_pipeline(..., queued_decisions=...)``
or HTTP ``POST /rfp/tickets/{id}/approvals``. Reviewers must not depend on
irreproducible UI clicks alone.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from data.pipelines.rfp_approval.approvers import CEO_NAME, DEPARTMENT_OWNERS
from data.pipelines.rfp_intake.constants import STATUS_WAITING_FOR_APPROVAL

# Stable ticket id for the script / unit path (not a live HTTP upload).
ANDES_SIMULATED_TICKET_ID = "rfp-part3-andes-simulated"

ANDES_METADATA: dict[str, Any] = {
    "client_name": "Andes Tech Solutions",
    "location": "Medellín",
    "estimated_contract_value_usd": 20_000,
    "service_type": "weekly catering",
}

ANDES_DEPARTMENTS: tuple[str, ...] = ("marketing", "operaciones", "procurement")

ANDES_SECTIONS: list[dict[str, Any]] = [
    {
        "department_id": "marketing",
        "owner": DEPARTMENT_OWNERS["marketing"],
        "draft_content": (
            "## Brand terms\n"
            "Offer validity period: 30 days from issuance.\n"
            "Brasaland pillars: consistent quality, warm experience, speed of service.\n"
        ),
        "approval_status": "pending",
    },
    {
        "department_id": "operaciones",
        "owner": DEPARTMENT_OWNERS["operaciones"],
        "draft_content": (
            "## Setup times\n"
            "Setup in 12 business days.\n"
            "## Cost per event\n"
            "USD $40 per cover / COP $160000 per cover.\n"
        ),
        "approval_status": "pending",
    },
    {
        "department_id": "procurement",
        "owner": DEPARTMENT_OWNERS["procurement"],
        "draft_content": (
            "## Estimated ingredient cost based on volume\n"
            "USD $25 ingredient cost per cover / COP $100000.\n"
        ),
        "approval_status": "pending",
    },
]

SUNSET_SIMULATED_TICKET_ID = "rfp-part3-sunset-simulated"

SUNSET_METADATA: dict[str, Any] = {
    "client_name": "Sunset Bay Resorts, LLC",
    "location": "Florida",
    "estimated_contract_value_usd": 75_000,
    "service_type": "co-branded concession",
}

SUNSET_DEPARTMENTS: tuple[str, ...] = (
    "marketing",
    "operaciones",
    "procurement",
    "training",
)

SUNSET_SECTIONS: list[dict[str, Any]] = [
    {
        "department_id": "marketing",
        "owner": DEPARTMENT_OWNERS["marketing"],
        "draft_content": (
            "## Brand terms\n"
            "Offer validity period: 30 days from issuance.\n"
            "Exclusivity across Sunset Bay resorts.\n"
            "Brasaland pillars: consistent quality, warm experience, speed of service.\n"
        ),
        "approval_status": "pending",
    },
    {
        "department_id": "operaciones",
        "owner": DEPARTMENT_OWNERS["operaciones"],
        "draft_content": (
            "## Setup times\n"
            "Setup in 12 business days.\n"
            "## Cost per event\n"
            "USD $55 per cover / COP $220000 per cover.\n"
        ),
        "approval_status": "pending",
    },
    {
        "department_id": "procurement",
        "owner": DEPARTMENT_OWNERS["procurement"],
        "draft_content": (
            "## Estimated ingredient cost based on volume\n"
            "USD $30 ingredient cost per cover / COP $120000.\n"
        ),
        "approval_status": "pending",
    },
    {
        "department_id": "training",
        "owner": DEPARTMENT_OWNERS["training"],
        "draft_content": (
            "## Training and certification\n"
            "Signature-menu certification for resort staff within 12 business days.\n"
            "Brasaland pillars: consistent quality, warm experience, speed of service.\n"
        ),
        "approval_status": "pending",
    },
]


def andes_sections() -> list[dict[str, Any]]:
    return deepcopy(ANDES_SECTIONS)


def andes_metadata() -> dict[str, Any]:
    return deepcopy(ANDES_METADATA)


def sunset_sections() -> list[dict[str, Any]]:
    return deepcopy(SUNSET_SECTIONS)


def sunset_metadata() -> dict[str, Any]:
    return deepcopy(SUNSET_METADATA)


def simulated_department_approvals(
    departments: list[str] | tuple[str, ...] | None = None,
    *,
    decision: str = "approved",
) -> list[dict[str, str]]:
    """Programmatic resume payloads for CONTEXT named owners (no UI)."""
    depts = list(departments or ANDES_DEPARTMENTS)
    return [
        {
            "department_id": dept,
            "decision": decision,
            "approver": DEPARTMENT_OWNERS[dept],
        }
        for dept in depts
    ]


def simulated_ceo_approval(*, decision: str = "approved") -> dict[str, str]:
    return {
        "department_id": "ceo",
        "decision": decision,
        "approver": CEO_NAME,
    }


def andes_pipeline_kwargs(
    *,
    ticket_id: str = ANDES_SIMULATED_TICKET_ID,
    queued_decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Kwargs for ``run_approval_pipeline`` — Andes, no CEO."""
    return {
        "ticket_id": ticket_id,
        "status": STATUS_WAITING_FOR_APPROVAL,
        "sections": andes_sections(),
        "metadata": andes_metadata(),
        "departments_needed": list(ANDES_DEPARTMENTS),
        "requires_ceo_approval": False,
        "queued_decisions": (
            simulated_department_approvals(ANDES_DEPARTMENTS)
            if queued_decisions is None
            else list(queued_decisions)
        ),
    }


def sunset_pipeline_kwargs(
    *,
    ticket_id: str = SUNSET_SIMULATED_TICKET_ID,
    include_ceo: bool = True,
) -> dict[str, Any]:
    """Kwargs for ``run_approval_pipeline`` — Sunset Bay, CEO required."""
    decisions = simulated_department_approvals(SUNSET_DEPARTMENTS)
    if include_ceo:
        decisions.append(simulated_ceo_approval())
    return {
        "ticket_id": ticket_id,
        "status": STATUS_WAITING_FOR_APPROVAL,
        "sections": sunset_sections(),
        "metadata": sunset_metadata(),
        "departments_needed": list(SUNSET_DEPARTMENTS),
        "requires_ceo_approval": True,
        "queued_decisions": decisions,
    }


# --- Disagreement seeds (CONTEXT §7) for arbitration / iteration-limit tests ---

COST_DISAGREEMENT_SECTIONS: list[dict[str, Any]] = [
    {
        "department_id": "marketing",
        "owner": DEPARTMENT_OWNERS["marketing"],
        "draft_content": (
            "## Brand terms\n"
            "Offer validity period: 30 days from issuance.\n"
            "Brasaland pillars: consistent quality, warm experience, speed of service.\n"
        ),
        "approval_status": "pending",
    },
    {
        "department_id": "operaciones",
        "owner": DEPARTMENT_OWNERS["operaciones"],
        "draft_content": (
            "## Setup times\n"
            "Setup in 12 business days.\n"
            "## Cost per event\n"
            "USD $20 per cover.\n"
        ),
        "approval_status": "pending",
    },
    {
        "department_id": "procurement",
        "owner": DEPARTMENT_OWNERS["procurement"],
        "draft_content": (
            "## Estimated ingredient cost based on volume\n"
            "USD $80 ingredient cost per cover.\n"
        ),
        "approval_status": "pending",
    },
]

SETUP_SLA_BREACH_SECTIONS: list[dict[str, Any]] = [
    {
        "department_id": "marketing",
        "owner": DEPARTMENT_OWNERS["marketing"],
        "draft_content": (
            "## Brand terms\n"
            "Offer validity period: 30 days from issuance.\n"
            "Setup in 3 business days so we can start immediately.\n"
        ),
        "approval_status": "pending",
    },
    {
        "department_id": "operaciones",
        "owner": DEPARTMENT_OWNERS["operaciones"],
        "draft_content": (
            "## Setup times\n"
            "Setup in 12 business days.\n"
            "## Cost per event\n"
            "USD $40 per cover / COP $160000 per cover.\n"
        ),
        "approval_status": "pending",
    },
    {
        "department_id": "procurement",
        "owner": DEPARTMENT_OWNERS["procurement"],
        "draft_content": (
            "## Estimated ingredient cost based on volume\n"
            "USD $25 ingredient cost per cover / COP $100000.\n"
        ),
        "approval_status": "pending",
    },
]


def cost_disagreement_pipeline_kwargs(
    *,
    ticket_id: str = "rfp-part3-cost-disagreement",
    approval_iterations: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Andes-shaped ticket whose drafts trip ``cost-vs-feasibility`` (Camila)."""
    return {
        "ticket_id": ticket_id,
        "status": STATUS_WAITING_FOR_APPROVAL,
        "sections": deepcopy(COST_DISAGREEMENT_SECTIONS),
        "metadata": andes_metadata(),
        "departments_needed": list(ANDES_DEPARTMENTS),
        "requires_ceo_approval": False,
        "queued_decisions": [],
        "approval_iterations": dict(approval_iterations or {}),
    }


def setup_sla_breach_pipeline_kwargs(
    *,
    ticket_id: str = "rfp-part3-setup-sla-breach",
) -> dict[str, Any]:
    """Drafts trip ``setup-sla-breach`` (Felipe Guerrero fixed arbiter)."""
    return {
        "ticket_id": ticket_id,
        "status": STATUS_WAITING_FOR_APPROVAL,
        "sections": deepcopy(SETUP_SLA_BREACH_SECTIONS),
        "metadata": andes_metadata(),
        "departments_needed": list(ANDES_DEPARTMENTS),
        "requires_ceo_approval": False,
        "queued_decisions": [],
    }
