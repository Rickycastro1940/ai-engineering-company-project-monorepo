"""Evaluate: implementation matches departments + RFP format in CONTEXT-company.md.

Parses CONTEXT §2.1 department table and §2.2–§2.3 RFP format language, then
asserts pipeline constants, classifier behavior, and SQLModel entities agree.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from data.pipelines.rfp_intake import (
    classifier_agent,
    convert_document_to_markdown,
    run_intake_pipeline,
)
from data.pipelines.rfp_intake.constants import (
    CEO_NAME,
    CEO_USD_THRESHOLD,
    DEPARTMENT_CONTRIBUTIONS,
    DEPARTMENT_IDS,
    DEPARTMENT_LABELS,
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_OWNERS,
    RFP_METADATA_FIELDS,
    STATUS_DISCARDED,
    STATUS_INTAKE_COMPLETE,
    TICKET_OWNER,
)
from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_DEPARTMENT_CONTRIBUTIONS,
    CONTEXT_DEPARTMENT_IDS,
    CONTEXT_DEPARTMENT_LABELS,
    CONTEXT_DEPARTMENT_OWNERS,
    CONTEXT_RFP_METADATA_FIELDS,
    CONTEXT_SEED_EXPECTATIONS,
    CONTEXT_SERVICE_TYPES,
    FORBIDDEN_DEPARTMENT_IDS,
)
from services.rfp.models import RfpDepartmentSection, RfpTicket

REPO = Path(__file__).resolve().parents[2]
CONTEXT = REPO / "CONTEXT-company.md"
SEEDS = REPO / "rfp-requests" / "brasaland"
PIPELINE = REPO / "data" / "pipelines" / "rfp_intake"


def _context() -> str:
    assert CONTEXT.is_file()
    return CONTEXT.read_text(encoding="utf-8")


def _parse_context_department_table(text: str) -> list[dict[str, str]]:
    """Parse CONTEXT §2.1 markdown table rows into structured records."""
    # Limit to the §2.1 block (before §2.2) so status-table backticks are ignored.
    start = text.find("### 2.1")
    end = text.find("### 2.2")
    assert start != -1 and end != -1 and end > start
    block = text[start:end]
    rows: list[dict[str, str]] = []
    pattern = re.compile(
        r"\|\s*`(?P<id>[a-z_]+)`\s*\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<owner>[^|]+?)\s*\|\s*(?P<contrib>[^|]+?)\s*\|"
    )
    for match in pattern.finditer(block):
        dept_id = match.group("id").strip()
        if dept_id == "department_id":
            continue
        rows.append(
            {
                "department_id": dept_id,
                "label": match.group("label").strip(),
                "owner": match.group("owner").strip(),
                "contribution": match.group("contrib").strip(),
            }
        )
    return rows


def test_context_section_2_1_table_parses_four_departments() -> None:
    rows = _parse_context_department_table(_context())
    assert [r["department_id"] for r in rows] == [
        "marketing",
        "operaciones",
        "procurement",
        "training",
    ]
    assert rows[0]["owner"] == "Camila Ospina"
    assert rows[1]["owner"] == "Felipe Guerrero"
    assert rows[2]["owner"] == "Lucía Fernández"
    assert rows[3]["owner"] == "Jake Morrison"


def test_implementation_department_ids_owners_labels_match_context_table() -> None:
    rows = _parse_context_department_table(_context())
    parsed_ids = tuple(r["department_id"] for r in rows)
    assert CONTEXT_DEPARTMENT_IDS == parsed_ids
    assert DEPARTMENT_IDS == frozenset(parsed_ids)

    for row in rows:
        dept = row["department_id"]
        assert DEPARTMENT_OWNERS[dept] == row["owner"]
        assert CONTEXT_DEPARTMENT_OWNERS[dept] == row["owner"]
        assert DEPARTMENT_LABELS[dept] == row["label"]
        assert CONTEXT_DEPARTMENT_LABELS[dept] == row["label"]
        impl = DEPARTMENT_CONTRIBUTIONS[dept].rstrip(".")
        ctx = row["contribution"].rstrip(".")
        assert impl == ctx or impl in ctx or ctx in impl


def test_operaciones_spanish_id_not_english_operations() -> None:
    text = _context()
    assert "`operaciones`" in text
    assert DEPARTMENT_OPERACIONES == "operaciones"
    assert "operations" not in DEPARTMENT_IDS
    assert "operations" in FORBIDDEN_DEPARTMENT_IDS
    assert "sales" in FORBIDDEN_DEPARTMENT_IDS


def test_ticket_owner_is_marketing_camila_as_sales() -> None:
    text = _context()
    assert "Camila Ospina" in text
    assert "Marketing" in text and "Sales" in text
    assert TICKET_OWNER == "Camila Ospina"
    assert TICKET_OWNER == DEPARTMENT_OWNERS[DEPARTMENT_MARKETING]


def test_pipeline_code_never_assigns_forbidden_department_ids() -> None:
    pattern = re.compile(
        r"""(?:department_id\s*=\s*|departments_needed\s*=\s*\[|[\"'])("""
        + "|".join(re.escape(b) for b in sorted(FORBIDDEN_DEPARTMENT_IDS))
        + r""")[\"']"""
    )
    for path in PIPELINE.glob("*.py"):
        if path.name == "context_rules.py":
            continue
        stripped = re.sub(r"#.*", "", path.read_text(encoding="utf-8"))
        match = pattern.search(stripped)
        assert match is None, f"{path.name} uses forbidden id {match.group(1)!r}"


def test_context_section_2_2_service_types_mirrored() -> None:
    text = _context()
    for service in ("recurring catering", "concession", "co-branding"):
        assert service in text
        assert service in CONTEXT_SERVICE_TYPES


def test_rfp_format_fields_from_context_2_2_and_2_3() -> None:
    text = _context()
    for phrase in (
        "client name",
        "location",
        "type of service",
        "deadline",
        "budget range",
        "informal letters of intent",
    ):
        assert phrase in text.casefold()

    for field in (
        "client_name",
        "location",
        "service_type",
        "scope",
        "deadline",
        "budget_range",
        "departments_needed",
    ):
        assert f"`{field}`" in text or field in text
        assert field in CONTEXT_RFP_METADATA_FIELDS or field == "departments_needed"
        if field != "departments_needed":
            assert field in RFP_METADATA_FIELDS


def test_classifier_accepts_formal_and_informal_brasaland_rfp_shapes() -> None:
    """CONTEXT §2.2: formal PDFs and informal letters of intent both accepted."""
    formal = classifier_agent(
        convert_document_to_markdown(SEEDS / "CONTEXT-brasaland-request-1.pdf")
    )
    informal = classifier_agent(
        convert_document_to_markdown(SEEDS / "CONTEXT-brasaland-request-2.pdf")
    )
    assert formal.is_valid_rfp and informal.is_valid_rfp
    assert formal.metadata.get("service_type")
    assert informal.metadata.get("service_type")
    formal_svc = (formal.metadata.get("service_type") or "").casefold()
    informal_svc = (informal.metadata.get("service_type") or "").casefold()
    assert "co-brand" in formal_svc or "concession" in formal_svc
    assert "cater" in informal_svc


def test_classifier_rejects_non_brasaland_generic_saas_rfp() -> None:
    decision = classifier_agent(
        """
        REQUEST FOR PROPOSAL
        Client: Acme Cloud Inc
        Proposal Due: 2026-12-01
        Scope: CRM SaaS vendor for ticket routing and SLA dashboards.
        """
    )
    assert decision.is_valid_rfp is False
    assert decision.discard_rule_id == "not_an_rfp"


def test_sqlmodel_entities_cover_context_ticket_and_department_section() -> None:
    for attr in (
        "ticket_id",
        "status",
        "source_pdf_path",
        "created_at",
        "updated_at",
        "metadata_json",
        "readability_json",
    ):
        assert hasattr(RfpTicket, attr)
    for attr in (
        "department_id",
        "key_aspects_json",
        "draft_content",
        "evaluation_results_json",
        "approval_status",
        "approver",
        "approved_at",
    ):
        assert hasattr(RfpDepartmentSection, attr)


def test_ceo_threshold_and_name_match_context() -> None:
    text = _context()
    assert "Mariana Restrepo" in text
    assert "$50,000" in text or "50,000" in text
    assert CEO_NAME == "Mariana Restrepo"
    assert CEO_USD_THRESHOLD == 50_000.0


@pytest.mark.parametrize("filename", sorted(CONTEXT_SEED_EXPECTATIONS))
def test_seed_pdf_outcomes_match_context_section_4(filename: str) -> None:
    expected = CONTEXT_SEED_EXPECTATIONS[filename]
    result = run_intake_pipeline(pdf_path=SEEDS / filename)
    if expected.get("accept"):
        assert result.status == STATUS_INTAKE_COMPLETE
        assert expected["client_substr"] in (result.metadata.get("client_name") or "")
        assert set(result.departments_needed) == set(expected["departments"])
        assert set(result.departments_needed) <= set(CONTEXT_DEPARTMENT_IDS)
        assert result.requires_ceo_approval is expected["requires_ceo_approval"]
        for excluded in expected.get("exclude_departments") or set():
            assert excluded not in result.departments_needed
        for field in ("client_name", "location", "service_type", "deadline"):
            assert field in result.metadata
    else:
        assert result.status == STATUS_DISCARDED
        assert result.discard_reason
        assert result.departments_needed == []


def test_constants_module_reexports_context_rules_not_diverged_copies() -> None:
    assert DEPARTMENT_OWNERS == CONTEXT_DEPARTMENT_OWNERS
    assert DEPARTMENT_LABELS == CONTEXT_DEPARTMENT_LABELS
    assert DEPARTMENT_CONTRIBUTIONS == CONTEXT_DEPARTMENT_CONTRIBUTIONS
    assert RFP_METADATA_FIELDS == CONTEXT_RFP_METADATA_FIELDS
    src = (PIPELINE / "constants.py").read_text(encoding="utf-8")
    assert "from data.pipelines.rfp_intake.context_rules import" in src
    assert "CONTEXT_DEPARTMENT_OWNERS" in src
