"""Part 3 unit: CONTEXT §7 arbitration is a fixed table, not LLM consensus."""

from __future__ import annotations

from data.pipelines.rfp_approval.arbitration import (
    apply_fixed_arbitration,
    request_changes_departments,
    synthesizer_blocked_by_arbitration,
)
from data.pipelines.rfp_approval.conflicts import conflict_surface_agent
from data.pipelines.rfp_intake.context_rules import CONTEXT_ARBITRATION_RULES


def test_cost_vs_feasibility_surfaces_and_camila_forces_request_changes() -> None:
    sections = [
        {
            "department_id": "operaciones",
            "draft_content": "## Cost per event\nUSD $20 per cover.\n",
        },
        {
            "department_id": "procurement",
            "draft_content": "## Estimated ingredient cost based on volume\nUSD $80 ingredient cost.\n",
        },
    ]
    surfaced = conflict_surface_agent(sections=sections, metadata={})
    ids = [c["trigger_id"] for c in surfaced]
    assert "cost-vs-feasibility" in ids
    resolutions = apply_fixed_arbitration(surfaced)
    cost = next(r for r in resolutions if r["trigger_id"] == "cost-vs-feasibility")
    assert cost["arbiter"] == "Camila Ospina"
    assert cost["action"] == "request_changes"
    assert cost["llm_resolved"] is False
    assert set(request_changes_departments(resolutions)) >= {"operaciones", "procurement"}


def test_setup_sla_breach_felipe_is_fixed_arbiter() -> None:
    sections = [
        {
            "department_id": "marketing",
            "draft_content": "Setup in 3 business days so we can start immediately.\n",
        },
        {
            "department_id": "operaciones",
            "draft_content": "Delivery within 12 business days.\n",
        },
    ]
    surfaced = conflict_surface_agent(sections=sections)
    hit = next(c for c in surfaced if c["trigger_id"] == "setup-sla-breach")
    assert "marketing" in hit["affected_departments"]
    assert "operaciones" not in hit["affected_departments"]
    resolution = apply_fixed_arbitration([hit])[0]
    assert resolution["arbiter"] == "Felipe Guerrero"
    assert resolution["escalation_arbiter"] == "Camila Ospina"
    assert resolution["action"] == "request_changes"
    assert resolution["llm_resolved"] is False


def test_ceo_threshold_blocks_synthesizer_until_mariana_approves() -> None:
    surfaced = conflict_surface_agent(
        sections=[],
        metadata={"estimated_contract_value_usd": 75_000},
        requires_ceo_flag=True,
        ceo_approval={"approval_status": "pending"},
    )
    assert any(c["trigger_id"] == "ceo-threshold" for c in surfaced)
    resolutions = apply_fixed_arbitration(surfaced)
    ceo = next(r for r in resolutions if r["trigger_id"] == "ceo-threshold")
    assert ceo["arbiter"] == "Mariana Restrepo"
    assert ceo["action"] == "block_synthesizer"
    assert synthesizer_blocked_by_arbitration(resolutions, ceo_approval_status="pending")
    assert synthesizer_blocked_by_arbitration(resolutions, ceo_approval_status="rejected")
    assert not synthesizer_blocked_by_arbitration(
        resolutions, ceo_approval_status="approved"
    )


def test_arbitration_rules_are_the_context_table_not_freeform() -> None:
    assert set(CONTEXT_ARBITRATION_RULES) == {
        "cost-vs-feasibility",
        "setup-sla-breach",
        "ceo-threshold",
    }
    src = (  # noqa: PTH123 — assert source file does not call an LLM
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "data"
        / "pipelines"
        / "rfp_approval"
        / "arbitration.py"
    ).read_text(encoding="utf-8")
    assert "openai" not in src.casefold()
    assert "ChatOpenAI" not in src
    assert "llm" in src.casefold()  # documents that LLM must not resolve
