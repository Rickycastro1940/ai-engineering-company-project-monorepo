"""Department section generators — produce draft_content from Part 1 key_aspects.

Primary input is Part 1 routing handoff only:
  ticket_id + work_streams[].key_aspects (+ intake metadata / open_questions).

Does **not** re-ingest the raw PDF (no converter import, no pdf_path, no
markdown re-summary). Grounds drafts in handoff metadata + key_aspects +
CONTEXT §5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_CONTRIBUTIONS,
    DEPARTMENT_LABELS,
    DEPARTMENT_OWNERS,
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
)
from data.pipelines.rfp_response.compliance_rules import (
    BRAND_PILLARS,
    MIN_SETUP_BUSINESS_DAYS,
    OFFER_VALIDITY_PHRASE,
)

# Rejected if callers try to smuggle PDF / raw-markdown as generator input
_FORBIDDEN_GENERATOR_KWARGS = frozenset(
    {
        "pdf_path",
        "source_pdf_path",
        "pdf_bytes",
        "raw_pdf",
        "markdown_text",
        "markdown",
        "document_path",
    }
)


@dataclass
class DraftResult:
    department_id: str
    owner: str
    draft_content: str
    iteration: int = 1
    used_feedback: list[str] = field(default_factory=list)


def _client(metadata: dict[str, Any]) -> str:
    return str(metadata.get("client_name") or "the client")


def _location(metadata: dict[str, Any]) -> str:
    return str(metadata.get("location") or "the service location")


def _budget_line(metadata: dict[str, Any]) -> str:
    budget = metadata.get("budget_range")
    value = metadata.get("estimated_contract_value_usd")
    if budget:
        # Always pair USD with COP when stating money (CONTEXT §5) — do not invent FX.
        return (
            f"Commercial envelope as stated in the RFP: {budget}. "
            f"Any firm quote will list both USD $ and COP $ exactly as agreed "
            f"(no currency conversion in this draft)."
        )
    if value is not None:
        return (
            f"Estimated annual value referenced from intake: USD ${float(value):,.0f} "
            f"and the matching COP $ amount to be confirmed with Procurement "
            f"(never invent an exchange rate)."
        )
    return (
        "Pricing will be confirmed with Procurement in both USD $ and COP $; "
        "figures absent from the RFP remain open questions."
    )


def _pillars_paragraph() -> str:
    pillars = ", ".join(BRAND_PILLARS)
    return (
        f"Brasaland delivers on our three pillars — {pillars} — "
        f"in every corporate engagement."
    )


def _aspects_block(key_aspects: list[str]) -> str:
    if not key_aspects:
        return "- (no key aspects supplied from intake)"
    return "\n".join(f"- {a}" for a in key_aspects)


def generate_department_draft(
    *,
    department_id: str,
    metadata: dict[str, Any],
    key_aspects: list[str],
    open_questions: list[str] | None = None,
    feedback: list[str] | None = None,
    iteration: int = 1,
    **kwargs: Any,
) -> DraftResult:
    """Generate a proposal section from Part 1 key_aspects (never the raw PDF)."""
    banned = _FORBIDDEN_GENERATOR_KWARGS.intersection(kwargs)
    if banned:
        raise TypeError(
            "Generators must not re-ingest the raw PDF as primary input; "
            f"forbidden kwargs: {sorted(banned)}. "
            "Use Part 1 handoff ticket_id + work_streams.key_aspects."
        )
    if not key_aspects:
        raise ValueError(
            "Generators require Part 1 work_streams.key_aspects "
            "(synthesizer payload) — PDF is not an accepted substitute"
        )

    # Strip any accidental PDF pointers from metadata before drafting
    clean_meta = {
        k: v
        for k, v in dict(metadata or {}).items()
        if k
        not in {
            "source_pdf_path",
            "pdf_path",
            "markdown_text",
            "markdown",
            "raw_pdf",
        }
    }

    owner = DEPARTMENT_OWNERS.get(department_id, department_id)
    label = DEPARTMENT_LABELS.get(department_id, department_id)
    remit = DEPARTMENT_CONTRIBUTIONS.get(department_id, "")
    client = _client(clean_meta)
    location = _location(clean_meta)
    service = clean_meta.get("service_type") or clean_meta.get("scope") or "corporate catering"
    deadline = clean_meta.get("deadline") or "as agreed"
    fb = list(feedback or [])
    questions = list(open_questions or [])

    lines: list[str] = [
        f"# Proposal section — {label}",
        f"Owner: {owner} (`{department_id}`)",
        f"Client: {client} | Location: {location}",
        f"Service: {service} | Proposal deadline: {deadline}",
        "",
        _pillars_paragraph(),
        f"Offer validity period for this proposal: {OFFER_VALIDITY_PHRASE}.",
        "",
        "## Remit",
        remit or f"Department contribution for {department_id}.",
        "",
        "## Grounded key aspects (from Part 1 intake)",
        _aspects_block(key_aspects),
        "",
    ]

    if department_id == DEPARTMENT_MARKETING:
        lines.extend(
            [
                "## Brand, exclusivity, and offer terms",
                f"Brasaland proposes brand terms tailored to {client}, covering "
                f"co-branding / exclusivity language only where the RFP requests it.",
                f"Offer validity period: {OFFER_VALIDITY_PHRASE}.",
                "Marketing owns the ticket and coordinates Sales-facing follow-up.",
                "",
            ]
        )
    elif department_id == DEPARTMENT_OPERACIONES:
        lines.extend(
            [
                "## Operational feasibility",
                f"Kitchen staffing, setup, and delivery planning for {client} at {location}.",
                f"Setup and delivery commitments are never shorter than "
                f"{MIN_SETUP_BUSINESS_DAYS} business days (Brasaland guideline).",
                "Cost-per-event estimates remain subject to volume figures stated in the RFP; "
                "missing diner counts stay as open questions — we do not invent headcount.",
                "",
            ]
        )
    elif department_id == DEPARTMENT_PROCUREMENT:
        lines.extend(
            [
                "## Ingredient cost and supplier lead times",
                _budget_line(clean_meta),
                "Supplier lead times follow Brasaland procurement procedure; "
                "emergency orders follow documented approval thresholds.",
                "All prices in this section are expressed with both USD $ and COP $ labels "
                "when a monetary figure is stated.",
                "",
            ]
        )
    elif department_id == DEPARTMENT_TRAINING:
        lines.extend(
            [
                "## Training and quality standards",
                "When the RFP requires a new recipe or signature standard, Training "
                "schedules development and certification time before go-live.",
                "If the client requests the existing standard menu only, certification "
                "scope stays limited to brand quality refresh — no invented curriculum.",
                "",
            ]
        )
    else:
        lines.append(f"## Section body for {department_id}\n")

    if questions:
        lines.append("## Open questions (do not invent answers)")
        lines.extend(f"- {q}" for q in questions)
        lines.append("")

    if fb:
        lines.append("## Revisions applied from evaluator feedback")
        lines.extend(f"- Addressed: {item}" for item in fb)
        lines.append("")
        # Reinforce compliance fixes when feedback mentions them
        joined_fb = " ".join(fb).casefold()
        if "pillar" in joined_fb or "brand" in joined_fb:
            lines.append(_pillars_paragraph())
        if "validity" in joined_fb or "30 day" in joined_fb:
            lines.append(f"Offer validity period restated: {OFFER_VALIDITY_PHRASE}.")
        if "setup" in joined_fb or "business day" in joined_fb:
            lines.append(
                f"Reconfirmed: setup/delivery ≥ {MIN_SETUP_BUSINESS_DAYS} business days."
            )
        if "usd" in joined_fb or "cop" in joined_fb or "price" in joined_fb:
            lines.append(
                "Monetary figures restated with both USD $ and COP $ labels "
                "(no invented FX conversion)."
            )
        if "competitor" in joined_fb:
            lines.append("Competitor names removed; proposal uses Brasaland branding only.")
        lines.append("")

    lines.extend(
        [
            "## Closing",
            f"This `{department_id}` section is ready for evaluation "
            f"(readability, relevance, compliance) before Part 3 owner approval.",
        ]
    )

    return DraftResult(
        department_id=department_id,
        owner=owner,
        draft_content="\n".join(lines).strip() + "\n",
        iteration=iteration,
        used_feedback=fb,
    )
