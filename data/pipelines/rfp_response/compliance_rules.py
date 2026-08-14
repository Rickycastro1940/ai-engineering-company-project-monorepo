"""CONTEXT-company.md §5 guidelines + §2.1 section format for Part 2.

These constants are the single source of truth for:
- ``evaluators.evaluate_compliance`` (guidelines)
- ``evaluators.evaluate_relevance`` (expected section headings)
- ``agents`` (generator section shape)

Read CONTEXT §2.1 and §5 before changing generator or evaluator behavior.
A generic SaaS RFP schema is not accepted.
"""

from __future__ import annotations

from typing import Final

from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_BRAND_PILLARS,
    CONTEXT_CEO_NAME,
    CONTEXT_CEO_USD_THRESHOLD,
    CONTEXT_DEPARTMENT_CONTRIBUTIONS,
    CONTEXT_DEPARTMENT_OWNERS,
    CONTEXT_FORBIDDEN_COMPETITORS,
    CONTEXT_MIN_SETUP_BUSINESS_DAYS,
    CONTEXT_OFFER_VALIDITY_DAYS,
    CONTEXT_OFFER_VALIDITY_PHRASE,
    CONTEXT_SECTION_5_GUIDELINES,
    CONTEXT_SECTION_REQUIRED_HEADINGS,
)

# --- CONTEXT-company.md §5 (verbatim bullets) --------------------------------
# 1. Every price must be expressed in both COP and USD.
# 2. Every proposal must mention, at least once, the brand's three pillars:
#    consistent quality, warm experience, speed of service.
# 3. No section may promise setup/delivery times shorter than 10 business days.
# 4. No proposal may mention competitors by name.
# 5. Every proposal must include an offer validity period (30 days from issuance).
# 6. Estimated contracts above $50,000 USD/year require additional CEO approval
#    before the final document is generated (Part 3; Part 2 flags).

CONTEXT_SECTION_5_RULES: Final[tuple[dict[str, str], ...]] = (
    {"id": "dual_currency", "guideline": CONTEXT_SECTION_5_GUIDELINES[0]},
    {"id": "brand_pillars", "guideline": CONTEXT_SECTION_5_GUIDELINES[1]},
    {"id": "min_setup_business_days", "guideline": CONTEXT_SECTION_5_GUIDELINES[2]},
    {"id": "no_competitors", "guideline": CONTEXT_SECTION_5_GUIDELINES[3]},
    {"id": "offer_validity", "guideline": CONTEXT_SECTION_5_GUIDELINES[4]},
    {"id": "ceo_threshold", "guideline": CONTEXT_SECTION_5_GUIDELINES[5]},
)

# Brand pillars — every proposal must mention each at least once (CONTEXT §5)
BRAND_PILLARS: Final[tuple[str, ...]] = CONTEXT_BRAND_PILLARS

# Offer validity (CONTEXT §5)
OFFER_VALIDITY_DAYS: Final[int] = CONTEXT_OFFER_VALIDITY_DAYS
OFFER_VALIDITY_PHRASE: Final = CONTEXT_OFFER_VALIDITY_PHRASE

# Setup / delivery SLA (CONTEXT §5)
MIN_SETUP_BUSINESS_DAYS: Final[int] = CONTEXT_MIN_SETUP_BUSINESS_DAYS

# CEO threshold — synced with Part 1 CONTEXT seed (Part 2 flags; Part 3 enforces)
CEO_USD_THRESHOLD: Final[float] = CONTEXT_CEO_USD_THRESHOLD
CEO_NAME: Final = CONTEXT_CEO_NAME

# Competitors — never mention by name (CONTEXT §5). Colombia + Florida grill/QSR.
FORBIDDEN_COMPETITOR_NAMES: Final[tuple[str, ...]] = CONTEXT_FORBIDDEN_COMPETITORS

# Expected ``##`` headings per department (CONTEXT §2.1 contribution column)
SECTION_REQUIRED_HEADINGS: Final[dict[str, tuple[str, ...]]] = dict(
    CONTEXT_SECTION_REQUIRED_HEADINGS
)
SECTION_CONTRIBUTIONS: Final[dict[str, str]] = dict(CONTEXT_DEPARTMENT_CONTRIBUTIONS)
SECTION_OWNERS: Final[dict[str, str]] = dict(CONTEXT_DEPARTMENT_OWNERS)

# Generator–evaluator loop (CONTEXT §3 KPI: average iterations < 2)
MAX_SECTION_ITERATIONS: Final[int] = 2

# Evaluation dimensions persisted on DepartmentSection.evaluation_results
EVAL_DIMENSIONS: Final[tuple[str, ...]] = (
    "readability",
    "relevance",
    "compliance",
)
