"""Evaluate: implementation respects CONTEXT.md field names, KB topics, restrictions.

Source of truth for Brasaland: repository ``CONTEXT.md`` (same content as
``CONTEXT-company.md``). The harness, APIs, KB allow-list, and guardrails must
not invent alternate fields, topics, or policy wording.
"""

from __future__ import annotations

from pathlib import Path

from data.pipelines import rag as rag_mod
from data.process.rag import COLLECTION_NAME
from services.agent.grounding import ALLOWED_SOURCE_DOCUMENTS, KB_DIR
from services.agent.harness.input import check_input
from services.agent.harness.output import OUTCOME_ALLOW, OUTCOME_BLOCK, OUTCOME_REDACT, check_output
from services.agent.harness.restrictions import (
    ALLERGEN_REFUSAL,
    CONTEXT_COMPANY_PATH,
    CURRENCY_REFUSAL,
    IN_SCOPE_KB_TOPICS,
    NO_CONTEXT_ANSWER,
    REASON_ALLERGEN_ABSOLUTE_SAFETY,
    REASON_CURRENCY_CONVERSION,
    REASON_RAG_INTERNALS,
    REASON_SENSITIVE_CONTEXT_LEAK,
    context_company_text,
)
from services.agent.harness.system_prompt import agent_system_prompt
from services.agent.router import AgentQueryRequest, AgentQueryResponse
from services.api.routers.knowledge import QueryRequest, QueryResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_MD = REPO_ROOT / "CONTEXT.md"
CONTEXT_COMPANY_MD = REPO_ROOT / "CONTEXT-company.md"

# CONTEXT.md knowledge-base table (exact file names).
CONTEXT_KB_FILES = (
    "brasaland-supplier-ordering.en.md",
    "brasaland-waste-protocol.en.md",
    "brasaland-loyalty-program.en.md",
    "brasaland-menu-allergens.en.md",
)

# CONTEXT.md topics column (must appear in harness scope / prompt).
CONTEXT_KB_TOPICS = (
    "Weekly orders",
    "delivery lead times",
    "minimum protein stock",
    "emergency orders",
    "Waste categories",
    "daily logging",
    "escalation thresholds",
    "operational targets",
    "Brasa Points",
    "redemption rules",
    "Dish allergens",
    "customer allergy protocol",
    "gluten-free",
)

# CONTEXT.md RAG / API field and naming constraints.
CONTEXT_FIELD_MARKERS = (
    ("collection", "brasaland_kb"),
    ("company slug", "brasaland"),
    ("knowledge request field", '"question"'),
    ("knowledge response field", '"answer"'),
    ("agent request field", '"question"'),
    ("agent response fields", '"trace_id"'),
)

# CONTEXT.md restrictions (exact wording the harness must enforce).
CONTEXT_RESTRICTIONS = (
    ("never convert", "never convert"),
    ("zero risk", "zero risk"),
    ("100% safe", "100% safe"),
    ("unknown answer", "There is not enough information available."),
    ("no chunks", "chunks"),
    ("no scores", "scores"),
    ("no qdrant payloads", "Qdrant"),
)


def _load_context_md() -> str:
    assert CONTEXT_MD.is_file(), "CONTEXT.md missing at repo root"
    return CONTEXT_MD.read_text(encoding="utf-8")


def test_context_md_and_context_company_md_agree() -> None:
    """Company fork matches CONTEXT.md (same Brasaland field/KB/restriction text)."""
    ctx = _load_context_md()
    company = CONTEXT_COMPANY_MD.read_text(encoding="utf-8")
    assert CONTEXT_COMPANY_PATH == CONTEXT_COMPANY_MD
    assert ctx.strip() == company.strip()
    assert context_company_text().strip() == ctx.strip()


def test_api_field_names_match_context_md() -> None:
    """HTTP contracts use CONTEXT.md field names (question / answer / trace_id)."""
    ctx = _load_context_md()
    for _label, needle in CONTEXT_FIELD_MARKERS:
        assert needle in ctx, f"CONTEXT.md missing {_label}: {needle}"

    # Knowledge API: request {question}, response {answer} only.
    assert "question" in QueryRequest.model_fields
    assert set(QueryRequest.model_fields) == {"question"}
    assert "answer" in QueryResponse.model_fields
    assert set(QueryResponse.model_fields) == {"answer"}
    # Forbid extra fields so chunks/scores/payloads cannot leak via schema.
    assert QueryResponse.model_config.get("extra") == "forbid"

    # Agent API: request {question}; response includes answer + trace_id.
    assert "question" in AgentQueryRequest.model_fields
    assert set(AgentQueryRequest.model_fields) == {"question"}
    agent_fields = set(AgentQueryResponse.model_fields)
    assert {"answer", "trace_id"} <= agent_fields
    assert AgentQueryResponse.model_config.get("extra") == "forbid"

    # Collection / slug from CONTEXT.md.
    assert COLLECTION_NAME == "brasaland_kb"
    assert "brasaland_kb" in ctx
    assert "`brasaland`" in ctx


def test_kb_topics_and_files_match_context_md() -> None:
    """On-disk KB + allow-list match CONTEXT.md knowledge-base table."""
    ctx = _load_context_md()
    for filename in CONTEXT_KB_FILES:
        assert filename in ctx, filename
        path = KB_DIR / filename
        assert path.is_file(), f"missing KB file from CONTEXT.md: {filename}"

    assert ALLOWED_SOURCE_DOCUMENTS == {
        "supplier-ordering",
        "waste-protocol",
        "loyalty-program",
        "menu-allergens",
    }

    prompt = agent_system_prompt(base=rag_mod.SYSTEM_PROMPT)
    for topic in CONTEXT_KB_TOPICS:
        assert topic.casefold() in ctx.casefold(), f"CONTEXT.md missing topic: {topic}"

    # Harness in-scope topics are derived from CONTEXT.md, not invented.
    for required in (
        "supplier ordering",
        "minimum protein stock",
        "emergency orders",
        "waste",
        "brasa points",
        "allergens",
        "gluten-free",
    ):
        assert required in IN_SCOPE_KB_TOPICS, required
        assert required.casefold() in prompt.casefold(), required


def test_key_people_from_context_md_in_prompt_and_scope() -> None:
    ctx = _load_context_md()
    prompt = agent_system_prompt(base=rag_mod.SYSTEM_PROMPT)
    for person, role in (
        ("Mariana", "CEO"),
        ("Felipe Guerrero", "Operations Director"),
        ("Lucía Fernández", "Procurement Manager"),
    ):
        assert person in ctx and role in ctx
        assert person in prompt
    assert "500 USD" in ctx and "500 USD" in prompt
    assert "Colombia" in ctx and "Florida" in ctx
    assert "Colombia" in prompt and "Florida" in prompt
    assert "salesperson perspective" in ctx.casefold()
    assert "salesperson perspective" in prompt.casefold()


def test_context_md_restrictions_enforced_by_guardrails() -> None:
    """Restrictions in CONTEXT.md are code gates — not prompt-only suggestions."""
    ctx = _load_context_md()
    prompt = agent_system_prompt(base=rag_mod.SYSTEM_PROMPT)

    for label, needle in CONTEXT_RESTRICTIONS:
        assert needle.casefold() in ctx.casefold(), f"CONTEXT.md missing {label}"
        assert needle.casefold() in prompt.casefold(), f"prompt missing {label}"

    assert NO_CONTEXT_ANSWER == "There is not enough information available."
    assert NO_CONTEXT_ANSWER in ctx

    # Currency — never convert.
    blocked = check_input("Please convert 500 USD to COP.")
    assert blocked.allowed is False
    assert blocked.reason == REASON_CURRENCY_CONVERSION
    redacted = check_output("500 USD converts to about 2,000,000 COP.")
    assert redacted.outcome == OUTCOME_REDACT
    assert redacted.reason == REASON_CURRENCY_CONVERSION
    assert redacted.answer == CURRENCY_REFUSAL

    # Allergens — never "zero risk" / "100% safe".
    allergen_in = check_input("Is the kitchen 100% safe for nut allergies?")
    assert allergen_in.allowed is False
    assert allergen_in.reason == REASON_ALLERGEN_ABSOLUTE_SAFETY
    allergen_out = check_output("There is zero risk of cross-contamination.")
    assert allergen_out.outcome == OUTCOME_REDACT
    assert allergen_out.reason == REASON_ALLERGEN_ABSOLUTE_SAFETY
    assert allergen_out.answer == ALLERGEN_REFUSAL

    # Never chunks / scores / Qdrant payloads in user-facing answers.
    internals = check_output(
        "Protein stock is 3 days. Retrieved chunks scored 0.91 from Qdrant."
    )
    assert internals.outcome == OUTCOME_REDACT
    assert internals.reason == REASON_RAG_INTERNALS
    assert "qdrant" not in internals.answer.casefold()
    assert "chunks" not in internals.answer.casefold()

    # Sensitive CONTEXT field names (collection / slug / API paths) stay private.
    leak = check_output(
        "Vectors live in collection brasaland_kb with company slug brasaland."
    )
    assert leak.outcome == OUTCOME_BLOCK
    assert leak.reason == REASON_SENSITIVE_CONTEXT_LEAK

    # Grounded company answer still allowed.
    ok = check_output(
        "Emergency orders over 500 USD need approval from Lucía Fernández."
    )
    assert ok.outcome == OUTCOME_ALLOW


def test_suite_fails_if_context_md_fields_or_topics_diverge() -> None:
    """Regression: inventing alternate KB files or API fields must fail this eval."""
    ctx = _load_context_md()
    # Must not silently accept a different collection name.
    assert COLLECTION_NAME == "brasaland_kb"
    assert COLLECTION_NAME in ctx
    # Must not expand beyond the four CONTEXT.md KB documents.
    assert len(ALLOWED_SOURCE_DOCUMENTS) == 4
    for stem in ALLOWED_SOURCE_DOCUMENTS:
        assert f"brasaland-{stem}.en.md" in CONTEXT_KB_FILES
        assert f"brasaland-{stem}.en.md" in ctx
    # Must keep CONTEXT unknown-answer wording exact.
    assert NO_CONTEXT_ANSWER in ctx
