"""Evaluate: classifier_agent — first agent after convert.

Must read markdown, accept valid RFPs, and stop invalid ones as discarded
with an explicit discard_reason (never fail silently).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_intake import (
    classifier_agent,
    convert_document_to_markdown,
    run_intake_pipeline,
)
from data.pipelines.rfp_intake.classifier import (
    ClassifierDecision,
    assert_no_silent_discard,
    _discard,
)
from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_TRAINING,
    DISCARD_EMPTY_DOCUMENT,
    DISCARD_NOT_AN_RFP,
    STATUS_DISCARDED,
    STATUS_INTAKE_COMPLETE,
)

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"


def test_classifier_accepts_formal_sunset_bay() -> None:
    md = convert_document_to_markdown(SEEDS / "CONTEXT-brasaland-request-1.pdf")
    decision = classifier_agent(md)
    assert decision.is_valid_rfp is True
    assert decision.status == "accepted"
    assert decision.discard_reason is None
    assert DEPARTMENT_TRAINING in decision.departments_needed
    assert decision.requires_ceo_approval is True


def test_classifier_accepts_informal_andes() -> None:
    md = convert_document_to_markdown(SEEDS / "CONTEXT-brasaland-request-2.pdf")
    decision = classifier_agent(md)
    assert decision.is_valid_rfp is True
    assert DEPARTMENT_TRAINING not in decision.departments_needed


def test_classifier_discards_franchise_with_explicit_reason() -> None:
    md = convert_document_to_markdown(SEEDS / "CONTEXT-brasaland-request-3.pdf")
    decision = classifier_agent(md)
    assert decision.is_valid_rfp is False
    assert decision.status == STATUS_DISCARDED
    assert decision.discard_reason
    assert "franchise" in decision.discard_reason.casefold() or "franquicia" in md.casefold()
    assert decision.discard_rule_id == DISCARD_NOT_AN_RFP
    assert_no_silent_discard(decision)


def test_classifier_rejects_empty_markdown_explicitly() -> None:
    decision = classifier_agent("short")
    assert decision.is_valid_rfp is False
    assert decision.discard_rule_id == DISCARD_EMPTY_DOCUMENT
    assert decision.discard_reason


def test_classifier_rejects_non_rfp_noise() -> None:
    decision = classifier_agent(
        "Hello, I love your brand and want a sticker pack for my birthday party next week. "
        "Please send merch catalog only. Thanks!"
    )
    assert decision.is_valid_rfp is False
    assert decision.discard_rule_id == DISCARD_NOT_AN_RFP
    assert decision.discard_reason


def test_discard_helper_refuses_silent_failure() -> None:
    with pytest.raises(ValueError, match="silent"):
        _discard(reason="", rule_id=DISCARD_NOT_AN_RFP)
    with pytest.raises(ValueError, match="silent"):
        _discard(reason="missing reason only", rule_id="")


def test_assert_no_silent_discard_raises() -> None:
    bad = ClassifierDecision(is_valid_rfp=False, discard_reason=None, discard_rule_id=None)
    with pytest.raises(RuntimeError, match="silent"):
        assert_no_silent_discard(bad)


def test_pipeline_stops_after_classifier_on_discard() -> None:
    result = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-3.pdf")
    assert result.status == STATUS_DISCARDED
    assert result.discard_reason
    assert result.discard_rule_id == DISCARD_NOT_AN_RFP
    assert result.departments_needed == []
    assert result.sections == {}
    nodes = [e["node"] for e in result.trace]
    assert "classifier_agent" in nodes
    assert "department_worker" not in nodes
    assert "synthesize" not in nodes


def test_pipeline_continues_past_classifier_when_valid() -> None:
    result = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-1.pdf")
    assert result.status == STATUS_INTAKE_COMPLETE
    assert result.discard_reason is None
    nodes = [e["node"] for e in result.trace]
    assert "classifier_agent" in nodes
    assert "department_worker" in nodes
    assert "synthesizer" in nodes or "synthesize" in nodes
    assert "orchestrator" in nodes
