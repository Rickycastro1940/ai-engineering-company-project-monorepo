"""Optional knowledge-base grounding for Part 2 generators (not a graded requirement)."""

from __future__ import annotations

from unittest.mock import patch

from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
)
from data.pipelines.rfp_response.agents import Part1DepartmentSummary, run_generator_agent
from data.pipelines.rfp_response.kb_grounding import (
    KbSnippet,
    lookup_department_knowledge,
)


def _summary(dept: str, aspects: list[str]) -> Part1DepartmentSummary:
    return Part1DepartmentSummary(
        department_id=dept,
        key_aspects=aspects,
        metadata={
            "client_name": "Andes Tech",
            "location": "Medellín",
            "service_type": "weekly catering",
        },
    )


def test_local_kb_fallback_grounds_each_department() -> None:
    with patch(
        "data.pipelines.rfp_response.kb_grounding._from_retrieve", return_value=[]
    ):
        marketing = run_generator_agent(
            _summary(DEPARTMENT_MARKETING, ["Brand terms for Andes Tech catering"])
        )
        ops = run_generator_agent(
            _summary(
                DEPARTMENT_OPERACIONES,
                ["Operational feasibility for Andes Tech @ Medellín"],
            )
        )
        proc = run_generator_agent(
            _summary(
                DEPARTMENT_PROCUREMENT,
                ["Ingredient cost / supplier lead times for Andes Tech"],
            )
        )
        train = run_generator_agent(
            _summary(
                DEPARTMENT_TRAINING,
                ["Certification and quality standards for Andes Tech"],
            )
        )

    assert marketing.kb_grounded is True
    assert "brasa points" in marketing.draft_content.casefold()
    assert "10,000 cop" in marketing.draft_content.casefold()
    assert "10 usd" in marketing.draft_content.casefold()

    assert ops.kb_grounded is True
    assert "felipe guerrero" in ops.draft_content.casefold()
    assert "waste" in ops.draft_content.casefold()

    assert proc.kb_grounded is True
    assert "lucía fernández" in proc.draft_content.casefold()
    assert "500 usd" in proc.draft_content.casefold()
    assert "cop" in proc.draft_content.casefold()

    assert train.kb_grounded is True
    assert "allergen" in train.draft_content.casefold() or "allergy" in train.draft_content.casefold()
    assert "zero" in train.draft_content.casefold()

    for draft in (marketing, ops, proc, train):
        assert "brasaland_kb" not in draft.draft_content
        assert "/knowledge/query" not in draft.draft_content


def test_retrieve_path_used_when_semantic_kb_returns_chunks() -> None:
    snip = KbSnippet(
        source_document="supplier-ordering",
        text=(
            "An emergency order requires approval from Lucía Fernández "
            "(Procurement Manager) if it exceeds 500 USD (or the COP equivalent)."
        ),
        via="retrieve",
    )
    with patch(
        "data.pipelines.rfp_response.kb_grounding._from_retrieve",
        return_value=[snip],
    ):
        result = run_generator_agent(
            _summary(
                DEPARTMENT_PROCUREMENT,
                ["Ingredient cost / supplier lead times for Andes Tech"],
            )
        )
    assert result.kb_grounded is True
    assert result.kb_sources == ["supplier-ordering"]
    assert "500 USD" in result.draft_content
    assert "COP" in result.draft_content
    assert "Lucía Fernández" in result.draft_content


def test_kb_outage_does_not_block_drafting() -> None:
    with (
        patch(
            "data.pipelines.rfp_response.kb_grounding._from_retrieve",
            side_effect=RuntimeError("qdrant down"),
        ),
        patch(
            "data.pipelines.rfp_response.kb_grounding._from_local_docs",
            side_effect=OSError("docs missing"),
        ),
    ):
        result = run_generator_agent(
            _summary(DEPARTMENT_MARKETING, ["Brand exclusivity for Andes Tech"])
        )
    assert result.draft_content
    assert result.kb_grounded is False
    assert "andes tech" in result.draft_content.casefold()
    assert "pricing proposal" in result.draft_content.casefold()


def test_kb_grounding_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("RFP_KB_GROUNDING", "0")
    snips = lookup_department_knowledge(DEPARTMENT_PROCUREMENT)
    assert snips == []
    result = run_generator_agent(
        _summary(
            DEPARTMENT_PROCUREMENT,
            ["Ingredient cost / supplier lead times for Andes Tech"],
        )
    )
    assert result.kb_grounded is False
    assert "Company knowledge (policies and brand language)" not in result.draft_content
    assert "ingredient cost" in result.draft_content.casefold()
