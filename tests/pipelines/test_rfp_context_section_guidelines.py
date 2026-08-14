"""Company guidelines + section format must match CONTEXT-company.md.

A generic SaaS RFP evaluator/generator (SOC 2, SLA credits, Salesforce, …)
is not accepted. Rules and headings are parsed from CONTEXT §2.1 and §5.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_CONTRIBUTIONS,
    DEPARTMENT_IDS,
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_OWNERS,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
)
from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_BRAND_PILLARS,
    CONTEXT_CEO_NAME,
    CONTEXT_CEO_USD_THRESHOLD,
    CONTEXT_MIN_SETUP_BUSINESS_DAYS,
    CONTEXT_OFFER_VALIDITY_PHRASE,
    CONTEXT_SECTION_5_GUIDELINES,
    CONTEXT_SECTION_5_TITLE,
    CONTEXT_SECTION_REQUIRED_HEADINGS,
    parse_context_department_table,
    parse_context_section_5_bullets,
    read_context_company_md,
    section_headings_from_contribution,
)
from data.pipelines.rfp_response.compliance_rules import (
    BRAND_PILLARS,
    CEO_NAME,
    CEO_USD_THRESHOLD,
    CONTEXT_SECTION_5_RULES,
    FORBIDDEN_COMPETITOR_NAMES,
    MIN_SETUP_BUSINESS_DAYS,
    OFFER_VALIDITY_PHRASE,
    SECTION_REQUIRED_HEADINGS,
)
from data.pipelines.rfp_response.evaluators import evaluate_compliance, evaluate_section
from data.pipelines.rfp_response.generator import generate_department_draft

REPO = Path(__file__).resolve().parents[2]
CONTEXT = REPO / "CONTEXT-company.md"


def test_context_section_5_bullets_match_evaluator_catalog() -> None:
    """Compliance guidelines are the six CONTEXT §5 bullets, not a generic policy set."""
    text = read_context_company_md()
    assert CONTEXT.is_file()
    assert CONTEXT_SECTION_5_TITLE in text
    bullets = parse_context_section_5_bullets(text)
    assert len(bullets) == 6
    assert bullets == CONTEXT_SECTION_5_GUIDELINES
    assert tuple(r["guideline"] for r in CONTEXT_SECTION_5_RULES) == bullets

    section = text.split("## 5. Business Constraints")[1].split("## 6.")[0]
    assert "COP" in section and "USD" in section
    for pillar in CONTEXT_BRAND_PILLARS:
        assert pillar in section.casefold()
    assert "10 business days" in section
    assert "competitors by name" in section
    assert "30 days from issuance" in section
    assert "$50,000" in section or "50,000" in section
    assert BRAND_PILLARS == CONTEXT_BRAND_PILLARS
    assert MIN_SETUP_BUSINESS_DAYS == CONTEXT_MIN_SETUP_BUSINESS_DAYS == 10
    assert OFFER_VALIDITY_PHRASE == CONTEXT_OFFER_VALIDITY_PHRASE
    assert CEO_USD_THRESHOLD == CONTEXT_CEO_USD_THRESHOLD == 50_000.0
    assert CEO_NAME == CONTEXT_CEO_NAME == "Mariana Restrepo"


def test_section_headings_parsed_from_context_2_1_contribution_column() -> None:
    """Expected section format is the §2.1 contribution column, not a generic outline."""
    rows = parse_context_department_table()
    assert [r["department_id"] for r in rows] == [
        "marketing",
        "operaciones",
        "procurement",
        "training",
    ]
    for row in rows:
        dept = row["department_id"]
        from_file = section_headings_from_contribution(dept, row["contribution"])
        from_constants = CONTEXT_SECTION_REQUIRED_HEADINGS[dept]
        assert from_file == from_constants
        assert SECTION_REQUIRED_HEADINGS[dept] == from_file
        for heading in from_file:
            assert heading.casefold() in row["contribution"].casefold() or all(
                token in row["contribution"].casefold()
                for token in heading.casefold().split()[:2]
            )

    assert CONTEXT_SECTION_REQUIRED_HEADINGS[DEPARTMENT_MARKETING] == (
        "Brand terms",
        "Exclusivity",
        "Co-branding",
        "Offer validity period",
    )
    assert CONTEXT_SECTION_REQUIRED_HEADINGS[DEPARTMENT_OPERACIONES] == (
        "Kitchen/staff capacity",
        "Setup times",
        "Cost per event",
    )
    assert CONTEXT_SECTION_REQUIRED_HEADINGS[DEPARTMENT_PROCUREMENT] == (
        "Estimated ingredient cost based on volume",
        "Supplier lead times",
    )
    assert CONTEXT_SECTION_REQUIRED_HEADINGS[DEPARTMENT_TRAINING] == (
        "New recipe or standard",
        "Development and certification time needed",
    )


@pytest.mark.parametrize("department_id", sorted(DEPARTMENT_IDS))
def test_generated_section_uses_context_2_1_headings_and_owner(department_id: str) -> None:
    draft = generate_department_draft(
        department_id=department_id,
        metadata={
            "client_name": "Sunset Bay Resorts",
            "location": "Florida",
            "service_type": "co-branded concession",
            "deadline": "2026-09-01",
            "budget_range": "USD $60,000–75,000 / year",
            "estimated_contract_value_usd": 75_000,
            "requires_ceo_approval": True,
        },
        key_aspects=[
            DEPARTMENT_CONTRIBUTIONS[department_id],
            "Sunset Bay Resorts co-branded concession in Florida",
        ],
    ).draft_content
    text = draft.casefold()
    owner = DEPARTMENT_OWNERS[department_id]
    assert owner in draft
    assert f"`{department_id}`" in draft or department_id in text
    for heading in SECTION_REQUIRED_HEADINGS[department_id]:
        assert f"## {heading}" in draft, f"{department_id} missing heading {heading!r}"
    for pillar in BRAND_PILLARS:
        assert pillar in text
    assert OFFER_VALIDITY_PHRASE.casefold() in text
    assert CEO_NAME in draft
    assert "## SLA credits" not in draft
    assert "## SOC 2" not in draft
    assert "## Implementation timeline" not in draft


def test_relevance_rejects_generic_saas_section_missing_context_format() -> None:
    generic = """
# Executive summary
## Implementation timeline
## SLA credits
## SOC 2 Type II
Client: Andes Tech. This operaciones memo covers a generic SaaS rollout.
consistent quality warm experience speed of service.
Offer validity period: 30 days from issuance. USD $1 and COP $1.
Part 1 summary received (handoff key_aspects)
- Operational feasibility for Andes Tech @ Medellín
"""
    result = evaluate_section(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content=generic,
        key_aspects=["Operational feasibility for Andes Tech @ Medellín"],
        metadata={"client_name": "Andes Tech", "location": "Medellín"},
    )
    assert result.relevance.passed is False
    joined = " ".join(result.relevance.failures).casefold()
    assert "context §2.1" in joined or "heading" in joined or "owner" in joined
    assert result.passed is False


def test_compliance_does_not_use_generic_saas_vendor_list() -> None:
    """Salesforce/Oracle are not Brasaland competitors; §5 names restaurant rivals."""
    for saas in ("salesforce", "oracle", "servicenow", "aws"):
        assert saas not in FORBIDDEN_COMPETITOR_NAMES
    draft = (
        "Brasaland delivers consistent quality, warm experience, speed of service. "
        "Offer validity period: 30 days from issuance. "
        "Setup in 12 business days. Price USD $100 and COP $400000. "
        "Integration with Salesforce is out of scope for this catering offer."
    )
    result = evaluate_compliance(draft, metadata={})
    assert "no_competitors" not in result.rule_ids
    assert result.passed is True


def test_compliance_flags_brasaland_competitor_and_short_setup() -> None:
    bad = (
        "We beat El Corral on price. Setup in 3 business days. "
        "Price USD $100 only."
    )
    result = evaluate_compliance(bad, metadata={})
    assert result.passed is False
    assert "no_competitors" in result.rule_ids
    assert "min_setup_business_days" in result.rule_ids


def test_ceo_threshold_requires_mariana_restrepo_in_generated_content() -> None:
    missing = (
        "consistent quality, warm experience, speed of service. "
        "Offer validity period: 30 days from issuance. "
        "USD $60,000 and COP $ labels. Setup 12 business days."
    )
    failed = evaluate_compliance(
        missing, metadata={"estimated_contract_value_usd": 65_000}
    )
    assert failed.passed is False
    assert "ceo_threshold" in failed.rule_ids
    assert CEO_NAME.split()[0].casefold() in " ".join(failed.failures).casefold()

    ok = generate_department_draft(
        department_id=DEPARTMENT_MARKETING,
        metadata={
            "client_name": "Sunset Bay",
            "location": "Florida",
            "estimated_contract_value_usd": 65_000,
            "requires_ceo_approval": True,
        },
        key_aspects=["Brand exclusivity for Sunset Bay"],
    ).draft_content
    flagged = evaluate_compliance(
        ok, metadata={"estimated_contract_value_usd": 65_000}
    )
    assert flagged.passed is True
    assert "ceo_threshold" in flagged.rule_ids
    assert CEO_NAME in ok


def test_compliance_checkers_cover_every_context_section_5_rule() -> None:
    from data.pipelines.rfp_response import evaluators as ev_mod

    assert set(ev_mod._COMPLIANCE_CHECKERS) == {r["id"] for r in CONTEXT_SECTION_5_RULES}
    src = Path(ev_mod.__file__).read_text(encoding="utf-8")
    assert "CONTEXT_SECTION_5_RULES" in src
    assert "SOC 2" not in src
    assert "GDPR" not in src
    assert "ISO 27001" not in src
