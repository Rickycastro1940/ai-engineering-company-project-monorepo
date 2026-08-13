"""RFP intake pipeline — convert, classify, route departments, synthesize.

Business logic lives here (not in HTTP routers). Departments / discard rules
come from CONTEXT-company.md Milestone 9.

Flow: convert → classifier_agent (first agent) → department workers → synthesize.
Invalid RFPs stop after the classifier with status=discarded (never silent).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from markitdown import MarkItDown

from data.pipelines.rfp_intake.classifier import (
    ClassifierDecision,
    assert_no_silent_discard,
    classifier_agent,
    classify_document,
)
from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_IDS,
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_OWNERS,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
    MIN_MARKDOWN_CHARS,
    STATUS_DISCARDED,
    STATUS_FAILED,
    STATUS_INTAKE_COMPLETE,
)

logger = logging.getLogger(__name__)

# Back-compat name used in older call sites / docs
ClassifyResult = ClassifierDecision

__all__ = [
    "ClassifyResult",
    "ClassifierDecision",
    "IntakeResult",
    "build_department_excerpt",
    "classifier_agent",
    "classify_document",
    "compute_readability_scores",
    "convert_document_to_markdown",
    "convert_pdf_to_markdown",
    "department_worker",
    "run_intake_from_bytes",
    "run_intake_pipeline",
    "synthesize_intake",
]


@dataclass
class IntakeResult:
    status: str
    metadata: dict[str, Any]
    departments_needed: list[str]
    sections: dict[str, list[str]]
    unmapped_topics: list[str]
    conflicts: list[dict[str, Any]]
    intake_summary: str
    requires_ceo_approval: bool
    markdown_text: str
    readability_scores: dict[str, float]
    discard_reason: str | None = None
    discard_rule_id: str | None = None
    error_message: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)


def convert_document_to_markdown(path: Path) -> str:
    """Convert PDF/DOCX/etc. via markitdown; plain text/markdown read directly."""
    if not path.is_file():
        raise FileNotFoundError(f"Document not found: {path}")
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt", ".markdown"}:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if len(text) < MIN_MARKDOWN_CHARS:
            raise ValueError("Document text too short")
        return text
    result = MarkItDown().convert(str(path))
    text = (getattr(result, "text_content", None) or "").strip()
    if len(text) < MIN_MARKDOWN_CHARS:
        raise ValueError("PDF conversion produced empty or too-short text")
    return text


def convert_pdf_to_markdown(pdf_path: Path) -> str:
    """Back-compat alias."""
    return convert_document_to_markdown(pdf_path)


def compute_readability_scores(markdown_text: str) -> dict[str, float]:
    words = re.findall(r"\b\w+\b", markdown_text or "")
    if len(words) < 100:
        return {}
    try:
        import nltk
        from readability import Readability

        nltk.download("punkt_tab", quiet=True)
        analyzer = Readability(markdown_text)
        scores: dict[str, float] = {}
        for name, getter in (
            ("flesch_reading_ease", analyzer.flesch),
            ("flesch_kincaid_grade", analyzer.flesch_kincaid),
            ("gunning_fog", analyzer.gunning_fog),
        ):
            try:
                raw = getter()
                value = float(getattr(raw, "score", raw))
                scores[name] = value
            except Exception:  # noqa: BLE001
                continue
        return scores
    except Exception as exc:  # noqa: BLE001
        logger.debug("readability skipped: %s", exc)
        return {}


def build_department_excerpt(markdown_text: str, department_id: str, *, max_chars: int = 2000) -> str:
    """Return a dept-relevant slice of the RFP markdown (not the full document)."""
    text = markdown_text or ""
    keywords = {
        DEPARTMENT_MARKETING: (
            "brand",
            "exclusiv",
            "co-brand",
            "marketing",
            "validity",
            "marca",
        ),
        DEPARTMENT_OPERACIONES: (
            "kitchen",
            "staff",
            "setup",
            "operat",
            "logíst",
            "logist",
            "capacity",
            "event",
        ),
        DEPARTMENT_PROCUREMENT: (
            "cost",
            "budget",
            "supplier",
            "ingredient",
            "volume",
            "USD",
            "COP",
            "precio",
        ),
        DEPARTMENT_TRAINING: (
            "recipe",
            "signature menu",
            "training",
            "standard",
            "certif",
            "menú de autor",
            "nuevo",
        ),
    }.get(department_id, ())
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    scored: list[tuple[int, str]] = []
    for para in paragraphs:
        low = para.casefold()
        score = sum(1 for k in keywords if k.casefold() in low)
        if score:
            scored.append((score, para))
    scored.sort(key=lambda item: (-item[0], -len(item[1])))
    if scored:
        joined = "\n\n".join(p for _, p in scored[:4])
        return joined[:max_chars]
    return text[:max_chars]


def department_worker(
    department_id: str,
    metadata: dict[str, Any],
    excerpt: str,
) -> list[str]:
    """Produce key_aspects for one department (Part 1 worker)."""
    client = metadata.get("client_name") or "the client"
    templates: dict[str, list[str]] = {
        DEPARTMENT_MARKETING: [
            f"Brand / exclusivity terms for {client}",
            "Offer validity period (30 days from issuance)",
            "Co-branding and CRM coordination owned by Camila Ospina",
        ],
        DEPARTMENT_OPERACIONES: [
            f"Operational feasibility and staffing for {client}",
            "Setup/delivery timeline must be ≥10 business days",
            "Kitchen capacity and service cadence",
        ],
        DEPARTMENT_PROCUREMENT: [
            "Ingredient cost estimate by volume (USD $ and COP $ as written)",
            "Supplier lead times for contract volume",
            "Never invent prices absent from the RFP",
        ],
        DEPARTMENT_TRAINING: [
            "New recipe / signature-menu development time",
            "Certification and quality standards rollout",
            "Training plan across locations",
        ],
    }
    aspects = list(templates.get(department_id, [f"Review {department_id} requirements"]))
    # Prefer excerpt-grounded notes when keywords present
    if excerpt and len(excerpt) > 80:
        aspects.append(f"Excerpt focus: {excerpt[:160].replace(chr(10), ' ')}…")
    return aspects[:5]


def synthesize_intake(
    metadata: dict[str, Any],
    departments_needed: list[str],
    sections: dict[str, list[str]],
) -> tuple[str, list[dict[str, Any]]]:
    lines = [
        f"Client: {metadata.get('client_name') or 'Unknown'}",
        f"Location: {metadata.get('location') or 'Unknown'}",
        f"Service: {metadata.get('service_type') or metadata.get('scope') or 'Unspecified'}",
        f"Deadline: {metadata.get('deadline') or 'Not specified'}",
        f"Departments: {', '.join(departments_needed) or 'none'}",
    ]
    for dept in departments_needed:
        owner = DEPARTMENT_OWNERS.get(dept, dept)
        aspects = sections.get(dept) or []
        lines.append(f"- {dept} ({owner}): " + "; ".join(aspects[:2]))
    return "\n".join(lines), []


def run_intake_pipeline(*, pdf_path: Path, title: str | None = None) -> IntakeResult:
    """Full Part 1 pipeline: convert → classifier_agent → workers → synthesize.

    The classifier is the first agent after convert. Invalid documents stop here
    with ``status=discarded`` and an explicit discard_reason (never silent).
    """
    trace: list[dict[str, Any]] = []

    def _event(node: str, **payload: Any) -> None:
        trace.append({"node": node, "payload": payload})

    try:
        markdown = convert_document_to_markdown(pdf_path)
        _event("convert", markdown_chars=len(markdown), source=str(pdf_path.name))
    except Exception as exc:  # noqa: BLE001
        return IntakeResult(
            status=STATUS_FAILED,
            metadata={},
            departments_needed=[],
            sections={},
            unmapped_topics=[],
            conflicts=[],
            intake_summary="",
            requires_ceo_approval=False,
            markdown_text="",
            readability_scores={},
            error_message=f"convert_failed:{type(exc).__name__}: {exc}",
            trace=trace,
        )

    scores = compute_readability_scores(markdown)
    _event("readability", scores=scores)

    # First agent: valid RFP?
    classified = classifier_agent(markdown)
    assert_no_silent_discard(classified)
    _event(
        "classifier_agent",
        is_valid_rfp=classified.is_valid_rfp,
        status=classified.status,
        departments_needed=classified.departments_needed,
        discard_reason=classified.discard_reason,
        discard_rule_id=classified.discard_rule_id,
        rationale=classified.rationale,
    )

    metadata = dict(classified.metadata)
    if title:
        metadata["title"] = title
    metadata["readability_scores"] = scores

    if not classified.is_valid_rfp:
        reason = classified.discard_reason or ""
        logger.warning(
            "Intake stopped after classifier_agent: %s (%s)",
            reason,
            classified.discard_rule_id,
        )
        return IntakeResult(
            status=STATUS_DISCARDED,
            metadata=metadata,
            departments_needed=[],
            sections={},
            unmapped_topics=classified.unmapped_topics,
            conflicts=[],
            intake_summary=reason,
            requires_ceo_approval=False,
            markdown_text=markdown,
            readability_scores=scores,
            discard_reason=reason,
            discard_rule_id=classified.discard_rule_id,
            trace=trace,
        )

    depts = [d for d in classified.departments_needed if d in DEPARTMENT_IDS]
    sections: dict[str, list[str]] = {}
    for dept in depts:
        excerpt = build_department_excerpt(markdown, dept)
        aspects = department_worker(dept, metadata, excerpt)
        sections[dept] = aspects
        _event("department_worker", department_id=dept, key_aspects=aspects)

    summary, conflicts = synthesize_intake(metadata, depts, sections)
    _event("synthesize", summary=summary, conflicts=conflicts)

    return IntakeResult(
        status=STATUS_INTAKE_COMPLETE,
        metadata=metadata,
        departments_needed=depts,
        sections=sections,
        unmapped_topics=classified.unmapped_topics,
        conflicts=conflicts,
        intake_summary=summary,
        requires_ceo_approval=classified.requires_ceo_approval,
        markdown_text=markdown,
        readability_scores=scores,
        trace=trace,
    )


def run_intake_from_bytes(
    *,
    raw: bytes,
    filename: str,
    title: str | None = None,
    store_dir: Path,
) -> tuple[IntakeResult, Path]:
    """Persist uploaded bytes under store_dir, then run the pipeline."""
    store_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\-]+", "_", Path(filename).name)[:180] or "rfp.pdf"
    pdf_path = store_dir / safe
    pdf_path.write_bytes(raw)
    result = run_intake_pipeline(pdf_path=pdf_path, title=title)
    (store_dir / "extracted.md").write_text(
        result.markdown_text + ("\n" if result.markdown_text else ""),
        encoding="utf-8",
    )
    (store_dir / "intake.json").write_text(
        json.dumps(
            {
                "status": result.status,
                "metadata": result.metadata,
                "departments_needed": result.departments_needed,
                "sections": result.sections,
                "requires_ceo_approval": result.requires_ceo_approval,
                "discard_reason": result.discard_reason,
                "intake_summary": result.intake_summary,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return result, pdf_path
