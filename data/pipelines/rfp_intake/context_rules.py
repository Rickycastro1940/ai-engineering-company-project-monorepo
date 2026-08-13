"""CONTEXT-company.md Milestone 9 rules — source of truth for Brasaland RFP intake.

Department ids, owners, RFP format fields, and classification criteria are
derived from CONTEXT §2.1–§2.2 and §4. Do not invent alternate departments
(e.g. ``sales``, ``operations``, ``hr``) or generic SaaS RFP schemas.
"""

from __future__ import annotations

from typing import Final

# --- CONTEXT §2.1 — exact department_id values (Spanish id for operaciones) ---
CONTEXT_DEPARTMENT_IDS: Final[tuple[str, ...]] = (
    "marketing",
    "operaciones",
    "procurement",
    "training",
)

CONTEXT_DEPARTMENT_OWNERS: Final[dict[str, str]] = {
    "marketing": "Camila Ospina",
    "operaciones": "Felipe Guerrero",
    "procurement": "Lucía Fernández",
    "training": "Jake Morrison",
}

CONTEXT_DEPARTMENT_LABELS: Final[dict[str, str]] = {
    "marketing": "Marketing and Digital Experience",
    "operaciones": "Restaurant Operations",
    "procurement": "Procurement and Suppliers",
    "training": "Training and Quality Standards",
}

# What each department contributes (CONTEXT §2.1 table)
CONTEXT_DEPARTMENT_CONTRIBUTIONS: Final[dict[str, str]] = {
    "marketing": (
        "Brand terms, exclusivity, co-branding, offer validity period. Owns the ticket."
    ),
    "operaciones": (
        "Operational feasibility: kitchen/staff capacity, setup times, cost per event"
    ),
    "procurement": (
        "Estimated ingredient cost based on volume, supplier lead times"
    ),
    "training": (
        "If the request requires a new recipe or standard, the development and "
        "certification time needed"
    ),
}

# Forbidden generic ids that would ignore Brasaland CONTEXT
FORBIDDEN_DEPARTMENT_IDS: Final[frozenset[str]] = frozenset(
    {
        "sales",
        "operations",  # must be operaciones
        "ops",
        "hr",
        "finance",
        "legal",
        "engineering",
        "customer_success",
    }
)

# --- CONTEXT §2.2 — what a real Brasaland RFP looks like ---
# Formal or informal; typically include these fields:
CONTEXT_RFP_METADATA_FIELDS: Final[tuple[str, ...]] = (
    "client_name",
    "location",
    "service_type",
    "scope",
    "deadline",
    "budget_range",  # optional
    "departments_needed",
)

# Service types called out in CONTEXT §2.2
CONTEXT_SERVICE_TYPES: Final[tuple[str, ...]] = (
    "recurring catering",
    "concession",
    "co-branding",
)

# Structural markers (not sufficient alone — need a Brasaland service type)
CONTEXT_RFP_STRUCTURE_SIGNALS: Final[tuple[str, ...]] = (
    "request for proposal",
    "rfp reference",
    "scope of work",
    "proposal due",
)

# Brasaland service-type signals (CONTEXT §2.2 / §1 corporate RFP kinds)
CONTEXT_RFP_SERVICE_SIGNALS: Final[tuple[str, ...]] = (
    "catering",
    "concession",
    "co-brand",
    "co-branded",
    "co-branding",
    "food & beverage",
    "food and beverage",
    "institutional catering",
    "exclusivity",
    "menú estándar",
    "menu estándar",
    "menu estandar",
    "contrato por un año",
    "weekly catering",
    "catering semanal",
    "signature menu",
)

# Combined accept signals (service OR informal catering letter markers)
CONTEXT_RFP_ACCEPT_SIGNALS: Final[tuple[str, ...]] = CONTEXT_RFP_SERVICE_SIGNALS

# CONTEXT §4 seed #3 — franchise inquiry is NOT an RFP
CONTEXT_REJECT_SIGNALS: Final[tuple[str, ...]] = (
    "franquicia",
    "franquicias",
    "franchise",
    "franchises",
)

# Core fields whose absence (with franchise / non-RFP) drives discard
# CONTEXT: "franchise inquiry with no scope, budget, or deadline"
CONTEXT_CORE_FIELDS_FOR_ACCEPT: Final[tuple[str, ...]] = (
    "client_name",
    "scope_or_service",
    "deadline",
)

# --- CONTEXT §4 seed expectations ---
CONTEXT_SEED_EXPECTATIONS: Final[dict[str, dict]] = {
    "CONTEXT-brasaland-request-1.pdf": {
        "accept": True,
        "client_substr": "Sunset Bay",
        "departments": {"marketing", "operaciones", "procurement", "training"},
        "requires_ceo_approval": True,  # ~$60–75k > $50k
        "notes": "formal RFP; exclusivity + new signature menu → training",
    },
    "CONTEXT-brasaland-request-2.pdf": {
        "accept": True,
        "client_substr": "Andes Tech",
        "departments": {"marketing", "operaciones", "procurement"},
        "exclude_departments": {"training"},  # standard menu
        "requires_ceo_approval": False,
        "notes": "informal RFP; standard menu → no training",
    },
    "CONTEXT-brasaland-request-3.pdf": {
        "accept": False,
        "discard": True,
        "notes": "franchise inquiry; no scope/budget/deadline",
    },
}

# CONTEXT §5 / §2.1 — CEO threshold
CONTEXT_CEO_USD_THRESHOLD: Final[float] = 50_000.0
CONTEXT_CEO_NAME: Final[str] = "Mariana Restrepo"

# Ticket owner = Marketing / Camila (CONTEXT: Marketing is "Sales")
CONTEXT_TICKET_OWNER: Final[str] = "Camila Ospina"
CONTEXT_TICKET_OWNER_DEPARTMENT: Final[str] = "marketing"


def select_departments_from_content(text_cf: str, *, service_type: str | None = None) -> list[str]:
    """CONTEXT-aware department selection — never assume all four.

    Rules from CONTEXT §2.1 / §4:
    - ``marketing`` always owns the ticket for accepted B2B RFPs.
    - ``operaciones`` for catering / concession / co-brand operational delivery.
    - ``procurement`` when volume/catering/concession implies ingredient costing.
    - ``training`` only when a *new* recipe/signature/standard is required
      (not when the client asks for the existing standard menu).
    """
    depts: list[str] = ["marketing"]

    cateringish = any(
        tok in text_cf
        for tok in (
            "catering",
            "concession",
            "co-brand",
            "food & beverage",
            "food and beverage",
            "menú",
            "menu",
            "diner",
            "empleados",
            "employees",
            "resort",
        )
    ) or bool(service_type)
    if cateringish:
        depts.append("operaciones")
        depts.append("procurement")

    uses_standard_menu = any(
        tok in text_cf
        for tok in ("menú estándar", "menu estándar", "menu estandar", "standard menu")
    )
    needs_new_recipe_or_signature = any(
        tok in text_cf
        for tok in (
            "signature menu",
            "co-branded signature",
            "new recipe",
            "nuevo menú",
            "menú de autor",
            "menú exclusivo",
            "new signature",
        )
    )
    # CONTEXT §4: standard menu → training not required; signature/new menu → training
    if needs_new_recipe_or_signature and not (
        uses_standard_menu and not needs_new_recipe_or_signature
    ):
        depts.append("training")

    order = ["marketing", "operaciones", "procurement", "training"]
    return [d for d in order if d in depts]
