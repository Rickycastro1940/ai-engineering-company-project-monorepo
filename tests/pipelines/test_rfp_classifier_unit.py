"""Unit tests: classifier_agent against CONTEXT sample PDFs.

Formal accept (#1), informal accept (#2), invalid reject (#3).
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
    DISCARD_NOT_AN_RFP,
    STATUS_DISCARDED,
)
from data.pipelines.rfp_intake.context_rules import CONTEXT_SEED_EXPECTATIONS

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"


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
