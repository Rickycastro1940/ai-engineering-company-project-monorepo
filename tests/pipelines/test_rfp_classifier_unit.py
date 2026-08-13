"""Unit tests: classifier_agent against CONTEXT sample PDFs + synthetic markdown.

Formal accept (#1), informal accept (#2), invalid reject (#3).
Also pure units with no PDF I/O (synthetic markdown only).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_intake import classifier_agent, convert_document_to_markdown
from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
    DISCARD_EMPTY_DOCUMENT,
    DISCARD_NOT_AN_RFP,
    STATUS_DISCARDED,
)
from data.pipelines.rfp_intake.context_rules import CONTEXT_SEED_EXPECTATIONS

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"

# Synthetic formal RFP — no PDF conversion required
_SYNTHETIC_FORMAL = """
REQUEST FOR PROPOSAL
Client: Synthetic Co-Brand Partners LLC
Location: Bogotá, Colombia
Service type: Co-branded food & beverage concession partnership
Scope of work: exclusivity clause and new signature menu development
Proposal due: 2026-10-15
Estimated annual contract value: $60,000–$75,000 USD
"""

_SYNTHETIC_INFORMAL = """
Hola Camila,

Somos Andes Demo Corp en Medellín. Nos gustaría un catering semanal
para 220 empleados con el menú estándar. Contrato por un año.
Propuesta para el 2026-08-18 por favor.

Saludos
"""

_SYNTHETIC_FRANCHISE = """
Hola, me interesa abrir una franquicia Brasaland en mi ciudad.
¿Me pueden enviar información de franquicias? No tengo presupuesto
ni fecha límite todavía.
"""


@pytest.mark.parametrize(
    "filename,expect_accept",
    [
        ("CONTEXT-brasaland-request-1.pdf", True),
        ("CONTEXT-brasaland-request-2.pdf", True),
        ("CONTEXT-brasaland-request-3.pdf", False),
    ],
)
def test_classifier_unit_on_context_seed_pdfs(filename: str, expect_accept: bool) -> None:
    """Unit: classifier_agent(markdown) for each CONTEXT §4 sample PDF."""
    pdf = SEEDS / filename
    assert pdf.is_file()
    markdown = convert_document_to_markdown(pdf)
    assert len(markdown) > 40

    decision = classifier_agent(markdown)
    expected = CONTEXT_SEED_EXPECTATIONS[filename]

    if expect_accept:
        assert decision.is_valid_rfp is True
        assert decision.discard_reason is None
        assert set(decision.departments_needed) == set(expected["departments"])
        assert expected["client_substr"] in (decision.metadata.get("client_name") or "")
        assert decision.requires_ceo_approval is expected["requires_ceo_approval"]
        for excluded in expected.get("exclude_departments") or set():
            assert excluded not in decision.departments_needed
    else:
        assert decision.is_valid_rfp is False
        assert decision.status == STATUS_DISCARDED
        assert decision.discard_reason
        assert decision.discard_rule_id == DISCARD_NOT_AN_RFP
        assert decision.departments_needed == []


def test_classifier_unit_formal_includes_all_four_departments() -> None:
    md = convert_document_to_markdown(SEEDS / "CONTEXT-brasaland-request-1.pdf")
    decision = classifier_agent(md)
    assert set(decision.departments_needed) == {
        DEPARTMENT_MARKETING,
        DEPARTMENT_OPERACIONES,
        DEPARTMENT_PROCUREMENT,
        DEPARTMENT_TRAINING,
    }


def test_classifier_unit_informal_excludes_training() -> None:
    md = convert_document_to_markdown(SEEDS / "CONTEXT-brasaland-request-2.pdf")
    decision = classifier_agent(md)
    assert DEPARTMENT_TRAINING not in decision.departments_needed
    assert set(decision.departments_needed) == {
        DEPARTMENT_MARKETING,
        DEPARTMENT_OPERACIONES,
        DEPARTMENT_PROCUREMENT,
    }


def test_classifier_unit_synthetic_formal_accepts_with_training_and_ceo() -> None:
    """Pure unit: synthetic markdown — no PDF I/O."""
    decision = classifier_agent(_SYNTHETIC_FORMAL)
    assert decision.is_valid_rfp is True
    assert decision.discard_reason is None
    assert DEPARTMENT_MARKETING in decision.departments_needed
    assert DEPARTMENT_TRAINING in decision.departments_needed  # signature menu
    assert decision.requires_ceo_approval is True
    assert "Synthetic" in (decision.metadata.get("client_name") or "")


def test_classifier_unit_synthetic_informal_skips_training() -> None:
    decision = classifier_agent(_SYNTHETIC_INFORMAL)
    assert decision.is_valid_rfp is True
    assert DEPARTMENT_TRAINING not in decision.departments_needed
    assert DEPARTMENT_MARKETING in decision.departments_needed
    assert DEPARTMENT_OPERACIONES in decision.departments_needed
    assert DEPARTMENT_PROCUREMENT in decision.departments_needed


def test_classifier_unit_synthetic_franchise_discards_explicitly() -> None:
    decision = classifier_agent(_SYNTHETIC_FRANCHISE)
    assert decision.is_valid_rfp is False
    assert decision.status == STATUS_DISCARDED
    assert decision.discard_rule_id == DISCARD_NOT_AN_RFP
    assert decision.discard_reason
    assert decision.departments_needed == []


def test_classifier_unit_empty_markdown_discards() -> None:
    decision = classifier_agent("tiny")
    assert decision.is_valid_rfp is False
    assert decision.discard_rule_id == DISCARD_EMPTY_DOCUMENT
    assert decision.discard_reason
