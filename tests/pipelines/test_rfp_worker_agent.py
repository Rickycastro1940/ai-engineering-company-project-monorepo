"""Unit tests: department worker agent (at least marketing + operaciones).

Workers receive shared metadata + department-relevant extracts only and emit
``key_aspects`` without inventing figures absent from the RFP (CONTEXT §2.3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_intake import (
    classifier_agent,
    convert_document_to_markdown,
)
from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_CONTRIBUTIONS,
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_OWNERS,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
    TICKET_OWNER,
)
from data.pipelines.rfp_intake.orchestration import (
    DepartmentSubtask,
    build_department_excerpt,
    department_worker,
    orchestrator,
)

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"


def _subtask_for_seed(pdf_name: str, department_id: str) -> DepartmentSubtask:
    pdf = SEEDS / pdf_name
    markdown = convert_document_to_markdown(pdf)
    classified = classifier_agent(markdown)
    assert classified.is_valid_rfp, f"{pdf_name} should be accepted before worker unit test"
    excerpt = build_department_excerpt(markdown, department_id)
    return DepartmentSubtask(
        department_id=department_id,
        owner=DEPARTMENT_OWNERS[department_id],
        label=department_id,
        excerpt=excerpt,
        shared_metadata=dict(classified.metadata),
    )


def test_marketing_worker_unit_formal_sunset_bay() -> None:
    """Unit: marketing worker on formal CONTEXT seed #1."""
    subtask = _subtask_for_seed("CONTEXT-brasaland-request-1.pdf", DEPARTMENT_MARKETING)
    result = department_worker(subtask)

    assert result.department_id == DEPARTMENT_MARKETING
    assert result.owner == TICKET_OWNER
    assert result.key_aspects
    assert result.excerpt_chars > 0
    joined = " ".join(result.key_aspects)
    assert "30 days" in joined or "validity" in joined.casefold()
    assert "CONTEXT remit" in joined or "Brand" in joined or "exclusiv" in joined.casefold()
    # Must not invent prices
    assert "we will charge $" not in joined.casefold()


def test_operaciones_worker_unit_informal_andes() -> None:
    """Unit: operaciones worker on informal CONTEXT seed #2."""
    subtask = _subtask_for_seed("CONTEXT-brasaland-request-2.pdf", DEPARTMENT_OPERACIONES)
    result = department_worker(subtask)

    assert result.department_id == DEPARTMENT_OPERACIONES
    assert result.owner == DEPARTMENT_OWNERS[DEPARTMENT_OPERACIONES]
    assert result.key_aspects
    joined = " ".join(result.key_aspects)
    assert "10 business days" in joined or "feasibility" in joined.casefold()
    # Volume 220 is in the RFP — may appear; invented figures must not
    assert "guaranteed 999" not in joined.casefold()
    assert DEPARTMENT_CONTRIBUTIONS[DEPARTMENT_OPERACIONES].split(":")[0] in joined or (
        "CONTEXT remit" in joined
    )


def test_procurement_worker_unit_never_invents_missing_budget() -> None:
    """Unit: procurement worker records open_questions when budget absent (Andes)."""
    subtask = _subtask_for_seed("CONTEXT-brasaland-request-2.pdf", DEPARTMENT_PROCUREMENT)
    # Andes has no budget_range in metadata
    assert not subtask.shared_metadata.get("budget_range")
    result = department_worker(subtask)
    assert result.key_aspects
    assert result.open_questions or any(
        "open_questions" in a.casefold() or "not" in a.casefold() for a in result.key_aspects
    )


def test_training_worker_only_when_orchestrator_includes_it() -> None:
    """Unit: training worker runs for formal (#1) and is skipped for informal (#2)."""
    md1 = convert_document_to_markdown(SEEDS / "CONTEXT-brasaland-request-1.pdf")
    c1 = classifier_agent(md1)
    tasks1 = orchestrator(
        markdown_text=md1,
        metadata=c1.metadata,
        departments_needed=c1.departments_needed,
    )
    assert any(t.department_id == DEPARTMENT_TRAINING for t in tasks1)
    training = next(t for t in tasks1 if t.department_id == DEPARTMENT_TRAINING)
    tr = department_worker(training)
    assert tr.key_aspects
    assert tr.owner == DEPARTMENT_OWNERS[DEPARTMENT_TRAINING]

    md2 = convert_document_to_markdown(SEEDS / "CONTEXT-brasaland-request-2.pdf")
    c2 = classifier_agent(md2)
    tasks2 = orchestrator(
        markdown_text=md2,
        metadata=c2.metadata,
        departments_needed=c2.departments_needed,
    )
    assert all(t.department_id != DEPARTMENT_TRAINING for t in tasks2)


@pytest.mark.parametrize(
    "department_id",
    [DEPARTMENT_MARKETING, DEPARTMENT_OPERACIONES],
)
def test_worker_receives_excerpt_not_full_document(department_id: str) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    markdown = convert_document_to_markdown(pdf)
    classified = classifier_agent(markdown)
    excerpt = build_department_excerpt(markdown, department_id)
    assert excerpt
    assert len(excerpt) <= len(markdown)
    subtask = DepartmentSubtask(
        department_id=department_id,
        owner=DEPARTMENT_OWNERS[department_id],
        label=department_id,
        excerpt=excerpt,
        shared_metadata=classified.metadata,
    )
    result = department_worker(subtask)
    assert result.excerpt_chars == len(excerpt)
    assert result.key_aspects
