"""CONTEXT-company.md §5 — compliance guidelines for Part 2 evaluators.

Read before changing generator or evaluator behavior.
"""

from __future__ import annotations

from typing import Final

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

# CEO threshold (Part 3 gate; Part 2 may flag)
CEO_USD_THRESHOLD: Final[float] = 50_000.0
CEO_NAME: Final = "Mariana Restrepo"

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
