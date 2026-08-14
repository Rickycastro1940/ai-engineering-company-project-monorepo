"""CONTEXT-company.md §5 — compliance guidelines for Part 2 evaluators.

These constants are the single source of truth for `evaluators.evaluate_compliance`.
Read CONTEXT §5 before changing generator or evaluator behavior.
"""

from __future__ import annotations

from typing import Final

from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_CEO_NAME,
    CONTEXT_CEO_USD_THRESHOLD,
)

# --- CONTEXT-company.md §5 (verbatim intent) ---------------------------------
# - Every price must be expressed in both COP and USD.
# - Every proposal must mention, at least once, the brand's three pillars:
#   consistent quality, warm experience, speed of service.
# - No section may promise setup/delivery times shorter than 10 business days.
# - No proposal may mention competitors by name.
# - Every proposal must include an offer validity period (30 days from issuance).
# - Estimated contracts above $50,000 USD/year require additional CEO approval
#   before the final document is generated (Part 3; Part 2 flags).

CONTEXT_SECTION_5_RULES: Final[tuple[dict[str, str], ...]] = (
    {
        "id": "dual_currency",
        "guideline": "Every price must be expressed in both COP and USD.",
    },
    {
        "id": "brand_pillars",
        "guideline": (
            "Every proposal must mention, at least once, the brand's three pillars: "
            "consistent quality, warm experience, speed of service."
        ),
    },
    {
        "id": "min_setup_business_days",
        "guideline": (
            "No section may promise setup/delivery times shorter than 10 business days."
        ),
    },
    {
        "id": "no_competitors",
        "guideline": "No proposal may mention competitors by name.",
    },
    {
        "id": "offer_validity",
        "guideline": (
            "Every proposal must include an offer validity period (30 days from issuance)."
        ),
    },
    {
        "id": "ceo_threshold",
        "guideline": (
            "Estimated contracts above $50,000 USD/year require an additional CEO "
            "approval before the final document is generated."
        ),
    },
)

# Brand pillars — every proposal must mention each at least once (CONTEXT §5)
BRAND_PILLARS: Final[tuple[str, ...]] = (
    "consistent quality",
    "warm experience",
    "speed of service",
)

# Offer validity (CONTEXT §5)
OFFER_VALIDITY_DAYS: Final[int] = 30
OFFER_VALIDITY_PHRASE: Final = "30 days from issuance"

# Setup / delivery SLA (CONTEXT §5)
MIN_SETUP_BUSINESS_DAYS: Final[int] = 10

# CEO threshold — synced with Part 1 CONTEXT seed (Part 2 flags; Part 3 enforces)
CEO_USD_THRESHOLD: Final[float] = CONTEXT_CEO_USD_THRESHOLD
CEO_NAME: Final = CONTEXT_CEO_NAME

# Competitors — never mention by name (CONTEXT §5). Keep short, high-signal list.
FORBIDDEN_COMPETITOR_NAMES: Final[tuple[str, ...]] = (
    "mcdonald",
    "burger king",
    "kfc",
    "wendy",
    "subway",
    "chipotle",
    "outback",
    "texas roadhouse",
    "el corral",
    "frisby",
    "presto",
)

# Generator–evaluator loop (CONTEXT §3 KPI: average iterations < 2)
MAX_SECTION_ITERATIONS: Final[int] = 2

# Evaluation dimensions persisted on DepartmentSection.evaluation_results
EVAL_DIMENSIONS: Final[tuple[str, ...]] = (
    "readability",
    "relevance",
    "compliance",
)
