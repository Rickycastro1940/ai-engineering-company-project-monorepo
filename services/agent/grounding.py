"""Grounding helpers — LangGraph migration must not weaken RAG answer fidelity.

Answers must stay consistent with ``CONTEXT-company.md`` and
``docs/company-knowledge-base/``. A perfect trace that ignores company policy
is still a failure.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_COMPANY = REPO_ROOT / "CONTEXT-company.md"
KB_DIR = REPO_ROOT / "docs" / "company-knowledge-base"

# Canonical Brasaland KB source stems (see CONTEXT-company.md).
ALLOWED_SOURCE_DOCUMENTS = {
    "supplier-ordering",
    "waste-protocol",
    "loyalty-program",
    "menu-allergens",
}

# Affirmative forbidden claims (CONTEXT-company.md allergen constraint).
# Match phrases that assert safety, not ones that refuse to guarantee it.
FORBIDDEN_ALLERGEN_CLAIM_PATTERNS = (
    r"\bthere is zero risk\b",
    r"\bzero risk of\b",
    r"\b100%\s*safe\b",
    r"\bcompletely safe\b",
    r"\bzero cross-contamination risk\b",
    r"\bno risk of (?:cross[- ]contamination|allergens?)\b",
)


def load_context_company() -> str:
    return CONTEXT_COMPANY.read_text(encoding="utf-8")


def load_kb_document(stem: str) -> str:
    path = KB_DIR / f"brasaland-{stem}.en.md"
    if not path.exists():
        raise FileNotFoundError(f"Missing KB document: {path}")
    return path.read_text(encoding="utf-8")


def supplier_ordering_facts() -> dict[str, str]:
    """Known grounding entities for the minimum protein stock policy question."""
    context = load_context_company()
    kb = load_kb_document("supplier-ordering")
    assert "Lucía Fernández" in context
    assert "500 USD" in context
    assert "3 days" in kb
    assert "Lucía Fernández" in kb
    return {
        "person": "Lucía Fernández",
        "threshold": "500 USD",
        "stock_rule": "3 days",
        "source_document": "supplier-ordering",
        "surcharge": "8%",
    }


def assert_sources_from_company_kb(sources: list[Any]) -> None:
    """Retrieved source_document values must map to CONTEXT knowledge-base files."""
    assert sources, "grounded runs must retrieve at least one company document"
    for source in sources:
        stem = str(source or "").replace(".en.md", "").replace("brasaland-", "")
        assert stem in ALLOWED_SOURCE_DOCUMENTS, (
            f"Retrieved source '{source}' is not in the Brasaland knowledge base "
            f"({sorted(ALLOWED_SOURCE_DOCUMENTS)})"
        )


def assert_answer_grounded_in_supplier_policy(answer: str) -> None:
    """Acceptance gate for the protein stock / emergency-order policy question."""
    facts = supplier_ordering_facts()
    text = answer or ""
    missing = [label for label, value in (
        ("stock_rule", facts["stock_rule"]),
        ("person", facts["person"]),
        ("threshold", facts["threshold"]),
    ) if value not in text and value.replace("á", "a") not in text]
    assert not missing, (
        f"Answer is not grounded in CONTEXT-company.md / supplier-ordering. "
        f"Missing facts: {missing}. Answer={text!r}"
    )


def assert_allergen_answer_follows_context_policy(answer: str) -> None:
    """Never affirm zero allergen risk — CONTEXT-company.md constraint."""
    text = answer or ""
    for pattern in FORBIDDEN_ALLERGEN_CLAIM_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        assert match is None, (
            f"Answer violates CONTEXT allergen policy (matched {pattern!r}): {answer!r}"
        )


def assert_trace_grounded(trace: dict[str, Any], *, require_generate: bool = True) -> None:
    """Validate a saved agent trace for KB grounding (acceptance gate)."""
    sources = []
    for step in trace.get("steps") or []:
        if step.get("node_name") == "retrieve":
            sources = list((step.get("output") or {}).get("sources") or [])
    if require_generate:
        assert "generate" in (trace.get("node_order") or [])
        assert_sources_from_company_kb(sources)
        assert_answer_grounded_in_supplier_policy(trace.get("answer") or "")
        assert_allergen_answer_follows_context_policy(trace.get("answer") or "")
