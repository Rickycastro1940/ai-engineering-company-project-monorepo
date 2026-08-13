"""Dedicated Brasaland RFP intake LangGraph — separate from the CX support-agent graph.

CONTEXT §2.4: pipeline/graph lives under ``data/pipelines/rfp_intake/`` and must
not be mixed into ``services.agent.graph``.

Separate agent nodes:
  convert → readability → classifier_agent → (discard | orchestrator →
  department_worker → synthesizer)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from data.pipelines.rfp_intake.classifier import (
    ClassifierDecision,
    assert_no_silent_discard,
    classifier_agent,
)
from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_IDS,
    STATUS_DISCARDED,
    STATUS_FAILED,
    STATUS_INTAKE_COMPLETE,
)
from data.pipelines.rfp_intake.orchestration import (
    department_worker,
    orchestrator,
    synthesizer,
)

# Canonical node ids for this dedicated graph (separate agent callables).
REQUIRED_RFP_NODES: tuple[str, ...] = (
    "convert",
    "readability",
    "classifier_agent",
    "orchestrator",
    "department_worker",
    "synthesizer",
)

# Explicitly not part of the CX support-agent graph
CX_GRAPH_FORBIDDEN_RFP_NODES: frozenset[str] = frozenset(REQUIRED_RFP_NODES)


class RfpIntakeState(TypedDict, total=False):
    pdf_path: str
    title: str | None
    markdown_text: str
    readability_scores: dict[str, float]
    is_valid_rfp: bool
    classified_status: str
    discard_reason: str | None
    discard_rule_id: str | None
    classified_rationale: str
    unmapped_topics: list[str]
    requires_ceo_approval: bool
    metadata: dict[str, Any]
    departments_needed: list[str]
    subtasks: list[dict[str, Any]]
    worker_results: list[dict[str, Any]]
    sections: dict[str, list[str]]
    intake_summary: str
    ask_whom: list[dict[str, str]]
    open_questions: list[str]
    part2_handoff: dict[str, Any]
    conflicts: list[dict[str, Any]]
    status: str
    error_message: str | None
    trace: list[dict[str, Any]]


def _event(state: RfpIntakeState, node: str, **payload: Any) -> list[dict[str, Any]]:
    trace = list(state.get("trace") or [])
    trace.append({"node": node, "payload": payload})
    return trace


def convert_node(state: RfpIntakeState) -> dict[str, Any]:
    from data.pipelines.rfp_intake import convert_document_to_markdown

    path = Path(state["pdf_path"])
    try:
        markdown = convert_document_to_markdown(path)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": STATUS_FAILED,
            "markdown_text": "",
            "error_message": f"convert_failed:{type(exc).__name__}: {exc}",
            "trace": _event(state, "convert", error=str(exc)),
        }
    return {
        "markdown_text": markdown,
        "error_message": None,
        "trace": _event(
            state, "convert", markdown_chars=len(markdown), source=path.name
        ),
    }


def readability_node(state: RfpIntakeState) -> dict[str, Any]:
    from data.pipelines.rfp_intake import compute_readability_scores

    if state.get("status") == STATUS_FAILED:
        return {}
    scores = compute_readability_scores(state.get("markdown_text") or "")
    return {
        "readability_scores": scores,
        "trace": _event(state, "readability", scores=scores),
    }


def classifier_agent_node(state: RfpIntakeState) -> dict[str, Any]:
    if state.get("status") == STATUS_FAILED:
        return {}
    markdown = state.get("markdown_text") or ""
    classified: ClassifierDecision = classifier_agent(markdown)
    assert_no_silent_discard(classified)
    metadata = dict(classified.metadata)
    if state.get("title"):
        metadata["title"] = state["title"]
    metadata["readability_scores"] = dict(state.get("readability_scores") or {})
    out: dict[str, Any] = {
        "is_valid_rfp": classified.is_valid_rfp,
        "classified_status": classified.status,
        "discard_reason": classified.discard_reason,
        "discard_rule_id": classified.discard_rule_id,
        "classified_rationale": classified.rationale,
        "unmapped_topics": list(classified.unmapped_topics),
        "requires_ceo_approval": classified.requires_ceo_approval,
        "metadata": metadata,
        "departments_needed": [
            d for d in classified.departments_needed if d in DEPARTMENT_IDS
        ],
        "trace": _event(
            state,
            "classifier_agent",
            is_valid_rfp=classified.is_valid_rfp,
            status=classified.status,
            departments_needed=classified.departments_needed,
            discard_reason=classified.discard_reason,
            discard_rule_id=classified.discard_rule_id,
            rationale=classified.rationale,
        ),
    }
    if not classified.is_valid_rfp:
        reason = classified.discard_reason or ""
        out.update(
            {
                "status": STATUS_DISCARDED,
                "departments_needed": [],
                "sections": {},
                "intake_summary": reason,
                "ask_whom": [],
                "open_questions": [],
                "part2_handoff": {},
                "conflicts": [],
            }
        )
    return out


def orchestrator_node(state: RfpIntakeState) -> dict[str, Any]:
    """Separate orchestrator agent — decomposes into per-department subtasks."""
    subtasks = orchestrator(
        markdown_text=state.get("markdown_text") or "",
        metadata=dict(state.get("metadata") or {}),
        departments_needed=list(state.get("departments_needed") or []),
    )
    serialized = [
        {
            "department_id": s.department_id,
            "owner": s.owner,
            "label": s.label,
            "excerpt": s.excerpt,
            "shared_metadata": s.shared_metadata,
        }
        for s in subtasks
    ]
    return {
        "subtasks": serialized,
        "trace": _event(
            state,
            "orchestrator",
            subtasks=[s.department_id for s in subtasks],
            owners={s.department_id: s.owner for s in subtasks},
        ),
    }


def department_worker_node(state: RfpIntakeState) -> dict[str, Any]:
    """Separate worker agent — one invocation per department subtask."""
    from data.pipelines.rfp_intake.orchestration import DepartmentSubtask

    workers: list[dict[str, Any]] = []
    sections: dict[str, list[str]] = {}
    trace = list(state.get("trace") or [])
    for raw in state.get("subtasks") or []:
        subtask = DepartmentSubtask(
            department_id=raw["department_id"],
            owner=raw["owner"],
            label=raw["label"],
            excerpt=raw["excerpt"],
            shared_metadata=raw["shared_metadata"],
        )
        result = department_worker(subtask)
        workers.append(
            {
                "department_id": result.department_id,
                "owner": result.owner,
                "key_aspects": result.key_aspects,
                "open_questions": result.open_questions,
                "excerpt_chars": result.excerpt_chars,
            }
        )
        sections[result.department_id] = result.key_aspects
        trace.append(
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
    return {"worker_results": workers, "sections": sections, "trace": trace}


def synthesizer_node(state: RfpIntakeState) -> dict[str, Any]:
    """Separate synthesizer agent — Sales-facing summary + Part 2 handoff."""
    from data.pipelines.rfp_intake.orchestration import WorkerResult

    workers = [
        WorkerResult(
            department_id=w["department_id"],
            owner=w["owner"],
            key_aspects=list(w.get("key_aspects") or []),
            open_questions=list(w.get("open_questions") or []),
            excerpt_chars=int(w.get("excerpt_chars") or 0),
        )
        for w in (state.get("worker_results") or [])
    ]
    synthesis = synthesizer(
        metadata=dict(state.get("metadata") or {}),
        worker_results=workers,
        requires_ceo_approval=bool(state.get("requires_ceo_approval")),
    )
    metadata = dict(state.get("metadata") or {})
    metadata["open_questions"] = synthesis.open_questions
    metadata["part2_handoff"] = synthesis.part2_handoff
    metadata["ask_whom"] = synthesis.ask_whom
    return {
        "status": STATUS_INTAKE_COMPLETE,
        "metadata": metadata,
        "intake_summary": synthesis.intake_summary,
        "ask_whom": synthesis.ask_whom,
        "open_questions": synthesis.open_questions,
        "part2_handoff": synthesis.part2_handoff,
        "conflicts": synthesis.conflicts,
        "trace": _event(
            state,
            "synthesizer",
            ask_whom=synthesis.ask_whom,
            part2_handoff=synthesis.part2_handoff,
            open_questions=synthesis.open_questions,
        ),
    }


def _after_convert(state: RfpIntakeState) -> str:
    if state.get("status") == STATUS_FAILED:
        return "end"
    return "readability"


def _after_classifier(state: RfpIntakeState) -> str:
    if state.get("status") == STATUS_FAILED:
        return "end"
    if state.get("is_valid_rfp") is False or state.get("status") == STATUS_DISCARDED:
        return "end"
    return "orchestrator"


def build_rfp_intake_graph() -> Any:
    """Compile the dedicated RFP intake graph (not the CX agent graph)."""
    graph = StateGraph(RfpIntakeState)
    graph.add_node("convert", convert_node)
    graph.add_node("readability", readability_node)
    graph.add_node("classifier_agent", classifier_agent_node)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("department_worker", department_worker_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.add_edge(START, "convert")
    graph.add_conditional_edges(
        "convert",
        _after_convert,
        {"readability": "readability", "end": END},
    )
    graph.add_edge("readability", "classifier_agent")
    graph.add_conditional_edges(
        "classifier_agent",
        _after_classifier,
        {"orchestrator": "orchestrator", "end": END},
    )
    graph.add_edge("orchestrator", "department_worker")
    graph.add_edge("department_worker", "synthesizer")
    graph.add_edge("synthesizer", END)

    compiled = graph.compile()
    registered = set(compiled.get_graph().nodes)
    missing = [n for n in REQUIRED_RFP_NODES if n not in registered]
    if missing:
        raise RuntimeError(f"RFP intake graph missing nodes: {missing}")
    return compiled


_COMPILED = None


def get_compiled_rfp_intake_graph() -> Any:
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = build_rfp_intake_graph()
    return _COMPILED


def invoke_rfp_intake_graph(*, pdf_path: Path, title: str | None = None) -> RfpIntakeState:
    """Run the dedicated rfp_intake graph for one document."""
    graph = get_compiled_rfp_intake_graph()
    initial: RfpIntakeState = {
        "pdf_path": str(pdf_path),
        "title": title,
        "trace": [],
        "metadata": {},
        "readability_scores": {},
        "departments_needed": [],
        "sections": {},
        "ask_whom": [],
        "open_questions": [],
        "part2_handoff": {},
        "conflicts": [],
        "unmapped_topics": [],
    }
    return graph.invoke(initial)
