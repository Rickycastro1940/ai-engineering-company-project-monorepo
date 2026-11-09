"""Compliance Agent — check the application against the knowledge base.

Standards come from `docs/company-knowledge-base/` through the same retrieval
path as `POST /knowledge/query`. A rule is applied only when a retrieved chunk
states it. Empty retrieval does not invent an INVIMA, FDA, or 8% finding.
"""

from __future__ import annotations

import re

from agents.supplier_approval.supplier_agent import FOOD_CATEGORIES
from agents.tools.knowledge import query_standards

_ORDERING_QUESTION = "emergency protein order 8% surcharge over list price"
_ALLERGEN_QUESTION = "Brasaland allergen disclosure INVIMA in Colombia FDA in the United States"
_CROSS_QUESTION = '"Zero cross-contamination risk" is never guaranteed'
_GLUTEN_QUESTION = "There is no certified gluten-free version of the BBQ Ribs"

_GUARANTEE = re.compile(
    r"(?:"
    r"(?:guarantee[sd]?|100\s*%|certified|promise[sd]?)\s+[^.\n]{0,48}zero\s+cross"
    r"|zero\s+cross[-\s]?contamination[^.\n]{0,48}(?:guarantee|guaranteed|100\s*%|certified|promise)"
    r")",
    re.IGNORECASE,
)
_GLUTEN_RIBS = re.compile(
    r"(?:gluten[-\s]?free[^.\n]{0,48}(?:bbq\s+ribs|ribs)|(?:bbq\s+ribs|ribs)[^.\n]{0,48}gluten[-\s]?free)",
    re.IGNORECASE,
)


def _cite(sources: list[dict]) -> list[dict]:
    cited: list[dict] = []
    seen: set[tuple] = set()
    for source in sources:
        key = (
            source.get("source_document"),
            source.get("section"),
            source.get("chunk_index"),
        )
        if key in seen:
            continue
        seen.add(key)
        cited.append(
            {
                "source_document": source.get("source_document"),
                "section": source.get("section"),
                "text": source.get("text") or "",
                "score": source.get("score"),
                "chunk_index": source.get("chunk_index"),
                "language": source.get("language") or "en",
            }
        )
    return cited


def _check(check_id: str, status: str, detail: str) -> dict:
    return {"id": check_id, "status": status, "detail": detail}


def run(state: dict) -> dict:
    parsed = state["parsed"]
    review_text = parsed.get("review_text") or ""
    questions = [_ORDERING_QUESTION, _ALLERGEN_QUESTION]
    if re.search(r"cross[-\s]?contamination", review_text, re.IGNORECASE):
        questions.append(_CROSS_QUESTION)
    if re.search(r"gluten[-\s]?free", review_text, re.IGNORECASE):
        questions.append(_GLUTEN_QUESTION)

    answers = []
    collected: list[dict] = []
    for question in questions:
        result = query_standards(question, k=3)
        answers.append({"question": question, "answer": result.get("answer") or ""})
        collected.extend(result.get("sources") or [])
    citations = _cite(collected)
    blob = "\n".join(item["text"] for item in citations).lower()
    checks: list[dict] = []

    if not citations:
        checks.append(
            _check(
                "knowledge_base",
                "condition",
                "The knowledge base did not return a standard to cite. "
                "Do not approve until a person reads the supplier file against the written standards.",
            )
        )
    else:
        checks.append(
            _check(
                "knowledge_base",
                "pass",
                "Compliance cited the Brasaland knowledge base.",
            )
        )

    categories = set(parsed.get("categories") or [])
    if "proteins" in categories and "8%" in blob:
        surcharge = parsed.get("emergency_surcharge_pct")
        if surcharge is None:
            checks.append(
                _check(
                    "emergency_surcharge",
                    "condition",
                    "The ordering procedure carries an 8% surcharge on emergency protein orders. "
                    "The application does not state that percentage.",
                )
            )
        elif abs(float(surcharge) - 8) > 0.001:
            checks.append(
                _check(
                    "emergency_surcharge",
                    "condition",
                    "Emergency protein orders carry an 8% surcharge over list price. "
                    f"The application states {surcharge:g}%.",
                )
            )
        else:
            checks.append(
                _check(
                    "emergency_surcharge",
                    "pass",
                    "Emergency protein surcharge matches the 8% rule in the ordering procedure.",
                )
            )

    food = bool(categories & set(FOOD_CATEGORIES))
    if food and "invima" in blob and "fda" in blob:
        country = parsed.get("country")
        notes = review_text.lower()
        if country == "Colombia" and "invima" not in notes:
            checks.append(
                _check(
                    "health_authority",
                    "condition",
                    "Allergen disclosure in Colombia follows INVIMA. "
                    "The application does not cite an INVIMA registration.",
                )
            )
        elif country == "United States" and "fda" not in notes:
            checks.append(
                _check(
                    "health_authority",
                    "condition",
                    "Allergen disclosure in the United States follows the FDA. "
                    "The application does not cite an FDA registration.",
                )
            )
        elif country in {"Colombia", "United States"}:
            authority = "INVIMA" if country == "Colombia" else "FDA"
            checks.append(
                _check(
                    "health_authority",
                    "pass",
                    f"The application cites {authority}, which matches the allergen guide for that market.",
                )
            )

    if "zero cross-contamination risk" in blob or "never guaranteed" in blob:
        if _GUARANTEE.search(review_text):
            checks.append(
                _check(
                    "cross_contamination",
                    "fail",
                    'The allergen guide says "Zero cross-contamination risk" is never guaranteed. '
                    "The application promises that guarantee.",
                )
            )
        elif re.search(r"cross[-\s]?contamination", review_text, re.IGNORECASE):
            checks.append(
                _check(
                    "cross_contamination",
                    "pass",
                    "The application mentions cross-contamination and does not promise zero risk.",
                )
            )

    if "no certified gluten-free version of the bbq ribs" in blob and _GLUTEN_RIBS.search(review_text):
        checks.append(
            _check(
                "gluten_free_ribs",
                "fail",
                "There is no certified gluten-free version of the BBQ Ribs. "
                "The application claims a gluten-free rib product.",
            )
        )

    state["compliance"] = {"checks": checks, "sources": citations, "queries": answers}
    state["trace"].append("compliance")
    return state
