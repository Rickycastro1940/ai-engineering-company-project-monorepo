"""Lock Part 3 to CONTEXT-company.md — reject generic approvers / arbitration / FinalDocument.

Department owners (§2.1), arbitration triggers/arbiters (§7), and FinalDocument
fields (§2.3) must match the CONTEXT file in this repo. A generic SaaS-style
implementation that invents VP/Legal ladders or alternate trigger ids fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from data.pipelines.rfp_approval import (
    FINAL_DOCUMENT_CONTEXT_FIELDS,
    assert_final_document_context_shape,
    build_final_document,
    signoffs_for_ticket,
)
from data.pipelines.rfp_approval.approvers import (
    CEO_NAME,
    DEPARTMENT_OWNERS,
    UnknownApproverError,
    assert_allowed_approver,
    requires_ceo_approval,
)
from data.pipelines.rfp_approval.arbitration import apply_fixed_arbitration
from data.pipelines.rfp_approval.conflicts import (
    TRIGGER_CEO_THRESHOLD,
    TRIGGER_COST_VS_FEASIBILITY,
    TRIGGER_SETUP_SLA_BREACH,
    conflict_surface_agent,
)
from data.pipelines.rfp_approval.fixtures import (
    ANDES_DEPARTMENTS,
    SUNSET_DEPARTMENTS,
    andes_sections,
    simulated_ceo_approval,
    simulated_department_approvals,
    sunset_sections,
)
from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_ARBITRATION_RULES,
    CONTEXT_ARBITRATION_TRIGGER_IDS,
    CONTEXT_CEO_NAME,
    CONTEXT_CEO_USD_THRESHOLD,
    CONTEXT_DEPARTMENT_OWNERS,
    CONTEXT_FINAL_DOCUMENT_FIELDS,
    CONTEXT_FORBIDDEN_EXTRA_APPROVERS,
    parse_context_arbitration_table,
    parse_context_department_table,
    read_context_company_md,
)

REPO = Path(__file__).resolve().parents[2]
PART3 = REPO / "data" / "pipelines" / "rfp_approval"
UI_UPLOAD = REPO / "uis" / "backoffice" / "rfp-upload.html"


def test_context_md_department_owners_lock_part3_signoffs() -> None:
    """§2.1 table in CONTEXT-company.md is the only allowed owner roster."""
    rows = parse_context_department_table(read_context_company_md())
    parsed = {r["department_id"]: r["owner"] for r in rows}
    assert parsed == {
        "marketing": "Camila Ospina",
        "operaciones": "Felipe Guerrero",
        "procurement": "Lucía Fernández",
        "training": "Jake Morrison",
    }
    assert DEPARTMENT_OWNERS == CONTEXT_DEPARTMENT_OWNERS == parsed

    signoffs = signoffs_for_ticket(list(parsed), requires_ceo=True)
    by_dept = {s.department_id: s.approver for s in signoffs}
    assert by_dept == {
        **parsed,
        "ceo": "Mariana Restrepo",
    }
    assert CEO_NAME == CONTEXT_CEO_NAME == "Mariana Restrepo"
    assert requires_ceo_approval(estimated_contract_value_usd=CONTEXT_CEO_USD_THRESHOLD) is False
    assert requires_ceo_approval(
        estimated_contract_value_usd=CONTEXT_CEO_USD_THRESHOLD + 0.01
    )


def test_invented_org_ladder_cannot_sign_off() -> None:
    for fake in sorted(CONTEXT_FORBIDDEN_EXTRA_APPROVERS)[:6]:
        with pytest.raises(UnknownApproverError):
            assert_allowed_approver("marketing", fake)
    with pytest.raises(UnknownApproverError):
        assert_allowed_approver("procurement", "Camila Ospina")  # wrong owner
    assert assert_allowed_approver("procurement", "Lucía Fernández") == "Lucía Fernández"
    assert assert_allowed_approver("training", "Jake Morrison") == "Jake Morrison"


def test_context_md_section_7_arbitration_triggers_and_arbiters() -> None:
    """§7 trigger ids + fixed arbiters must match CONTEXT-company.md, not LLM freestyle."""
    md_rows = parse_context_arbitration_table(read_context_company_md())
    assert [r["trigger_id"] for r in md_rows] == list(CONTEXT_ARBITRATION_TRIGGER_IDS)
    assert tuple(r["trigger_id"] for r in md_rows) == (
        TRIGGER_COST_VS_FEASIBILITY,
        TRIGGER_SETUP_SLA_BREACH,
        TRIGGER_CEO_THRESHOLD,
    )

    by_id = {r["trigger_id"]: r for r in md_rows}
    assert "Camila Ospina" in by_id["cost-vs-feasibility"]["arbiter"]
    assert "Felipe Guerrero" in by_id["setup-sla-breach"]["arbiter"]
    assert "Camila" in by_id["setup-sla-breach"]["arbiter"]  # escalation named in CONTEXT
    assert "Mariana Restrepo" in by_id["ceo-threshold"]["arbiter"]

    assert CONTEXT_ARBITRATION_RULES["cost-vs-feasibility"]["arbiter"] == "Camila Ospina"
    assert CONTEXT_ARBITRATION_RULES["setup-sla-breach"]["arbiter"] == "Felipe Guerrero"
    assert CONTEXT_ARBITRATION_RULES["setup-sla-breach"]["escalation_arbiter"] == "Camila Ospina"
    assert CONTEXT_ARBITRATION_RULES["ceo-threshold"]["arbiter"] == "Mariana Restrepo"

    # Runtime surface → fixed table (llm_resolved always False)
    surfaced = conflict_surface_agent(
        sections=[
            {
                "department_id": "operaciones",
                "draft_content": "## Cost per event\nUSD $10 per cover.\n",
            },
            {
                "department_id": "procurement",
                "draft_content": "## Estimated ingredient cost based on volume\nUSD $90.\n",
            },
            {
                "department_id": "marketing",
                "draft_content": "Setup in 2 business days.\n",
            },
        ],
        metadata={"estimated_contract_value_usd": 75_000},
        requires_ceo_flag=True,
        ceo_approval={"approval_status": "pending"},
    )
    ids = {c["trigger_id"] for c in surfaced}
    assert ids >= {
        TRIGGER_COST_VS_FEASIBILITY,
        TRIGGER_SETUP_SLA_BREACH,
        TRIGGER_CEO_THRESHOLD,
    }
    resolutions = apply_fixed_arbitration(surfaced)
    assert all(r["llm_resolved"] is False for r in resolutions)
    by_trigger = {r["trigger_id"]: r for r in resolutions}
    assert by_trigger[TRIGGER_COST_VS_FEASIBILITY]["arbiter"] == "Camila Ospina"
    assert by_trigger[TRIGGER_SETUP_SLA_BREACH]["arbiter"] == "Felipe Guerrero"
    assert by_trigger[TRIGGER_CEO_THRESHOLD]["arbiter"] == "Mariana Restrepo"


def test_final_document_matches_context_section_2_3_shape() -> None:
    """CONTEXT §2.3: ticket_id, sections, total_estimated_value, generated_at."""
    text = read_context_company_md()
    assert "FinalDocument" in text
    for field in CONTEXT_FINAL_DOCUMENT_FIELDS:
        assert f"`{field}`" in text or field in text
    assert FINAL_DOCUMENT_CONTEXT_FIELDS == CONTEXT_FINAL_DOCUMENT_FIELDS

    sections = andes_sections()
    approvals = {
        d: {
            "department_id": d,
            "approval_status": "approved",
            "approver": DEPARTMENT_OWNERS[d],
            "approved_at": "2026-01-01T00:00:00Z",
        }
        for d in ANDES_DEPARTMENTS
    }
    for row in sections:
        row["approval_status"] = "approved"
        row["approver"] = approvals[row["department_id"]]["approver"]

    doc = build_final_document(
        ticket_id="ctx-final",
        sections=sections,
        metadata={
            "client_name": "Andes Tech Solutions",
            "estimated_contract_value_usd": 20_000,
        },
        departments_needed=list(ANDES_DEPARTMENTS),
        approvals=approvals,
    )
    assert_final_document_context_shape(doc)
    assert set(CONTEXT_FINAL_DOCUMENT_FIELDS).issubset(doc.keys())
    assert doc["ticket_id"] == "ctx-final"
    assert doc["total_estimated_value"] == 20_000
    assert isinstance(doc["sections"], list) and doc["sections"]
    assert all(s["approval_status"] == "approved" for s in doc["sections"])
    assert {s["department_id"] for s in doc["sections"]} == set(ANDES_DEPARTMENTS)
    # Sign-off names in body must be CONTEXT owners — not invented titles.
    for owner in (
        "Camila Ospina",
        "Felipe Guerrero",
        "Lucía Fernández",
    ):
        assert owner in doc["markdown"]
    assert "VP of Sales" not in doc["markdown"]
    assert "Mariana Restrepo" not in doc["markdown"]  # Andes < $50k — no CEO

    with pytest.raises(ValueError, match="CONTEXT §2.3"):
        assert_final_document_context_shape({"ticket_id": "x", "sections": []})


def test_fixtures_and_ui_use_context_named_owners_only() -> None:
    for row in andes_sections() + sunset_sections():
        assert row["owner"] == CONTEXT_DEPARTMENT_OWNERS[row["department_id"]]
    for decision in simulated_department_approvals(ANDES_DEPARTMENTS):
        assert decision["approver"] == CONTEXT_DEPARTMENT_OWNERS[decision["department_id"]]
    for decision in simulated_department_approvals(SUNSET_DEPARTMENTS):
        assert decision["approver"] == CONTEXT_DEPARTMENT_OWNERS[decision["department_id"]]
    ceo = simulated_ceo_approval()
    assert ceo["approver"] == "Mariana Restrepo"
    assert ceo["department_id"] == "ceo"

    html = UI_UPLOAD.read_text(encoding="utf-8")
    for owner in CONTEXT_DEPARTMENT_OWNERS.values():
        assert owner in html
    assert "Mariana Restrepo" in html
    assert "CONTEXT-company.md" in html


def test_part3_package_does_not_hardcode_generic_approver_ladder() -> None:
    forbidden = re.compile(
        r"""['\"](?:VP of Sales|Legal|General Counsel|CFO|COO|Board of Directors)['\"]"""
    )
    for path in PART3.glob("*.py"):
        if path.name.startswith("test_"):
            continue
        src = re.sub(r"#.*", "", path.read_text(encoding="utf-8"))
        # Forbidden titles may appear only inside CONTEXT_FORBIDDEN / reject paths.
        if path.name in {"approvers.py"}:
            continue
        match = forbidden.search(src)
        assert match is None, f"{path.name} hardcodes generic title {match.group(0)}"
