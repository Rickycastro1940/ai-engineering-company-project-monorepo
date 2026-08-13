"""Evaluate: RFP intake must match CONTEXT-company.md (not a generic RFP bot)."""

from __future__ import annotations

import re
from pathlib import Path

from data.pipelines.rfp_intake import classifier_agent, convert_document_to_markdown, run_intake_pipeline
from data.pipelines.rfp_intake.constants import (
    CEO_NAME,
    CEO_USD_THRESHOLD,
    DEPARTMENT_IDS,
    DEPARTMENT_LABELS,
    DEPARTMENT_OWNERS,
    RFP_METADATA_FIELDS,
)
from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_DEPARTMENT_IDS,
    CONTEXT_DEPARTMENT_LABELS,
    CONTEXT_DEPARTMENT_OWNERS,
    CONTEXT_SEED_EXPECTATIONS,
    FORBIDDEN_DEPARTMENT_IDS,
    select_departments_from_content,
)

REPO = Path(__file__).resolve().parents[2]
CONTEXT = REPO / "CONTEXT-company.md"
SEEDS = REPO / "rfp-requests" / "brasaland"


def _context_text() -> str:
    assert CONTEXT.is_file(), "CONTEXT-company.md missing"
    return CONTEXT.read_text(encoding="utf-8")


def test_context_lists_exact_department_ids() -> None:
    text = _context_text()
    for dept_id in CONTEXT_DEPARTMENT_IDS:
        assert f"`{dept_id}`" in text or f"| `{dept_id}`" in text or dept_id in text
    # Spanish id must appear (not English "operations" as the code id)
    assert "operaciones" in text
    assert DEPARTMENT_IDS == frozenset(CONTEXT_DEPARTMENT_IDS)


def test_constants_owners_and_labels_match_context_table() -> None:
    text = _context_text()
    for dept_id, owner in CONTEXT_DEPARTMENT_OWNERS.items():
        assert owner in text, f"{owner} missing from CONTEXT"
        assert DEPARTMENT_OWNERS[dept_id] == owner
    for dept_id, label in CONTEXT_DEPARTMENT_LABELS.items():
        assert label in text or label.replace(" and ", " ") in text
        assert DEPARTMENT_LABELS[dept_id] == label
    assert CEO_NAME == "Mariana Restrepo"
    assert CEO_NAME in text
    assert CEO_USD_THRESHOLD == 50_000.0
    assert "50,000" in text or "50000" in text or "$50,000" in text


def test_no_forbidden_generic_department_ids_in_pipeline_code() -> None:
    root = REPO / "data" / "pipelines" / "rfp_intake"
    # Match department_id assignments / list literals, not prose comments.
    pattern = re.compile(
        r"""(?:department_id\s*=\s*|departments_needed\s*=\s*\[|[\"'])("""
        + "|".join(re.escape(b) for b in sorted(FORBIDDEN_DEPARTMENT_IDS))
        + r""")[\"']"""
    )
    for path in root.glob("*.py"):
        if path.name == "context_rules.py":
            continue
        src = path.read_text(encoding="utf-8")
        # Strip comments before scanning
        stripped = re.sub(r"#.*", "", src)
        match = pattern.search(stripped)
        assert match is None, f"{path.name} uses forbidden department id {match.group(1)!r}"


def test_rfp_metadata_fields_match_context_section_2_3() -> None:
    text = _context_text()
    for field in (
        "client_name",
        "location",
        "service_type",
        "scope",
        "deadline",
        "budget_range",
        "departments_needed",
    ):
        assert field in text
        assert field in RFP_METADATA_FIELDS or field == "departments_needed"


def test_seed_classification_matches_context_section_4() -> None:
    for filename, expected in CONTEXT_SEED_EXPECTATIONS.items():
        pdf = SEEDS / filename
        assert pdf.is_file(), filename
        result = run_intake_pipeline(pdf_path=pdf)
        if expected.get("accept"):
            assert result.status == "intake_complete", filename
            client = result.metadata.get("client_name") or ""
            assert expected["client_substr"] in client, (filename, client)
            assert set(result.departments_needed) == set(expected["departments"]), (
                filename,
                result.departments_needed,
            )
            for excluded in expected.get("exclude_departments") or set():
                assert excluded not in result.departments_needed
            assert result.requires_ceo_approval is expected["requires_ceo_approval"]
            # Only CONTEXT department ids
            assert set(result.departments_needed) <= set(CONTEXT_DEPARTMENT_IDS)
        else:
            assert result.status == "discarded", filename
            assert result.discard_reason
            assert result.departments_needed == []


def test_classifier_rejects_non_brasaland_generic_rfp_noise() -> None:
    # Generic SaaS RFP without catering/concession/co-branding must not pass
    md = """
    REQUEST FOR PROPOSAL
    Issuing Organization: Acme Cloud Inc
    Proposal Due Date: 2026-12-01
    We need a CRM SaaS vendor for ticket routing and SLA dashboards.
    """
    decision = classifier_agent(md)
    assert decision.is_valid_rfp is False
    assert decision.discard_rule_id == "not_an_rfp"


def test_select_departments_standard_menu_skips_training() -> None:
    text = "weekly catering for 220 employees using the standard menu contrato por un año"
    depts = select_departments_from_content(text.casefold(), service_type="recurring catering")
    assert depts == ["marketing", "operaciones", "procurement"]
    assert "training" not in depts


def test_select_departments_signature_menu_includes_training() -> None:
    text = "co-branded concession with exclusivity and a new signature menu across resorts"
    depts = select_departments_from_content(text.casefold(), service_type="co-branding")
    assert "training" in depts
    assert set(depts) == {"marketing", "operaciones", "procurement", "training"}


def test_context_file_mentions_seed_pdfs_and_marketing_as_sales() -> None:
    text = _context_text()
    assert "Camila Ospina" in text
    assert "Marketing" in text
    assert "Sales" in text  # Marketing is "Sales" for this milestone
    assert "CONTEXT-brasaland-request-1.pdf" in text
    assert "CONTEXT-brasaland-request-3.pdf" in text
    assert "franchise" in text.casefold() or "franquicia" in text.casefold()
