"""Dedicated Part 3 LangGraph — HITL approval, §7 arbitration, final document.

Not mixed into the CX support-agent graph or the Part 1/2 graphs.

Flow:
  load_handoff → surface_conflicts → arbitration → collect_approvals
  → ceo_gate → synthesizer → END

``collect_approvals`` / ``ceo_gate`` always ``interrupt()`` before a
department section (or CEO gate) is marked approved. Resume supplies the
named-owner decision. HTTP uses the same checkpoint thread.
"""

from __future__ import annotations

from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from data.pipelines.rfp_intake.constants import (
    STATUS_DONE,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_approval.approvers import (
    CEO_DEPARTMENT_ID,
    CEO_NAME,
    UnknownApproverError,
    assert_allowed_approver,
    normalize_decision,
    requires_ceo_approval,
    signoffs_for_ticket,
)
from data.pipelines.rfp_approval.arbitration import (
    RESOLUTION_ACTION_REQUEST_CHANGES,
    apply_fixed_arbitration,
    request_changes_departments,
    synthesizer_blocked_by_arbitration,
)
from data.pipelines.rfp_approval.conflicts import conflict_surface_agent
from data.pipelines.rfp_approval.handoff import (
    Part2HandoffNotReady,
    assert_part2_ready_for_approval,
)
from data.pipelines.rfp_approval.synthesizer import (
    build_final_document,
    synthesizer_ready,
)

REQUIRED_APPROVAL_NODES: tuple[str, ...] = (
    "load_handoff",
    "surface_conflicts",
    "arbitration",
    "collect_approvals",
    "ceo_gate",
    "synthesizer",
)

CX_GRAPH_FORBIDDEN_RFP_APPROVAL_NODES: frozenset[str] = frozenset(
    REQUIRED_APPROVAL_NODES
)


class RfpApprovalState(TypedDict, total=False):
    ticket_id: str
    status: str
    metadata: dict[str, Any]
    departments_needed: list[str]
    sections: list[dict[str, Any]]
    part3_handoff: dict[str, Any]
    requires_ceo_approval: bool
    conflicts: list[dict[str, Any]]
    arbitration: list[dict[str, Any]]
    approvals: dict[str, dict[str, Any]]
    ceo_approval: dict[str, Any]
    pending_approvals: list[dict[str, Any]]
    queued_decisions: list[dict[str, Any]]
    final_document: dict[str, Any]
    use_interrupt: bool
    paused: bool
    synthesizer_blocked: bool
    block_reason: str
    error_message: str | None
    trace: list[dict[str, Any]]


def _event(state: RfpApprovalState, node: str, **payload: Any) -> list[dict[str, Any]]:
    trace = list(state.get("trace") or [])
    trace.append({"node": node, "payload": payload})
    return trace


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _interrupt(payload: dict[str, Any]) -> dict[str, Any]:
    from langgraph.types import interrupt

    resumed = interrupt(payload)
    if isinstance(resumed, dict):
        return resumed
    return {"decision": resumed}


def interrupt_values(result: Any) -> list[Any]:
    """LangGraph interrupt objects from an invoke result or get_state snapshot."""
    if isinstance(result, dict):
        return list(result.get("__interrupt__") or [])
    found: list[Any] = []
    interrupts = getattr(result, "interrupts", None)
    if interrupts:
        found.extend(list(interrupts))
    for task in getattr(result, "tasks", None) or ():
        found.extend(list(getattr(task, "interrupts", None) or []))
    return found


def interrupt_payload(result: Any) -> dict[str, Any] | None:
    items = interrupt_values(result)
    if not items:
        return None
    first = items[0]
    value = getattr(first, "value", None)
    if value is None:
        value = first
    return value if isinstance(value, dict) else {"decision": value}


def approval_thread_id(ticket_id: str) -> str:
    """Stable LangGraph thread for HTTP start-approval + resume."""
    return f"{ticket_id}:approval"


def enrich_interrupt_state(final: dict[str, Any]) -> dict[str, Any]:
    """Mark HITL pause on invoke results that stopped at ``interrupt()``."""
    payload = interrupt_payload(final)
    if payload is None:
        return final
    out = dict(final)
    out["paused"] = True
    out["status"] = str(out.get("status") or STATUS_WAITING_FOR_APPROVAL)
    pending = payload.get("pending")
    if pending:
        out["pending_approvals"] = list(pending)
    elif payload.get("department_id"):
        out.setdefault("pending_approvals", [payload])
    return out


def _persist(ticket_id: str, **kwargs: Any) -> None:
    if not ticket_id:
        return
    try:
        from services.rfp.store import persist_part3_progress

        persist_part3_progress(ticket_id, **kwargs)
    except Exception:
        return


def _dept_status(state: RfpApprovalState, department_id: str) -> str:
    approvals = state.get("approvals") or {}
    row = approvals.get(department_id) or {}
    return str(row.get("approval_status") or "pending")


def _pending_department_signoffs(state: RfpApprovalState) -> list[dict[str, Any]]:
    needed = list(state.get("departments_needed") or [])
    pending: list[dict[str, Any]] = []
    for signoff in signoffs_for_ticket(
        needed, requires_ceo=False
    ):
        status = _dept_status(state, signoff.department_id)
        if status == "pending":
            pending.append(
                {
                    **signoff.to_dict(),
                    "approval_status": status,
                }
            )
    return pending


def load_handoff_node(state: RfpApprovalState) -> dict[str, Any]:
    ticket_id = str(state.get("ticket_id") or "").strip()
    try:
        contract = assert_part2_ready_for_approval(
            ticket_id=ticket_id,
            status=str(state.get("status") or STATUS_WAITING_FOR_APPROVAL),
            sections=list(state.get("sections") or []),
            part3_handoff=state.get("part3_handoff"),
        )
    except Part2HandoffNotReady as exc:
        return {
            "status": "failed",
            "error_message": str(exc),
            "trace": _event(state, "load_handoff", error=str(exc)),
        }

    sections = list(contract["sections"])
    metadata = dict(state.get("metadata") or {})
    needed = list(state.get("departments_needed") or [])
    if not needed:
        needed = [
            str(s.get("department_id"))
            for s in sections
            if s.get("department_id") and s.get("department_id") != CEO_DEPARTMENT_ID
        ]
    ceo_needed = requires_ceo_approval(
        requires_ceo_flag=bool(state.get("requires_ceo_approval")),
        metadata=metadata,
    )
    approvals = dict(state.get("approvals") or {})
    for dept in needed:
        approvals.setdefault(
            dept,
            {
                "department_id": dept,
                "approval_status": "pending",
                "approver": None,
                "approved_at": None,
            },
        )
    _persist(
        ticket_id,
        status=STATUS_WAITING_FOR_APPROVAL,
        approvals=approvals,
        requires_ceo_approval=ceo_needed,
    )
    return {
        "ticket_id": ticket_id,
        "status": STATUS_WAITING_FOR_APPROVAL,
        "sections": sections,
        "departments_needed": needed,
        "requires_ceo_approval": ceo_needed,
        "approvals": approvals,
        "paused": False,
        "error_message": None,
        "trace": _event(
            state,
            "load_handoff",
            ticket_id=ticket_id,
            departments=needed,
            requires_ceo_approval=ceo_needed,
            reparse_pdf_required=False,
        ),
    }


def surface_conflicts_node(state: RfpApprovalState) -> dict[str, Any]:
    if state.get("error_message"):
        return {}
    conflicts = conflict_surface_agent(
        sections=list(state.get("sections") or []),
        metadata=dict(state.get("metadata") or {}),
        requires_ceo_flag=bool(state.get("requires_ceo_approval")),
        ceo_approval=state.get("ceo_approval"),
    )
    return {
        "conflicts": conflicts,
        "trace": _event(
            state,
            "surface_conflicts",
            trigger_ids=[c.get("trigger_id") for c in conflicts],
            agent="conflict_surface_agent",
            resolved=False,
        ),
    }


def arbitration_node(state: RfpApprovalState) -> dict[str, Any]:
    """Dedicated graph node: CONTEXT §7 table, not LLM consensus."""
    if state.get("error_message"):
        return {}
    resolutions = apply_fixed_arbitration(list(state.get("conflicts") or []))
    approvals = dict(state.get("approvals") or {})
    for dept in request_changes_departments(resolutions):
        current = dict(approvals.get(dept) or {"department_id": dept})
        if current.get("approval_status") != "approved":
            current["approval_status"] = RESOLUTION_ACTION_REQUEST_CHANGES
            current["arbiter_forced"] = True
            approvals[dept] = current
    ceo_status = str((state.get("ceo_approval") or {}).get("approval_status") or "pending")
    blocked = synthesizer_blocked_by_arbitration(
        resolutions, ceo_approval_status=ceo_status
    )
    _persist(
        str(state.get("ticket_id") or ""),
        status=STATUS_WAITING_FOR_APPROVAL,
        approvals=approvals,
        arbitration=resolutions,
        conflicts=list(state.get("conflicts") or []),
    )
    return {
        "arbitration": resolutions,
        "approvals": approvals,
        "synthesizer_blocked": blocked,
        "trace": _event(
            state,
            "arbitration",
            trigger_ids=[r.get("trigger_id") for r in resolutions],
            arbiters=[r.get("arbiter") for r in resolutions],
            llm_resolved=False,
        ),
    }


def _apply_department_decision(
    state: RfpApprovalState, decision: dict[str, Any]
) -> dict[str, Any]:
    dept = str(decision.get("department_id") or "").strip()
    if dept == CEO_DEPARTMENT_ID:
        # CEO decisions belong on ceo_gate, but accept them here for queued HTTP.
        return _apply_ceo_decision(state, decision)
    try:
        mapped = normalize_decision(str(decision.get("decision") or ""))
        approver = assert_allowed_approver(dept, str(decision.get("approver") or ""))
    except (UnknownApproverError, ValueError) as exc:
        return {
            "error_message": str(exc),
            "paused": True,
            "status": STATUS_WAITING_FOR_APPROVAL,
            "trace": _event(state, "collect_approvals", error=str(exc)),
        }
    approvals = dict(state.get("approvals") or {})
    stamp = _now()
    approvals[dept] = {
        "department_id": dept,
        "approval_status": mapped,
        "approver": approver,
        "approved_at": stamp if mapped == "approved" else None,
        "decided_at": stamp,
        "comment": decision.get("comment"),
    }
    _persist(
        str(state.get("ticket_id") or ""),
        status=STATUS_WAITING_FOR_APPROVAL,
        approvals=approvals,
    )
    return {
        "approvals": approvals,
        "error_message": None,
        "paused": False,
        "trace": _event(
            state,
            "collect_approvals",
            department_id=dept,
            decision=mapped,
            approver=approver,
        ),
    }


def _apply_ceo_decision(
    state: RfpApprovalState, decision: dict[str, Any]
) -> dict[str, Any]:
    try:
        mapped = normalize_decision(str(decision.get("decision") or ""))
        approver = assert_allowed_approver(
            CEO_DEPARTMENT_ID, str(decision.get("approver") or CEO_NAME)
        )
    except (UnknownApproverError, ValueError) as exc:
        return {
            "error_message": str(exc),
            "paused": True,
            "status": STATUS_WAITING_FOR_APPROVAL,
            "trace": _event(state, "ceo_gate", error=str(exc)),
        }
    stamp = _now()
    ceo = {
        "department_id": CEO_DEPARTMENT_ID,
        "approval_status": mapped,
        "approver": approver,
        "approved_at": stamp if mapped == "approved" else None,
        "decided_at": stamp,
        "comment": decision.get("comment"),
    }
    blocked = mapped != "approved"
    _persist(
        str(state.get("ticket_id") or ""),
        status=STATUS_WAITING_FOR_APPROVAL,
        ceo_approval=ceo,
        synthesizer_blocked=blocked,
    )
    return {
        "ceo_approval": ceo,
        "synthesizer_blocked": blocked,
        "block_reason": "" if mapped == "approved" else f"CEO {mapped}",
        "paused": False,
        "error_message": None,
        "trace": _event(
            state,
            "ceo_gate",
            decision=mapped,
            approver=approver,
        ),
    }


def collect_approvals_node(state: RfpApprovalState) -> dict[str, Any]:
    if state.get("error_message"):
        return {}
    pending = _pending_department_signoffs(state)
    if not pending:
        return {
            "pending_approvals": [],
            "paused": False,
            "queued_decisions": [],
            "trace": _event(state, "collect_approvals", pending=0),
        }

    # Interruption point: the section stays pending until a human resumes.
    target = pending[0]
    ticket_id = str(state.get("ticket_id") or "")
    _persist(
        ticket_id,
        status=STATUS_WAITING_FOR_APPROVAL,
        approvals=dict(state.get("approvals") or {}),
    )
    resumed = _interrupt(
        {
            "kind": "department_approval",
            "ticket_id": ticket_id,
            "department_id": target["department_id"],
            "approver": target["approver"],
            "pending": pending,
        }
    )
    resumed.setdefault("department_id", target["department_id"])
    if not resumed.get("approver"):
        resumed["approver"] = target["approver"]
    applied = _apply_department_decision(state, resumed)
    merged = {**state, **applied}
    applied["pending_approvals"] = _pending_department_signoffs(merged)
    applied["queued_decisions"] = []
    return applied


def ceo_gate_node(state: RfpApprovalState) -> dict[str, Any]:
    if state.get("error_message"):
        return {}
    if not state.get("requires_ceo_approval"):
        return {
            "synthesizer_blocked": False,
            "trace": _event(state, "ceo_gate", required=False),
        }

    ceo = dict(state.get("ceo_approval") or {})
    status = str(ceo.get("approval_status") or "pending")
    if status == "approved":
        return {
            "synthesizer_blocked": False,
            "paused": False,
            "trace": _event(state, "ceo_gate", required=True, status="approved"),
        }
    if status == "rejected":
        return {
            "synthesizer_blocked": True,
            "paused": False,
            "status": STATUS_WAITING_FOR_APPROVAL,
            "block_reason": f"CEO {CEO_NAME} rejected",
            "trace": _event(state, "ceo_gate", required=True, status="rejected"),
        }

    pending = {
        "department_id": CEO_DEPARTMENT_ID,
        "approver": CEO_NAME,
        "role": "ceo",
        "approval_status": "pending",
    }
    ticket_id = str(state.get("ticket_id") or "")
    _persist(
        ticket_id,
        status=STATUS_WAITING_FOR_APPROVAL,
        synthesizer_blocked=True,
        ceo_approval=ceo or pending,
    )
    resumed = _interrupt(
        {
            "kind": "ceo_approval",
            "ticket_id": ticket_id,
            "department_id": CEO_DEPARTMENT_ID,
            "pending": [pending],
            "approver": CEO_NAME,
        }
    )
    resumed.setdefault("department_id", CEO_DEPARTMENT_ID)
    resumed.setdefault("approver", CEO_NAME)
    return _apply_ceo_decision(state, resumed)


def synthesizer_node(state: RfpApprovalState) -> dict[str, Any]:
    if state.get("error_message"):
        return {"status": "failed"}
    approvals = state.get("approvals") or {}
    dept_status = {
        dept: str((approvals.get(dept) or {}).get("approval_status") or "pending")
        for dept in (state.get("departments_needed") or [])
    }
    ceo_status = str((state.get("ceo_approval") or {}).get("approval_status") or "pending")
    changes = [
        dept for dept, status in dept_status.items() if status == "request_changes"
    ]
    ready, blocker = synthesizer_ready(
        department_approvals=dept_status,
        departments_needed=list(state.get("departments_needed") or []),
        requires_ceo=bool(state.get("requires_ceo_approval")),
        ceo_approval_status=ceo_status if state.get("requires_ceo_approval") else None,
        request_changes=changes,
    )
    if not ready:
        return {
            "status": STATUS_WAITING_FOR_APPROVAL,
            "synthesizer_blocked": True,
            "block_reason": blocker,
            "final_document": {},
            "trace": _event(state, "synthesizer", blocked=True, reason=blocker),
        }

    sections = []
    for row in state.get("sections") or []:
        dept = row.get("department_id")
        merged = dict(row)
        if dept in approvals:
            merged.update(approvals[dept])
        sections.append(merged)
    approval_rows = [
        approvals[d]
        for d in (state.get("departments_needed") or [])
        if d in approvals
    ]
    document = build_final_document(
        ticket_id=str(state.get("ticket_id") or ""),
        sections=sections,
        metadata=dict(state.get("metadata") or {}),
        departments_needed=list(state.get("departments_needed") or []),
        approvals=approval_rows,
        ceo_approval=state.get("ceo_approval") if state.get("requires_ceo_approval") else None,
    )
    _persist(
        str(state.get("ticket_id") or ""),
        status=STATUS_DONE,
        final_document=document,
        approvals=approvals,
        ceo_approval=state.get("ceo_approval"),
    )
    return {
        "status": STATUS_DONE,
        "final_document": document,
        "synthesizer_blocked": False,
        "paused": False,
        "trace": _event(
            state,
            "synthesizer",
            ticket_id=document["ticket_id"],
            total_estimated_value=document.get("total_estimated_value"),
        ),
    }


def _after_load(state: RfpApprovalState) -> str:
    if state.get("error_message"):
        return "end"
    return "surface_conflicts"


def _after_approvals(state: RfpApprovalState) -> str:
    if state.get("error_message") or state.get("paused"):
        return "end"
    if _pending_department_signoffs(state):
        return "collect_approvals"
    return "ceo_gate"


def _after_ceo(state: RfpApprovalState) -> str:
    if state.get("error_message") or state.get("paused"):
        return "end"
    if state.get("synthesizer_blocked") and (
        str((state.get("ceo_approval") or {}).get("approval_status") or "") == "rejected"
    ):
        return "end"
    return "synthesizer"


def build_rfp_approval_graph(*, checkpointer: Any | None = None) -> Any:
    graph = StateGraph(RfpApprovalState)
    graph.add_node("load_handoff", load_handoff_node)
    graph.add_node("surface_conflicts", surface_conflicts_node)
    graph.add_node("arbitration", arbitration_node)
    graph.add_node("collect_approvals", collect_approvals_node)
    graph.add_node("ceo_gate", ceo_gate_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.add_edge(START, "load_handoff")
    graph.add_conditional_edges(
        "load_handoff",
        _after_load,
        {"surface_conflicts": "surface_conflicts", "end": END},
    )
    graph.add_edge("surface_conflicts", "arbitration")
    graph.add_edge("arbitration", "collect_approvals")
    graph.add_conditional_edges(
        "collect_approvals",
        _after_approvals,
        {
            "collect_approvals": "collect_approvals",
            "ceo_gate": "ceo_gate",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "ceo_gate",
        _after_ceo,
        {"synthesizer": "synthesizer", "end": END},
    )
    graph.add_edge("synthesizer", END)

    compiled = graph.compile(checkpointer=checkpointer)
    registered = set(compiled.get_graph().nodes)
    missing = [n for n in REQUIRED_APPROVAL_NODES if n not in registered]
    if missing:
        raise RuntimeError(f"RFP approval graph missing nodes: {missing}")
    return compiled


_COMPILED = None
_COMPILED_INTERRUPT = None
_COMPILED_KEY = None


def get_compiled_rfp_approval_graph(*, use_interrupt: bool = False) -> Any:
    """Compile once per checkpointer backend.

    Always attaches a durable checkpointer (SQLite file or Postgres).
    ``MemorySaver`` is used only when ``RFP_CHECKPOINT_MEMORY=1``.
    ``use_interrupt`` is kept for callers; HITL is a state flag, not a
    separate graph topology.
    """
    from data.pipelines.rfp_approval.checkpointer import get_approval_checkpointer

    global _COMPILED, _COMPILED_INTERRUPT, _COMPILED_KEY
    saver = get_approval_checkpointer()
    key = id(saver)
    if _COMPILED is not None and _COMPILED_KEY == key:
        return _COMPILED
    compiled = build_rfp_approval_graph(checkpointer=saver)
    _COMPILED = compiled
    _COMPILED_INTERRUPT = compiled
    _COMPILED_KEY = key
    return compiled


def _approval_invoke_config(
    *,
    ticket_id: str,
    resume: Any,
    use_interrupt: bool,
    thread_id: str | None,
) -> dict[str, Any]:
    """Always pass ``thread_id`` — durable checkpointers require it.

    HITL interrupt/resume uses a stable id so ``Command(resume=)`` can
    continue the same thread. Fresh pipeline runs use a unique thread so
    a second start on the same ticket_id does not resume a checkpoint.
    HTTP uses :func:`approval_thread_id`.
    """
    if thread_id:
        tid = thread_id
    elif resume is not None:
        tid = ticket_id
    else:
        tid = f"{ticket_id}:{uuid4().hex}"
    return {"configurable": {"thread_id": tid}}


def invoke_rfp_approval_graph(
    *,
    ticket_id: str,
    status: str = STATUS_WAITING_FOR_APPROVAL,
    sections: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    departments_needed: list[str] | None = None,
    part3_handoff: dict[str, Any] | None = None,
    requires_ceo_approval: bool = False,
    approvals: dict[str, dict[str, Any]] | None = None,
    ceo_approval: dict[str, Any] | None = None,
    queued_decisions: list[dict[str, Any]] | None = None,
    use_interrupt: bool = True,
    thread_id: str | None = None,
    resume: Any | None = None,
) -> RfpApprovalState:
    graph = get_compiled_rfp_approval_graph(use_interrupt=use_interrupt)
    initial: RfpApprovalState = {
        "ticket_id": ticket_id,
        "status": status,
        "sections": list(sections or []),
        "metadata": dict(metadata or {}),
        "departments_needed": list(departments_needed or []),
        "part3_handoff": dict(part3_handoff or {}),
        "requires_ceo_approval": requires_ceo_approval,
        "approvals": dict(approvals or {}),
        "ceo_approval": dict(ceo_approval or {}),
        "queued_decisions": list(queued_decisions or []),
        "use_interrupt": use_interrupt,
        "trace": [],
        "conflicts": [],
        "arbitration": [],
        "pending_approvals": [],
    }
    config = _approval_invoke_config(
        ticket_id=ticket_id,
        resume=resume,
        use_interrupt=use_interrupt,
        thread_id=thread_id,
    )
    if resume is not None:
        from langgraph.types import Command

        return graph.invoke(Command(resume=resume), config=config)
    return graph.invoke(initial, config=config)
