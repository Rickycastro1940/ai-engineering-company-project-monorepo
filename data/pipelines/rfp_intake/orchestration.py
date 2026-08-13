"""Department orchestration — orchestrator → workers → synthesizer (Part 1).

After the classifier accepts an RFP:
1. Orchestrator decomposes work into per-department subtasks.
2. Each worker receives shared metadata + a department-relevant extract only,
   produces ``key_aspects`` (and ``open_questions`` for missing figures — never invent).
3. Synthesizer builds a Sales-facing summary (what to ask whom) and a Part 2 handoff.
4. Pipeline sets ticket status ``intake_complete``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from data.pipelines.rfp_intake.constants import (
    CEO_NAME,
    CEO_USD_THRESHOLD,
    DEPARTMENT_IDS,
    DEPARTMENT_LABELS,
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_OWNERS,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
    STATUS_INTAKE_COMPLETE,
)

logger = logging.getLogger(__name__)

# Patterns that look like invented absolute claims — workers must not emit these
_INVENTED_FIGURE_PATTERNS = (
    re.compile(r"\bexactly\s+\d[\d,]*\b", re.I),
    re.compile(r"\bwe will charge\s+\$\d", re.I),
    re.compile(r"\bguaranteed\s+\d+", re.I),
)

_DEPT_KEYWORDS: dict[str, tuple[str, ...]] = {
    DEPARTMENT_MARKETING: (
        "brand",
        "exclusiv",
        "co-brand",
        "marketing",
        "validity",
        "marca",
        "crm",
        "partnership",
    ),
    DEPARTMENT_OPERACIONES: (
        "kitchen",
        "staff",
        "setup",
        "operat",
        "logíst",
        "logist",
        "capacity",
        "event",
        "delivery",
        "diners",
        "employees",
        "resort",
        "oficina",
        "office",
    ),
    DEPARTMENT_PROCUREMENT: (
        "cost",
        "budget",
        "supplier",
        "ingredient",
        "volume",
        "USD",
        "COP",
        "precio",
        "contract value",
        "annual",
    ),
    DEPARTMENT_TRAINING: (
        "recipe",
        "signature menu",
        "training",
        "standard",
        "certif",
        "menú de autor",
        "nuevo",
        "quality",
    ),
}


@dataclass
class DepartmentSubtask:
    """Orchestrator output — one unit of work for a department worker."""

    department_id: str
    owner: str
    label: str
    excerpt: str
    shared_metadata: dict[str, Any]


@dataclass
class WorkerResult:
    """Worker output — key_aspects for Postgres DepartmentSection + open questions."""

    department_id: str
    owner: str
    key_aspects: list[str]
    open_questions: list[str] = field(default_factory=list)
    excerpt_chars: int = 0


@dataclass
class SynthesisResult:
    """Synthesizer output — Sales-facing summary + Part 2 handoff."""

    intake_summary: str
    ask_whom: list[dict[str, str]]
    part2_handoff: dict[str, Any]
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


def build_department_excerpt(
    markdown_text: str, department_id: str, *, max_chars: int = 2000
) -> str:
    """Return a dept-relevant slice of the RFP markdown (not the full document)."""
    text = markdown_text or ""
    keywords = _DEPT_KEYWORDS.get(department_id, ())
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    scored: list[tuple[int, str]] = []
    for para in paragraphs:
        low = para.casefold()
        score = sum(1 for k in keywords if k.casefold() in low)
        if score:
            scored.append((score, para))
    scored.sort(key=lambda item: (-item[0], -len(item[1])))
    if scored:
        joined = "\n\n".join(p for _, p in scored[:4])
        return joined[:max_chars]
    # Fallback: shared header / first chunk only — still not the whole doc if long
    return text[: min(max_chars, 1200)]


def orchestrator(
    *,
    markdown_text: str,
    metadata: dict[str, Any],
    departments_needed: list[str],
) -> list[DepartmentSubtask]:
    """Decompose intake into per-department subtasks (orchestrator node)."""
    ordered = [d for d in departments_needed if d in DEPARTMENT_IDS]
    # Preserve CONTEXT order when present
    preferred = [
        DEPARTMENT_MARKETING,
        DEPARTMENT_OPERACIONES,
        DEPARTMENT_PROCUREMENT,
        DEPARTMENT_TRAINING,
    ]
    ordered = [d for d in preferred if d in ordered] + [
        d for d in ordered if d not in preferred
    ]

    subtasks: list[DepartmentSubtask] = []
    for department_id in ordered:
        excerpt = build_department_excerpt(markdown_text, department_id)
        subtasks.append(
            DepartmentSubtask(
                department_id=department_id,
                owner=DEPARTMENT_OWNERS[department_id],
                label=DEPARTMENT_LABELS[department_id],
                excerpt=excerpt,
                shared_metadata=dict(metadata),
            )
        )
    logger.info(
        "orchestrator decomposed %d department subtasks: %s",
        len(subtasks),
        [s.department_id for s in subtasks],
    )
    return subtasks


def _figure_present(text: str, *needles: str) -> bool:
    blob = text.casefold()
    if any(n.casefold() in blob for n in needles):
        # Prefer actual digits nearby for volume/budget claims
        if re.search(r"\d", text):
            return True
    return bool(re.search(r"\$\s*\d|\d[\d,]*\s*(?:usd|cop|k\b|empleados|diners|personas)", blob))


def _open_questions_for_department(
    department_id: str, metadata: dict[str, Any], excerpt: str
) -> list[str]:
    """Missing figures become open_questions — never invent numbers."""
    questions: list[str] = []
    corpus = f"{excerpt}\n{json_ish(metadata)}"
    owner = DEPARTMENT_OWNERS.get(department_id, department_id)

    if department_id == DEPARTMENT_PROCUREMENT:
        if not metadata.get("budget_range") and not metadata.get(
            "estimated_contract_value_usd"
        ):
            if not _figure_present(corpus, "budget", "USD", "COP", "precio"):
                questions.append(
                    f"Ask {owner}: confirm budget / contract value in USD and COP "
                    "(not stated in the RFP)."
                )
        if not _figure_present(corpus, "volume", "ingredient", "portion"):
            # Only ask if volume-like digits absent
            if not re.search(r"\d+\s*(?:empleados|diners|personas|resorts|locations)", corpus, re.I):
                questions.append(
                    f"Ask {owner}: confirm volume / diner counts for costing "
                    "(figure absent from RFP extracts)."
                )

    if department_id == DEPARTMENT_OPERACIONES:
        if not _figure_present(corpus, "staff", "kitchen", "setup"):
            if "220" not in corpus and "3 resort" not in corpus.casefold():
                questions.append(
                    f"Ask {owner}: confirm staffing capacity and setup window "
                    "(≥10 business days); figures not fully specified."
                )

    if department_id == DEPARTMENT_TRAINING:
        if "signature" not in corpus.casefold() and "nuevo" not in corpus.casefold():
            questions.append(
                f"Ask {owner}: confirm whether new recipes require certification timeline."
            )

    return questions


def json_ish(metadata: dict[str, Any]) -> str:
    parts = []
    for key in (
        "client_name",
        "location",
        "service_type",
        "scope",
        "deadline",
        "budget_range",
        "estimated_contract_value_usd",
    ):
        val = metadata.get(key)
        if val not in (None, ""):
            parts.append(f"{key}: {val}")
    return "\n".join(parts)


def _grounded_aspects(
    department_id: str, metadata: dict[str, Any], excerpt: str
) -> list[str]:
    """Build key_aspects from metadata + excerpt only (no invented volumes)."""
    client = metadata.get("client_name") or "the client"
    location = metadata.get("location")
    scope = metadata.get("scope") or metadata.get("service_type") or ""
    deadline = metadata.get("deadline")
    budget = metadata.get("budget_range")
    value = metadata.get("estimated_contract_value_usd")
    excerpt_one_line = " ".join((excerpt or "").split())[:180]

    aspects: list[str] = []

    if department_id == DEPARTMENT_MARKETING:
        aspects.append(f"Ticket owner handoff for {client} (Camila Ospina / Sales)")
        aspects.append("Offer validity period must be 30 days from issuance")
        if "exclusiv" in (excerpt + scope).casefold():
            aspects.append("Exclusivity / co-branding terms present in RFP extract")
        elif "co-brand" in (excerpt + scope).casefold():
            aspects.append("Co-branding partnership language present in RFP extract")
        else:
            aspects.append(f"Brand positioning for catering request from {client}")
        if deadline:
            aspects.append(f"Proposal deadline from RFP: {deadline}")

    elif department_id == DEPARTMENT_OPERACIONES:
        aspects.append(f"Operational feasibility for {client}" + (f" @ {location}" if location else ""))
        aspects.append("Setup/delivery timeline must be ≥10 business days (guideline)")
        # Ground volume only if present in metadata/excerpt
        vol = re.search(
            r"(\d[\d,]*)\s*(employees|empleados|diners|personas|resorts|properties|locations)",
            f"{scope}\n{excerpt}",
            re.I,
        )
        if vol:
            aspects.append(
                f"Volume stated in RFP: {vol.group(1)} {vol.group(2).lower()} "
                "(do not invent additional headcount)"
            )
        elif excerpt_one_line:
            aspects.append(f"Ops extract: {excerpt_one_line}…")

    elif department_id == DEPARTMENT_PROCUREMENT:
        aspects.append("Costing must keep USD $ and COP $ exactly as written — never convert")
        if budget:
            aspects.append(f"Budget range from RFP: {budget}")
        elif value is not None:
            aspects.append(
                f"Estimated contract value from RFP: ${float(value):,.0f} USD/year "
                "(as stated; do not invent COP equivalent)"
            )
        else:
            aspects.append(
                "Budget/volume not fully stated — record under open_questions; "
                "do not invent prices"
            )
        if excerpt_one_line:
            aspects.append(f"Procurement extract: {excerpt_one_line}…")

    elif department_id == DEPARTMENT_TRAINING:
        aspects.append("New recipe / signature-menu development if required by RFP")
        aspects.append("Certification and quality standards rollout plan")
        if "signature" in (excerpt + scope).casefold() or "menú" in (excerpt + scope).casefold():
            aspects.append("Signature / new menu language found in department extract")
        if excerpt_one_line:
            aspects.append(f"Training extract: {excerpt_one_line}…")

    else:
        aspects.append(f"Review {department_id} requirements for {client}")

    # Strip anything that looks like an invented absolute figure claim
    cleaned = [
        a
        for a in aspects
        if not any(p.search(a) for p in _INVENTED_FIGURE_PATTERNS)
    ]
    return cleaned[:6]


def department_worker(subtask: DepartmentSubtask) -> WorkerResult:
    """Worker: metadata + department extract → key_aspects (+ open_questions)."""
    aspects = _grounded_aspects(
        subtask.department_id, subtask.shared_metadata, subtask.excerpt
    )
    open_qs = _open_questions_for_department(
        subtask.department_id, subtask.shared_metadata, subtask.excerpt
    )
    return WorkerResult(
        department_id=subtask.department_id,
        owner=subtask.owner,
        key_aspects=aspects,
        open_questions=open_qs,
        excerpt_chars=len(subtask.excerpt or ""),
    )


# Back-compat callable used by older tests / imports
def department_worker_from_parts(
    department_id: str,
    metadata: dict[str, Any],
    excerpt: str,
) -> list[str]:
    result = department_worker(
        DepartmentSubtask(
            department_id=department_id,
            owner=DEPARTMENT_OWNERS.get(department_id, department_id),
            label=DEPARTMENT_LABELS.get(department_id, department_id),
            excerpt=excerpt,
            shared_metadata=metadata,
        )
    )
    return result.key_aspects


def synthesizer(
    *,
    metadata: dict[str, Any],
    worker_results: list[WorkerResult],
    requires_ceo_approval: bool,
) -> SynthesisResult:
    """Consolidate worker outputs into a Sales-facing summary (what to ask whom)."""
    departments = [w.department_id for w in worker_results]
    ask_whom: list[dict[str, str]] = []
    open_all: list[str] = []

    lines = [
        "SALES-FACING INTAKE SUMMARY (Camila Ospina / Marketing)",
        f"Client: {metadata.get('client_name') or 'Unknown'}",
        f"Location: {metadata.get('location') or 'Unknown'}",
        f"Service: {metadata.get('service_type') or metadata.get('scope') or 'Unspecified'}",
        f"Deadline: {metadata.get('deadline') or 'Not specified'}",
        f"Departments engaged: {', '.join(departments) or 'none'}",
        "",
        "What to ask whom:",
    ]

    for worker in worker_results:
        label = DEPARTMENT_LABELS.get(worker.department_id, worker.department_id)
        top = worker.key_aspects[0] if worker.key_aspects else "Review RFP extract"
        ask_line = f"Ask {worker.owner} ({label}): {top}"
        lines.append(f"- {ask_line}")
        ask_whom.append(
            {
                "department_id": worker.department_id,
                "owner": worker.owner,
                "ask": top,
            }
        )
        for q in worker.open_questions:
            open_all.append(q)
            lines.append(f"  · Open: {q}")

    if requires_ceo_approval:
        lines.append(
            f"- Flag for Part 3: estimated value exceeds "
            f"${CEO_USD_THRESHOLD:,.0f} USD/year → {CEO_NAME} (CEO) must approve."
        )
        ask_whom.append(
            {
                "department_id": "ceo",
                "owner": CEO_NAME,
                "ask": f"CEO approval required (>{CEO_USD_THRESHOLD:,.0f} USD/year)",
            }
        )

    if open_all:
        lines.append("")
        lines.append("Open questions (figures absent from RFP — do not invent):")
        for q in open_all:
            lines.append(f"- {q}")

    lines.append("")
    lines.append(
        "Part 2 handoff: generate proposal drafts per engaged department, "
        "then evaluate readability / relevance / compliance."
    )

    part2_handoff = {
        "status": STATUS_INTAKE_COMPLETE,
        "next_part": 2,
        "message": (
            "Intake complete. Sales can read key aspects. "
            "Part 2: each active department generates its proposal section "
            "and runs evaluation (readability, relevance, compliance)."
        ),
        "departments_for_drafting": departments,
        "owners": {
            w.department_id: w.owner for w in worker_results
        },
        "requires_ceo_approval": requires_ceo_approval,
        "ceo_approver": CEO_NAME if requires_ceo_approval else None,
        "ask_whom": ask_whom,
        "open_questions": open_all,
        "work_streams": [
            {
                "department_id": w.department_id,
                "owner": w.owner,
                "label": DEPARTMENT_LABELS.get(w.department_id, w.department_id),
                "key_aspects": list(w.key_aspects),
                "open_questions": list(w.open_questions),
                "next_action": "draft_section",
            }
            for w in worker_results
        ],
    }

    return SynthesisResult(
        intake_summary="\n".join(lines),
        ask_whom=ask_whom,
        part2_handoff=part2_handoff,
        conflicts=[],
        open_questions=open_all,
    )


def run_department_orchestration(
    *,
    markdown_text: str,
    metadata: dict[str, Any],
    departments_needed: list[str],
    requires_ceo_approval: bool = False,
) -> tuple[dict[str, list[str]], SynthesisResult, list[dict[str, Any]]]:
    """Run orchestrator → workers → synthesizer; return sections, synthesis, trace events."""
    events: list[dict[str, Any]] = []
    subtasks = orchestrator(
        markdown_text=markdown_text,
        metadata=metadata,
        departments_needed=departments_needed,
    )
    events.append(
        {
            "node": "orchestrator",
            "payload": {
                "subtasks": [s.department_id for s in subtasks],
                "owners": {s.department_id: s.owner for s in subtasks},
            },
        }
    )

    workers: list[WorkerResult] = []
    sections: dict[str, list[str]] = {}
    for subtask in subtasks:
        result = department_worker(subtask)
        workers.append(result)
        sections[result.department_id] = result.key_aspects
        events.append(
            {
                "node": "department_worker",
                "payload": {
                    "department_id": result.department_id,
                    "owner": result.owner,
                    "key_aspects": result.key_aspects,
                    "open_questions": result.open_questions,
                    "excerpt_chars": result.excerpt_chars,
                },
            }
        )

    synthesis = synthesizer(
        metadata=metadata,
        worker_results=workers,
        requires_ceo_approval=requires_ceo_approval,
    )
    events.append(
        {
            "node": "synthesizer",
            "payload": {
                "ask_whom": synthesis.ask_whom,
                "part2_handoff": synthesis.part2_handoff,
                "open_questions": synthesis.open_questions,
            },
        }
    )
    return sections, synthesis, events
