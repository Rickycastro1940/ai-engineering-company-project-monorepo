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
    MIN_MARKDOWN_CHARS,
    STATUS_DISCARDED,
    STATUS_FAILED,
    STATUS_INTAKE_COMPLETE,
)
from data.pipelines.rfp_intake.orchestration import (
    build_department_excerpt,
    department_worker_from_parts,
    run_department_orchestration,
    synthesizer as _synthesizer_impl,
)
from data.pipelines.rfp_intake.routing import (
    build_part2_handoff,
    route_intake_to_part2,
    validate_part2_handoff,
)

logger = logging.getLogger(__name__)

# Back-compat name used in older call sites / docs
ClassifyResult = ClassifierDecision

# Back-compat: old signature department_worker(dept, metadata, excerpt) -> list[str]
department_worker = department_worker_from_parts


def synthesize_intake(
    metadata: dict[str, Any],
    departments_needed: list[str],
    sections: dict[str, list[str]],
) -> tuple[str, list[dict[str, Any]]]:
    """Back-compat wrapper around the Sales-facing synthesizer."""
    from data.pipelines.rfp_intake.orchestration import WorkerResult
    from data.pipelines.rfp_intake.constants import DEPARTMENT_OWNERS

    workers = [
        WorkerResult(
            department_id=d,
            owner=DEPARTMENT_OWNERS.get(d, d),
            key_aspects=list(sections.get(d) or []),
        )
        for d in departments_needed
    ]
    result = _synthesizer_impl(
        metadata=metadata,
        worker_results=workers,
        requires_ceo_approval=float(metadata.get("estimated_contract_value_usd") or 0)
        > 50_000,
    )
    return result.intake_summary, result.conflicts


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
    "run_department_orchestration",
    "run_intake_from_bytes",
    "run_intake_pipeline",
    "build_part2_handoff",
    "route_intake_to_part2",
    "validate_part2_handoff",
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
    open_questions: list[str] = field(default_factory=list)
    part2_handoff: dict[str, Any] = field(default_factory=dict)
    ask_whom: list[dict[str, str]] = field(default_factory=list)
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
    """Compute per-document readability metrics (CONTEXT §2.3).

    Always returns at least length stats; Flesch-family scores when text is long enough.
    """
    text = markdown_text or ""
    words = re.findall(r"\b\w+\b", text)
    scores: dict[str, float] = {
        "word_count": float(len(words)),
        "char_count": float(len(text)),
    }
    if len(words) < 100:
        return scores
    try:
        import nltk
        from readability import Readability

        nltk.download("punkt_tab", quiet=True)
        analyzer = Readability(text)
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
        logger.debug("readability formulas skipped: %s", exc)
        return scores


def run_intake_pipeline(*, pdf_path: Path, title: str | None = None) -> IntakeResult:
    """Part 1: convert → classifier → orchestrator → workers → synthesizer.

    On success: ``status=intake_complete`` with Sales-facing summary and Part 2 handoff.
    Invalid RFPs stop after the classifier with ``status=discarded`` (never silent).
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
    sections, synthesis, orch_events = run_department_orchestration(
        markdown_text=markdown,
        metadata=metadata,
        departments_needed=depts,
        requires_ceo_approval=classified.requires_ceo_approval,
    )
    for event in orch_events:
        trace.append(event)

    metadata["open_questions"] = synthesis.open_questions
    metadata["part2_handoff"] = synthesis.part2_handoff
    metadata["ask_whom"] = synthesis.ask_whom

    return IntakeResult(
        status=STATUS_INTAKE_COMPLETE,
        metadata=metadata,
        departments_needed=depts,
        sections=sections,
        unmapped_topics=classified.unmapped_topics,
        conflicts=synthesis.conflicts,
        intake_summary=synthesis.intake_summary,
        requires_ceo_approval=classified.requires_ceo_approval,
        markdown_text=markdown,
        readability_scores=scores,
        open_questions=synthesis.open_questions,
        part2_handoff=synthesis.part2_handoff,
        ask_whom=synthesis.ask_whom,
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
                "part2_handoff": result.part2_handoff,
                "ask_whom": result.ask_whom,
                "open_questions": result.open_questions,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return result, pdf_path
