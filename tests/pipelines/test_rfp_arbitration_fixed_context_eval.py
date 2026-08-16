"""Evaluate: arbitration fires on CONTEXT §7 triggers via fixed arbiter (not LLM).

Proves in code (source + runtime), not docs alone:
1. Graph wires ``surface_conflicts`` → ``arbitration`` as dedicated nodes
2. Conflicts are detected by trigger ids from CONTEXT (§7 table)
3. Resolutions come from ``CONTEXT_ARBITRATION_RULES`` / ``apply_fixed_arbitration``
4. Every resolution sets ``llm_resolved=False``; arbitration source has no LLM client
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from data.pipelines.rfp_approval.arbitration import apply_fixed_arbitration
from data.pipelines.rfp_approval.checkpointer import (
    approval_thread_id,
    reset_approval_checkpointer,
)
from data.pipelines.rfp_approval.conflicts import (
    TRIGGER_CEO_THRESHOLD,
    TRIGGER_COST_VS_FEASIBILITY,
    TRIGGER_SETUP_SLA_BREACH,
    conflict_surface_agent,
)
from data.pipelines.rfp_approval.fixtures import (
    cost_disagreement_pipeline_kwargs,
    setup_sla_breach_pipeline_kwargs,
    sunset_pipeline_kwargs,
)
from data.pipelines.rfp_approval.graph import (
    arbitration_node,
    build_rfp_approval_graph,
    invoke_rfp_approval_graph,
    surface_conflicts_node,
)
from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_ARBITRATION_RULES,
    CONTEXT_ARBITRATION_TRIGGER_IDS,
    CONTEXT_CEO_NAME,
    CONTEXT_DEPARTMENT_OWNERS,
    CONTEXT_TICKET_OWNER,
)

ARTIFACT = Path("/opt/cursor/artifacts/rfp_arbitration_fixed_context.json")
REPO = Path(__file__).resolve().parents[2]
APPROVAL_DIR = REPO / "data" / "pipelines" / "rfp_approval"

EXPECTED_ARBITERS = {
    TRIGGER_COST_VS_FEASIBILITY: CONTEXT_TICKET_OWNER,  # Camila Ospina
    TRIGGER_SETUP_SLA_BREACH: CONTEXT_DEPARTMENT_OWNERS["operaciones"],  # Felipe
    TRIGGER_CEO_THRESHOLD: CONTEXT_CEO_NAME,  # Mariana Restrepo
}


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "arb-fixed.sqlite"))
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()


def test_context_trigger_ids_match_section_7_table() -> None:
    assert set(CONTEXT_ARBITRATION_TRIGGER_IDS) == {
        TRIGGER_COST_VS_FEASIBILITY,
        TRIGGER_SETUP_SLA_BREACH,
        TRIGGER_CEO_THRESHOLD,
    }
    assert set(CONTEXT_ARBITRATION_RULES) == set(CONTEXT_ARBITRATION_TRIGGER_IDS)
    for trigger_id, arbiter in EXPECTED_ARBITERS.items():
        assert CONTEXT_ARBITRATION_RULES[trigger_id]["arbiter"] == arbiter
    assert (
        CONTEXT_ARBITRATION_RULES[TRIGGER_SETUP_SLA_BREACH]["escalation_arbiter"]
        == CONTEXT_TICKET_OWNER
    )


def test_arbitration_source_is_fixed_table_not_llm_client() -> None:
    """Arbitration module + node must not call an LLM to resolve conflicts."""
    arb_mod = (APPROVAL_DIR / "arbitration.py").read_text(encoding="utf-8")
    conflicts_mod = (APPROVAL_DIR / "conflicts.py").read_text(encoding="utf-8")
    arb_node_src = inspect.getsource(arbitration_node)
    surface_src = inspect.getsource(surface_conflicts_node)
    build_src = inspect.getsource(build_rfp_approval_graph)

    assert "apply_fixed_arbitration" in arb_node_src
    assert 'row["llm_resolved"] = False' in arb_node_src
    assert 'mode": "fixed_arbiter_table"' in arb_node_src
    assert "conflict_surface_agent" in surface_src
    assert 'add_node("arbitration"' in build_src
    assert 'add_node("surface_conflicts"' in build_src
    assert 'add_edge("surface_conflicts", "arbitration")' in build_src

    for label, src in (
        ("arbitration.py", arb_mod),
        ("conflicts.py", conflicts_mod),
        ("arbitration_node", arb_node_src),
    ):
        lowered = src.casefold()
        assert "openai" not in lowered, f"{label} imports/calls OpenAI"
        assert "chatopenai" not in lowered, f"{label} uses ChatOpenAI"
        assert "invoke_llm" not in lowered, f"{label} invokes LLM"
        assert "langchain_openai" not in lowered, f"{label} uses langchain OpenAI"

    # Unknown trigger must fail closed (table lookup), not invent an LLM answer.
    with pytest.raises(KeyError, match="No CONTEXT"):
        apply_fixed_arbitration([{"trigger_id": "made-up-consensus", "affected_departments": []}])


def test_graph_runtime_fires_all_three_context_triggers_with_fixed_arbiters() -> None:
    """End-to-end: each CONTEXT trigger surfaces and resolves via fixed arbiter."""
    evidence: dict[str, dict] = {}

    # --- cost-vs-feasibility → Camila / request_changes ---
    cost_kw = cost_disagreement_pipeline_kwargs(ticket_id="eval-arb-cost")
    cost_result = invoke_rfp_approval_graph(
        **{k: v for k, v in cost_kw.items() if k != "queued_decisions"},
        use_interrupt=True,
        thread_id=approval_thread_id(cost_kw["ticket_id"]),
    )
    cost_conflicts = list(cost_result.get("conflicts") or [])
    cost_arb = list(cost_result.get("arbitration") or [])
    assert any(c.get("trigger_id") == TRIGGER_COST_VS_FEASIBILITY for c in cost_conflicts)
    cost_row = next(r for r in cost_arb if r["trigger_id"] == TRIGGER_COST_VS_FEASIBILITY)
    assert cost_row["arbiter"] == EXPECTED_ARBITERS[TRIGGER_COST_VS_FEASIBILITY]
    assert cost_row["action"] == "request_changes"
    assert cost_row["llm_resolved"] is False
    assert cost_row["resolution_rule"] == CONTEXT_ARBITRATION_RULES[
        TRIGGER_COST_VS_FEASIBILITY
    ]["resolution"]
    assert (cost_result.get("approvals") or {}).get("operaciones", {}).get(
        "arbiter_forced"
    )
    cost_trace = [e for e in (cost_result.get("trace") or []) if e.get("node") == "arbitration"]
    assert cost_trace
    assert cost_trace[0]["output"].get("llm_resolved") is False
    assert TRIGGER_COST_VS_FEASIBILITY in (cost_trace[0]["output"].get("trigger_ids") or [])
    evidence["cost-vs-feasibility"] = {
        "surfaced": True,
        "arbiter": cost_row["arbiter"],
        "action": cost_row["action"],
        "llm_resolved": cost_row["llm_resolved"],
        "trace_agent": cost_trace[0].get("agent"),
        "trace_mode": (cost_trace[0].get("input") or {}).get("mode"),
    }

    # --- setup-sla-breach → Felipe (+ Camila escalate) / request_changes ---
    sla_kw = setup_sla_breach_pipeline_kwargs(ticket_id="eval-arb-sla")
    sla_result = invoke_rfp_approval_graph(
        **{k: v for k, v in sla_kw.items() if k != "queued_decisions"},
        use_interrupt=True,
        thread_id=approval_thread_id(sla_kw["ticket_id"]),
    )
    sla_arb = list(sla_result.get("arbitration") or [])
    sla_row = next(r for r in sla_arb if r["trigger_id"] == TRIGGER_SETUP_SLA_BREACH)
    assert sla_row["arbiter"] == EXPECTED_ARBITERS[TRIGGER_SETUP_SLA_BREACH]
    assert sla_row["escalation_arbiter"] == CONTEXT_TICKET_OWNER
    assert sla_row["action"] == "request_changes"
    assert sla_row["llm_resolved"] is False
    evidence["setup-sla-breach"] = {
        "surfaced": True,
        "arbiter": sla_row["arbiter"],
        "escalation_arbiter": sla_row["escalation_arbiter"],
        "action": sla_row["action"],
        "llm_resolved": sla_row["llm_resolved"],
    }

    # --- ceo-threshold → Mariana / block_synthesizer ---
    sunset_kw = sunset_pipeline_kwargs(include_ceo=False)
    sunset_kw["ticket_id"] = "eval-arb-ceo"
    sunset_kw["queued_decisions"] = []
    ceo_result = invoke_rfp_approval_graph(
        **{k: v for k, v in sunset_kw.items() if k != "queued_decisions"},
        use_interrupt=True,
        thread_id=approval_thread_id(str(sunset_kw["ticket_id"])),
    )
    ceo_arb = list(ceo_result.get("arbitration") or [])
    ceo_row = next(r for r in ceo_arb if r["trigger_id"] == TRIGGER_CEO_THRESHOLD)
    assert ceo_row["arbiter"] == EXPECTED_ARBITERS[TRIGGER_CEO_THRESHOLD]
    assert ceo_row["action"] == "block_synthesizer"
    assert ceo_row["llm_resolved"] is False
    evidence["ceo-threshold"] = {
        "surfaced": True,
        "arbiter": ceo_row["arbiter"],
        "action": ceo_row["action"],
        "llm_resolved": ceo_row["llm_resolved"],
        "synthesizer_blocked": bool(ceo_result.get("synthesizer_blocked")),
    }

    # Surface-only agent never resolves (no arbiter / action fields).
    bare = conflict_surface_agent(
        sections=cost_kw["sections"],
        metadata=cost_kw["metadata"],
        requires_ceo_flag=False,
    )
    for hit in bare:
        assert "arbiter" not in hit
        assert hit.get("action") is None

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "claim": (
                    "Arbitration node fires on CONTEXT conflict triggers and "
                    "resolves via the fixed CONTEXT arbiter (not LLM freestyle)"
                ),
                "verdict": "pass",
                "CONTEXT_ARBITRATION_TRIGGER_IDS": list(CONTEXT_ARBITRATION_TRIGGER_IDS),
                "expected_arbiters": EXPECTED_ARBITERS,
                "graph_wiring": "surface_conflicts → arbitration (dedicated nodes)",
                "resolution_mode": "fixed_arbiter_table",
                "runtime_evidence": evidence,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
