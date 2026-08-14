"""Optional Brasaland knowledge-base grounding for Part 2 generators.

Not a Part 2 requirement. When the semantic collection is reachable, generators
reuse ``data.pipelines.rag.retrieve`` (same path as ``POST /knowledge/query``).
If Qdrant/embeddings are unavailable, fall back to the source markdown in
``docs/company-knowledge-base/`` so drafts still use real policy language.

Disable with ``RFP_KB_GROUNDING=0``. Failures never block drafting.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
KB_DIR = REPO_ROOT / "docs" / "company-knowledge-base"

# Source docs that feed collection brasaland_kb (do not name the collection in drafts)
_DEPT_DOCS: Final[dict[str, tuple[str, ...]]] = {
    DEPARTMENT_MARKETING: ("brasaland-loyalty-program.en.md",),
    DEPARTMENT_OPERACIONES: ("brasaland-waste-protocol.en.md",),
    DEPARTMENT_PROCUREMENT: ("brasaland-supplier-ordering.en.md",),
    DEPARTMENT_TRAINING: ("brasaland-menu-allergens.en.md",),
}

_DEPT_QUERIES: Final[dict[str, tuple[str, ...]]] = {
    DEPARTMENT_MARKETING: (
        "Brasa Points loyalty program brand language Colombia Florida",
        "Gold tier seasonal menu early access points redemption",
    ),
    DEPARTMENT_OPERACIONES: (
        "waste control protocol kitchen logging Felipe Guerrero escalation",
        "operational waste target protein inventory shrinkage",
    ),
    DEPARTMENT_PROCUREMENT: (
        "supplier ordering lead times emergency order Lucía Fernández 500 USD",
        "protein delivery vegetables beverages imported sauces business days",
    ),
    DEPARTMENT_TRAINING: (
        "menu allergen protocol never guarantee zero risk gluten-free",
        "kitchen allergy utensils new staff training first two weeks",
    ),
}

_FORBIDDEN_IN_DRAFT: Final[tuple[str, ...]] = (
    "brasaland_kb",
    "/knowledge/query",
    "qdrant",
)

NO_CONTEXT = "There is not enough information available."

_SETUP_TOO_SHORT = re.compile(
    r"(?:setup|delivery|deliver|instalaci[oó]n|lead\s*time|timeline)"
    r"[^\n.]{0,40}?"
    r"(?:in|within|under|en|of)?\s*"
    r"([1-9])\s*(?:business\s*)?days?",
    re.I,
)


def _safe_for_proposal(text: str) -> bool:
    """Drop snippets that would fail CONTEXT §5 setup/delivery (<10 business days)."""
    for match in _SETUP_TOO_SHORT.finditer(text):
        if int(match.group(1)) < 10:
            return False
    return True


@dataclass(frozen=True)
class KbSnippet:
    source_document: str
    text: str
    via: str  # "retrieve" | "local_docs"


def kb_grounding_enabled() -> bool:
    flag = os.getenv("RFP_KB_GROUNDING", "1").strip().lower()
    return flag not in {"0", "false", "off", "no"}


def _clean_snippet(text: str) -> str:
    compact = " ".join((text or "").split())
    for banned in _FORBIDDEN_IN_DRAFT:
        compact = re.sub(re.escape(banned), "", compact, flags=re.I)
    return compact.strip()


def _paragraphs_from_markdown(path: Path) -> list[str]:
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8")
    parts = [p.strip() for p in re.split(r"\n\s*\n", raw) if len(p.strip()) > 40]
    return parts


def _score(text: str, query: str) -> int:
    hay = text.casefold()
    return sum(1 for token in query.casefold().split() if len(token) > 3 and token in hay)


def _from_local_docs(department_id: str, queries: tuple[str, ...]) -> list[KbSnippet]:
    docs = _DEPT_DOCS.get(department_id) or ()
    joined_q = " ".join(queries)
    scored: list[tuple[int, str, str]] = []
    for name in docs:
        path = KB_DIR / name
        for para in _paragraphs_from_markdown(path):
            cleaned = _clean_snippet(para)
            if not cleaned or NO_CONTEXT in cleaned:
                continue
            if not _safe_for_proposal(cleaned):
                continue
            scored.append((_score(cleaned, joined_q), name, cleaned))
    scored.sort(key=lambda row: row[0], reverse=True)
    out: list[KbSnippet] = []
    seen: set[str] = set()
    for score, name, text in scored:
        if score <= 0:
            continue
        key = text[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(KbSnippet(source_document=name, text=text[:520], via="local_docs"))
        if len(out) >= 3:
            break
    return out


def _from_retrieve(queries: tuple[str, ...]) -> list[KbSnippet]:
    try:
        from data.pipelines.rag import retrieve
    except Exception:
        return []
    out: list[KbSnippet] = []
    seen: set[str] = set()
    for question in queries:
        try:
            hits = retrieve(question, k=3)
        except Exception:
            continue
        for hit in hits or []:
            if not isinstance(hit, dict):
                continue
            text = _clean_snippet(str(hit.get("text") or ""))
            if not text or NO_CONTEXT in text:
                continue
            if not _safe_for_proposal(text):
                continue
            key = text[:80]
            if key in seen:
                continue
            seen.add(key)
            source = str(hit.get("source_document") or "knowledge-base")
            if any(b in source.casefold() for b in _FORBIDDEN_IN_DRAFT):
                source = "company-knowledge-base"
            out.append(KbSnippet(source_document=source, text=text[:520], via="retrieve"))
            if len(out) >= 3:
                return out
    return out


def lookup_department_knowledge(
    department_id: str,
    *,
    extra_query: str = "",
) -> list[KbSnippet]:
    """Return up to 3 policy/brand snippets. Empty list if disabled or unavailable."""
    if not kb_grounding_enabled():
        return []
    base = list(_DEPT_QUERIES.get(department_id) or ())
    extra = extra_query.strip()
    if extra:
        base.append(extra[:240])
    queries = tuple(base) or (department_id,)
    snippets: list[KbSnippet] = []
    try:
        snippets = _from_retrieve(queries)
    except Exception:
        snippets = []
    if snippets:
        return snippets
    try:
        return _from_local_docs(department_id, queries)
    except Exception:
        return []


def format_kb_section(snippets: list[KbSnippet]) -> list[str]:
    """Markdown block for the pricing-proposal draft. Empty if no snippets."""
    if not snippets:
        return []
    lines = [
        "## Company knowledge (policies and brand language)",
        "Optional grounding from Brasaland's company knowledge base. Figures and "
        "currency labels (USD $ / COP $) are copied as written — never converted. "
        "Ingredient replenishment windows are not client-event setup times "
        "(event setup remains at least 10 business days).",
    ]
    for snip in snippets:
        lines.append(f"- From {snip.source_document}: {snip.text}")
    lines.append("")
    return lines
