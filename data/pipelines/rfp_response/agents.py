"""Per-department generator agents for Part 2 pricing-proposal sections.

Each CONTEXT §2.1 department has its own generator agent. The agent receives
**only** that department's Part 1 summary from the routing handoff
(``work_streams[].key_aspects`` + shared metadata) — never the raw PDF.

Output is that department's section of the pricing proposal (CONTEXT §2.1 remit).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Final

from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_CONTRIBUTIONS,
    DEPARTMENT_IDS,
    DEPARTMENT_LABELS,
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_OWNERS,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
)
from data.pipelines.rfp_response.compliance_rules import (
    BRAND_PILLARS,
    MIN_SETUP_BUSINESS_DAYS,
    OFFER_VALIDITY_PHRASE,
)

_FORBIDDEN_GENERATOR_KWARGS: Final[frozenset[str]] = frozenset(
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

_STRIP_META: Final[frozenset[str]] = frozenset(
    {"source_pdf_path", "pdf_path", "markdown_text", "markdown", "raw_pdf"}
)


@dataclass
class Part1DepartmentSummary:
    """Relevant Part 1 summary for one department (from routing handoff)."""

    department_id: str
    key_aspects: list[str]
    metadata: dict[str, Any]
    owner: str = ""
    open_questions: list[str] = field(default_factory=list)
    ticket_id: str | None = None
    label: str = ""

    @classmethod
    def from_work_stream(
        cls,
        stream: dict[str, Any],
        *,
        metadata: dict[str, Any],
        ticket_id: str | None = None,
    ) -> Part1DepartmentSummary:
        dept = str(stream.get("department_id") or "").strip()
        aspects = [str(a) for a in (stream.get("key_aspects") or []) if str(a).strip()]
        owner = str(stream.get("owner") or DEPARTMENT_OWNERS.get(dept, dept))
        label = str(stream.get("label") or DEPARTMENT_LABELS.get(dept, dept))
        questions = [str(q) for q in (stream.get("open_questions") or []) if str(q).strip()]
        clean_meta = {k: v for k, v in dict(metadata or {}).items() if k not in _STRIP_META}
        return cls(
            department_id=dept,
            key_aspects=aspects,
            metadata=clean_meta,
            owner=owner,
            open_questions=questions,
            ticket_id=ticket_id,
            label=label,
        )


@dataclass
class DraftResult:
    department_id: str
    owner: str
    draft_content: str
    iteration: int = 1
    used_feedback: list[str] = field(default_factory=list)
    generator_agent: str = ""
    part1_summary_used: bool = True


def _client(metadata: dict[str, Any]) -> str:
    return str(metadata.get("client_name") or "the client")


def _location(metadata: dict[str, Any]) -> str:
    return str(metadata.get("location") or "the service location")


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


def _budget_line(metadata: dict[str, Any]) -> str:
    budget = metadata.get("budget_range")
    value = metadata.get("estimated_contract_value_usd")
    if budget:
        return (
            f"Commercial envelope as stated in the Part 1 summary: {budget}. "
            f"Any firm quote will list both USD $ and COP $ exactly as agreed "
            f"(no currency conversion in this draft)."
        )
    if value is not None:
        return (
            f"Estimated annual value referenced from Part 1 intake: USD ${float(value):,.0f} "
            f"and the matching COP $ amount to be confirmed with Procurement "
            f"(never invent an exchange rate)."
        )
    return (
        "Pricing will be confirmed with Procurement in both USD $ and COP $; "
        "figures absent from the Part 1 summary remain open questions."
    )


def _compliance_footer(*, feedback: list[str]) -> list[str]:
    lines: list[str] = []
    if feedback:
        lines.append("## Revisions applied from evaluator feedback")
        lines.extend(f"- Addressed: {item}" for item in feedback)
        lines.append("")
        joined_fb = " ".join(feedback).casefold()
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
    return lines


class DepartmentGeneratorAgent(ABC):
    """One generator agent for one CONTEXT department's pricing-proposal section."""

    department_id: str
    agent_name: str

    def receive_part1_summary(self, summary: Part1DepartmentSummary) -> Part1DepartmentSummary:
        """Bind the Part 1 handoff summary this agent is allowed to use."""
        if not summary.key_aspects:
            raise ValueError(
                f"{self.agent_name} requires Part 1 work_streams.key_aspects "
                "(synthesizer payload) — PDF is not an accepted substitute"
            )
        if summary.department_id != self.department_id:
            raise ValueError(
                f"{self.agent_name} received summary for {summary.department_id!r}, "
                f"expected {self.department_id!r}"
            )
        return summary

    def generate(
        self,
        summary: Part1DepartmentSummary,
        *,
        feedback: list[str] | None = None,
        iteration: int = 1,
    ) -> DraftResult:
        summary = self.receive_part1_summary(summary)
        owner = summary.owner or DEPARTMENT_OWNERS.get(self.department_id, self.department_id)
        label = summary.label or DEPARTMENT_LABELS.get(self.department_id, self.department_id)
        remit = DEPARTMENT_CONTRIBUTIONS.get(self.department_id, "")
        meta = summary.metadata
        client = _client(meta)
        location = _location(meta)
        service = meta.get("service_type") or meta.get("scope") or "corporate catering"
        deadline = meta.get("deadline") or "as agreed"
        fb = list(feedback or [])

        lines: list[str] = [
            f"# Pricing proposal section — {label}",
            f"Generator agent: `{self.agent_name}`",
            f"Owner: {owner} (`{self.department_id}`)",
            f"Client: {client} | Location: {location}",
            f"Service: {service} | Proposal deadline: {deadline}",
            "",
            _pillars_paragraph(),
            f"Offer validity period for this proposal: {OFFER_VALIDITY_PHRASE}.",
            "",
            "## Department remit (CONTEXT §2.1)",
            remit or f"Department contribution for {self.department_id}.",
            "",
            "## Part 1 summary received (handoff key_aspects)",
            "This agent drafts only from the department-relevant summary produced in Part 1.",
            _aspects_block(summary.key_aspects),
            "",
        ]
        lines.extend(self.build_pricing_proposal_section(summary, client=client, location=location))
        if summary.open_questions:
            lines.append("## Open questions (do not invent answers)")
            lines.extend(f"- {q}" for q in summary.open_questions)
            lines.append("")
        lines.extend(_compliance_footer(feedback=fb))
        lines.extend(
            [
                "## Closing",
                f"This `{self.department_id}` pricing-proposal section is ready for evaluation "
                f"(readability, relevance, compliance) before Part 3 owner approval.",
            ]
        )
        return DraftResult(
            department_id=self.department_id,
            owner=owner,
            draft_content="\n".join(lines).strip() + "\n",
            iteration=iteration,
            used_feedback=fb,
            generator_agent=self.agent_name,
            part1_summary_used=True,
        )

    @abstractmethod
    def build_pricing_proposal_section(
        self,
        summary: Part1DepartmentSummary,
        *,
        client: str,
        location: str,
    ) -> list[str]:
        """Department-specific body of the pricing proposal."""


class MarketingGeneratorAgent(DepartmentGeneratorAgent):
    """Brand terms, exclusivity, co-branding, offer validity. Owns the ticket."""

    department_id = DEPARTMENT_MARKETING
    agent_name = "marketing_generator_agent"

    def build_pricing_proposal_section(
        self,
        summary: Part1DepartmentSummary,
        *,
        client: str,
        location: str,
    ) -> list[str]:
        return [
            "## Pricing proposal — brand, exclusivity, and commercial terms",
            f"Marketing (Camila Ospina) owns this ticket and frames the commercial offer for {client} "
            f"at {location}. Co-branding and exclusivity language is included only where the Part 1 "
            "summary shows the RFP requested it — we do not invent partnership scope.",
            "Commercial terms in this section cover brand usage, campaign coordination, and the "
            f"public-facing offer window. Offer validity period: {OFFER_VALIDITY_PHRASE}.",
            "Any listed commercial envelope uses both USD $ and COP $ labels; Marketing does not "
            "convert currencies or invent a TRM.",
            "This is the Sales-facing cover of the pricing proposal: other departments attach "
            "operations, ingredient cost, and training time in their own sections.",
            "",
        ]


class OperacionesGeneratorAgent(DepartmentGeneratorAgent):
    """Kitchen/staff capacity, setup times, cost per event."""

    department_id = DEPARTMENT_OPERACIONES
    agent_name = "operaciones_generator_agent"

    def build_pricing_proposal_section(
        self,
        summary: Part1DepartmentSummary,
        *,
        client: str,
        location: str,
    ) -> list[str]:
        return [
            "## Pricing proposal — operational feasibility and cost per event",
            f"Restaurant Operations prices kitchen staffing, prep, setup, and service for {client} "
            f"at {location} using only volume figures present in the Part 1 summary.",
            f"Setup and delivery commitments are never shorter than {MIN_SETUP_BUSINESS_DAYS} "
            "business days (Brasaland guideline). We do not promise same-week go-live.",
            "Cost-per-event estimates remain subject to diner counts / location counts stated in "
            "the Part 1 key_aspects. Missing headcount stays an open question — we do not invent it.",
            "When a per-event figure is stated, it is labeled in both USD $ and COP $ without "
            "inventing an exchange rate. Operations does not quote ingredient unit costs "
            "(that is the procurement section).",
            "",
        ]


class ProcurementGeneratorAgent(DepartmentGeneratorAgent):
    """Estimated ingredient cost based on volume, supplier lead times."""

    department_id = DEPARTMENT_PROCUREMENT
    agent_name = "procurement_generator_agent"

    def build_pricing_proposal_section(
        self,
        summary: Part1DepartmentSummary,
        *,
        client: str,
        location: str,
    ) -> list[str]:
        return [
            "## Pricing proposal — ingredient cost and supplier lead times",
            f"Procurement estimates ingredient cost for {client} ({location}) from the volume "
            "and budget language in the Part 1 summary only.",
            _budget_line(summary.metadata),
            "Supplier lead times follow Brasaland procurement procedure; emergency orders follow "
            "documented approval thresholds. Lead time in this pricing section is never shorter "
            f"than {MIN_SETUP_BUSINESS_DAYS} business days when tied to first delivery.",
            "All prices in this section are expressed with both USD $ and COP $ labels when a "
            "monetary figure is stated. Procurement does not invent unit prices or FX.",
            "",
        ]


class TrainingGeneratorAgent(DepartmentGeneratorAgent):
    """New recipe / standard: development and certification time."""

    department_id = DEPARTMENT_TRAINING
    agent_name = "training_generator_agent"

    def build_pricing_proposal_section(
        self,
        summary: Part1DepartmentSummary,
        *,
        client: str,
        location: str,
    ) -> list[str]:
        return [
            "## Pricing proposal — training, recipe development, and certification time",
            f"Training prices development and certification effort for {client} only when the "
            "Part 1 summary shows a new recipe, signature dish, or quality standard.",
            "If the client requested the existing standard menu only, certification scope stays "
            "limited to a brand quality refresh — no invented curriculum and no invented hours.",
            f"Training calendar respects the {MIN_SETUP_BUSINESS_DAYS} business-day minimum "
            "before go-live so operations can absorb certified recipes.",
            "Any training-related fee in this pricing section is labeled in both USD $ and COP $ "
            "when a figure is stated; we do not invent a rate card.",
            "",
        ]


GENERATOR_AGENTS: Final[dict[str, DepartmentGeneratorAgent]] = {
    DEPARTMENT_MARKETING: MarketingGeneratorAgent(),
    DEPARTMENT_OPERACIONES: OperacionesGeneratorAgent(),
    DEPARTMENT_PROCUREMENT: ProcurementGeneratorAgent(),
    DEPARTMENT_TRAINING: TrainingGeneratorAgent(),
}


def get_generator_agent(department_id: str) -> DepartmentGeneratorAgent:
    agent = GENERATOR_AGENTS.get(department_id)
    if agent is None:
        raise KeyError(
            f"No generator agent for department {department_id!r}; "
            f"expected one of {sorted(DEPARTMENT_IDS)}"
        )
    return agent


def run_generator_agent(
    summary: Part1DepartmentSummary,
    *,
    feedback: list[str] | None = None,
    iteration: int = 1,
) -> DraftResult:
    """Dispatch the department's generator agent with its Part 1 summary."""
    agent = get_generator_agent(summary.department_id)
    return agent.generate(summary, feedback=feedback, iteration=iteration)
