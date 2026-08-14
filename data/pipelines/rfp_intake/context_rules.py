"""CONTEXT-company.md Milestone 9 rules — source of truth for Brasaland RFP intake.

Department ids, owners, RFP format fields, and classification criteria are
derived from CONTEXT §2.1–§2.2 and §4. Do not invent alternate departments
(e.g. ``sales``, ``operations``, ``hr``) or generic SaaS RFP schemas.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

CONTEXT_COMPANY_MD: Final = Path(__file__).resolve().parents[3] / "CONTEXT-company.md"

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


def _heading_case(phrase: str) -> str:
    text = phrase.strip().rstrip(".")
    if not text:
        return text
    return text[0].upper() + text[1:]


def section_headings_from_contribution(department_id: str, contribution: str) -> tuple[str, ...]:
    """Turn the CONTEXT §2.1 contribution column into required section headings.

    These headings *are* the expected format of each department's proposal
    section — not a generic SaaS RFP outline.
    """
    text = contribution.strip()
    if department_id == "marketing":
        text = re.sub(r"\.?\s*Owns the ticket\.?\s*$", "", text, flags=re.I)
        parts = [p.strip() for p in text.split(",") if p.strip()]
    elif department_id == "operaciones":
        if ":" in text:
            text = text.split(":", 1)[1]
        parts = [p.strip() for p in text.split(",") if p.strip()]
    elif department_id == "training":
        parts = [p.strip() for p in text.split(",") if p.strip()]
        cleaned: list[str] = []
        for part in parts:
            part = re.sub(r"^If the request requires\s+", "", part, flags=re.I)
            part = re.sub(r"^(the|a|an)\s+", "", part, flags=re.I)
            cleaned.append(part.strip().rstrip("."))
        parts = cleaned
    else:
        parts = [p.strip() for p in text.split(",") if p.strip()]
    return tuple(_heading_case(p) for p in parts if p)


# Required ``##`` headings for each department's Part 2 section (CONTEXT §2.1).
CONTEXT_SECTION_REQUIRED_HEADINGS: Final[dict[str, tuple[str, ...]]] = {
    dept_id: section_headings_from_contribution(dept_id, contrib)
    for dept_id, contrib in CONTEXT_DEPARTMENT_CONTRIBUTIONS.items()
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
        "location_substr": "Florida",
        "departments": {"marketing", "operaciones", "procurement", "training"},
        "requires_ceo_approval": True,  # ~$60–75k > $50k
        "contacts": {
            "marketing": "Camila Ospina",
            "operaciones": "Felipe Guerrero",
            "procurement": "Lucía Fernández",
            "training": "Jake Morrison",
            "ceo": "Mariana Restrepo",
        },
        # Substrings that must appear in that department's key_aspects (grounded in PDF/CONTEXT)
        "aspect_signals": {
            "marketing": ("Sunset Bay", "exclusiv"),
            "operaciones": ("Sunset Bay", "10 business days"),
            "procurement": ("60,000", "75,000"),
            "training": ("signature", "certif"),
        },
        "notes": "formal RFP; exclusivity + new signature menu → training",
    },
    "CONTEXT-brasaland-request-2.pdf": {
        "accept": True,
        "client_substr": "Andes Tech",
        "location_substr": "Medellín",
        "departments": {"marketing", "operaciones", "procurement"},
        "exclude_departments": {"training"},  # standard menu
        "requires_ceo_approval": False,
        "contacts": {
            "marketing": "Camila Ospina",
            "operaciones": "Felipe Guerrero",
            "procurement": "Lucía Fernández",
        },
        "aspect_signals": {
            "marketing": ("Andes Tech",),
            "operaciones": ("Andes Tech", "Medellín", "220"),
            "procurement": ("open_questions", "not fully stated"),
        },
        "notes": "informal RFP; standard menu → no training",
    },
    "CONTEXT-brasaland-request-3.pdf": {
        "accept": False,
        "discard": True,
        "departments": set(),
        "contacts": {},
        "aspect_signals": {},
        "notes": "franchise inquiry; no scope/budget/deadline",
    },
}

# CONTEXT §5 / §2.1 — CEO threshold
CONTEXT_CEO_USD_THRESHOLD: Final[float] = 50_000.0
CONTEXT_CEO_NAME: Final[str] = "Mariana Restrepo"

# CONTEXT §5 — verbatim guidelines the compliance evaluator must enforce
CONTEXT_SECTION_5_TITLE: Final = (
    "Business Constraints (Guidelines for the Compliance Evaluator)"
)
CONTEXT_SECTION_5_GUIDELINES: Final[tuple[str, ...]] = (
    "Every price must be expressed in both COP and USD.",
    (
        "Every proposal must mention, at least once, the brand's three pillars: "
        "consistent quality, warm experience, speed of service."
    ),
    "No section may promise setup/delivery times shorter than 10 business days.",
    "No proposal may mention competitors by name.",
    "Every proposal must include an offer validity period (30 days from issuance).",
    (
        "Estimated contracts above $50,000 USD/year require an additional CEO "
        "approval before the final document is generated."
    ),
)

CONTEXT_BRAND_PILLARS: Final[tuple[str, ...]] = (
    "consistent quality",
    "warm experience",
    "speed of service",
)
CONTEXT_MIN_SETUP_BUSINESS_DAYS: Final[int] = 10
CONTEXT_OFFER_VALIDITY_DAYS: Final[int] = 30
CONTEXT_OFFER_VALIDITY_PHRASE: Final = "30 days from issuance"

# Colombia + Florida grilled / QSR names a Brasaland proposal must not cite.
# Not a generic SaaS vendor list (Salesforce, Oracle, …).
CONTEXT_FORBIDDEN_COMPETITORS: Final[tuple[str, ...]] = (
    "el corral",
    "frisby",
    "presto",
    "mcdonald",
    "burger king",
    "kfc",
    "wendy",
    "outback",
    "texas roadhouse",
    "chipotle",
    "subway",
)

# Ticket owner = Marketing / Camila (CONTEXT: Marketing is "Sales")
CONTEXT_TICKET_OWNER: Final[str] = "Camila Ospina"
CONTEXT_TICKET_OWNER_DEPARTMENT: Final[str] = "marketing"


def read_context_company_md() -> str:
    """Load CONTEXT-company.md from the repo root."""
    return CONTEXT_COMPANY_MD.read_text(encoding="utf-8")


def parse_context_department_table(text: str | None = None) -> list[dict[str, str]]:
    """Parse CONTEXT §2.1 markdown table rows (id, label, owner, contribution)."""
    source = text if text is not None else read_context_company_md()
    start = source.find("### 2.1")
    end = source.find("### 2.2")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("CONTEXT-company.md is missing section 2.1 / 2.2 markers")
    block = source[start:end]
    rows: list[dict[str, str]] = []
    pattern = re.compile(
        r"\|\s*`(?P<id>[a-z_]+)`\s*\|\s*(?P<label>[^|]+?)\s*\|\s*"
        r"(?P<owner>[^|]+?)\s*\|\s*(?P<contrib>[^|]+?)\s*\|"
    )
    for match in pattern.finditer(block):
        dept_id = match.group("id").strip()
        if dept_id == "department_id":
            continue
        rows.append(
            {
                "department_id": dept_id,
                "label": match.group("label").strip(),
                "owner": match.group("owner").strip(),
                "contribution": match.group("contrib").strip(),
            }
        )
    return rows


def parse_context_section_5_bullets(text: str | None = None) -> tuple[str, ...]:
    """Extract the CONTEXT §5 guideline bullets (compliance evaluator source)."""
    source = text if text is not None else read_context_company_md()
    start = source.find("## 5. Business Constraints")
    end = source.find("## 6.")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("CONTEXT-company.md is missing section 5 / 6 markers")
    block = source[start:end]
    bullets = [m.strip() for m in re.findall(r"^-\s+(.+)$", block, flags=re.M)]
    return tuple(bullets)


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
