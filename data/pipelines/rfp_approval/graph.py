"""Dedicated Part 3 LangGraph — HITL approval, §7 arbitration, final document.

Not mixed into the CX support-agent graph or the Part 1/2 graphs.

Flow:
  load_handoff → surface_conflicts → arbitration
  → Send(collect_approvals) per *pending* department (parallel branches)
  → apply_approval (resume entry) → join_approvals → ceo_gate → synthesizer → END

Each department branch calls ``interrupt()`` only if that section is still
``pending``. Departments already decided skip the pause and do not block
sibling branches. A human decision resumes the matching interrupt and
enters ``apply_approval`` on the existing checkpoint — it does not
re-invoke from START / ``load_handoff``.

Guardrails (§ flow control):
  - ``MAX_DEPARTMENT_APPROVAL_ITERATIONS`` caps request_changes loops
  - ``arbitration`` is a dedicated node with CONTEXT §7 fixed arbiters (not LLM)
  - every node appends agent / input / output / timestamp to ``trace``
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send

from data.pipelines.rfp_intake.constants import (
    STATUS_DONE,
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_approval.approvers import (
    CEO_DEPARTMENT_ID,
    CEO_NAME,
    InvalidResumeDecisionError,
    UnknownApproverError,
    assert_allowed_approver,
    normalize_decision,
    requires_ceo_approval,
    signoffs_for_ticket,
    validate_human_resume,
)
from data.pipelines.rfp_approval.arbitration import (
    RESOLUTION_ACTION_REQUEST_CHANGES,
    apply_fixed_arbitration,
    request_changes_departments,
    synthesizer_blocked_by_arbitration,
)
from data.pipelines.rfp_approval.guardrails import (
    MAX_DEPARTMENT_APPROVAL_ITERATIONS,
    bump_department_iterations,
    iteration_limit_error,
    merge_iteration_counts,
)
from data.pipelines.rfp_approval.checkpointer import (
    approval_thread_id,
    ensure_rfp_thread_id,
    ephemeral_rfp_thread_id,
    rfp_checkpoint_thread_id,
)
from data.pipelines.rfp_approval.conflicts import conflict_surface_agent
from data.pipelines.rfp_approval.handoff import (
    Part2HandoffNotReady,
    assert_part2_ready_for_approval,
    normalize_section_approval_status,
)
from data.pipelines.rfp_approval.synthesizer import (
    build_final_document,
    synthesizer_ready,
)

APPLY_APPROVAL_NODE = "apply_approval"

REQUIRED_APPROVAL_NODES: tuple[str, ...] = (
    "load_handoff",
    "surface_conflicts",
    "arbitration",
    "collect_approvals",
    APPLY_APPROVAL_NODE,
    "ceo_gate",
    "synthesizer",
)

# Named agent (or deterministic role) recorded on every trace event.
NODE_AGENTS: dict[str, str] = {
    "load_handoff": "part2_handoff_loader",
    "surface_conflicts": "conflict_surface_agent",
    "arbitration": "fixed_arbitration",  # CONTEXT §7 table — never an LLM
    "collect_approvals": "department_hitl",
    APPLY_APPROVAL_NODE: "apply_approval",
    "join_approvals": "join_approvals",
    "ceo_gate": "ceo_hitl",
    "synthesizer": "final_document_synthesizer",
}

RESUME_NOT_PAUSED = "approval_not_paused"
RESUME_NOT_PAUSED_MESSAGE = (
    "Resume is an entry into the paused approval graph, not a restart. "
    "Start approval first."
)


def merge_approvals(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> dict[str, Any]:
    """Reducer: parallel department branches write disjoint approval keys."""
    out = dict(left or {})
    out.update(right or {})
    return out


def last_value(left: Any, right: Any) -> Any:
    return right if right is not None else left


def merge_error(left: str | None, right: str | None) -> str | None:
    return right or left


class RfpApprovalState(TypedDict, total=False):
    ticket_id: str
    status: Annotated[str, last_value]
    metadata: dict[str, Any]
    departments_needed: list[str]
    sections: list[dict[str, Any]]
    part3_handoff: dict[str, Any]
    requires_ceo_approval: bool
    conflicts: list[dict[str, Any]]
    arbitration: list[dict[str, Any]]
    approvals: Annotated[dict[str, dict[str, Any]], merge_approvals]
    ceo_approval: dict[str, Any]
    pending_approvals: Annotated[list[dict[str, Any]], last_value]
    queued_decisions: list[dict[str, Any]]
    final_document: dict[str, Any]
    use_interrupt: bool
    paused: Annotated[bool, last_value]
    synthesizer_blocked: Annotated[bool, last_value]
    block_reason: Annotated[str, last_value]
    error_message: Annotated[str | None, merge_error]
    trace: Annotated[list[dict[str, Any]], operator.add]
    department_id: Annotated[str, last_value]
    resume_decision: Annotated[dict[str, Any], last_value]
    approval_iterations: Annotated[dict[str, int], merge_iteration_counts]
    max_approval_iterations: int


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _event(
    state: RfpApprovalState,
    node: str,
    *,
    agent: str | None = None,
    input: Any = None,
    output: Any = None,
    **payload: Any,
) -> list[dict[str, Any]]:
    """Append one trace row: agent, input, output, timestamp (plus payload)."""
    resolved_agent = agent or NODE_AGENTS.get(node, node)
    resolved_output = output if output is not None else (payload or {})
    return [
        {
            "node": node,
            "agent": resolved_agent,
            "input": input,
            "output": resolved_output,
            "timestamp": _now(),
            "payload": payload,
        }
    ]


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


def interrupt_payloads(result: Any) -> list[dict[str, Any]]:
    """All interrupt payloads (one per paused department branch)."""
    out: list[dict[str, Any]] = []
    for item in interrupt_values(result):
        value = getattr(item, "value", None)
        if value is None:
            value = item
        if isinstance(value, dict):
            payload = dict(value)
        else:
            payload = {"decision": value}
        iid = getattr(item, "id", None)
        if iid:
            payload.setdefault("interrupt_id", str(iid))
        out.append(payload)
    return out


def interrupt_payload(result: Any) -> dict[str, Any] | None:
    items = interrupt_payloads(result)
    return items[0] if items else None


def match_interrupt_resumes(
    result: Any, decisions: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Map queued decisions onto pending interrupt ids by ``department_id``.

    Unmatched decisions are returned so a later CEO interrupt can consume them.
    """
    leftover = list(decisions)
    mapping: dict[str, Any] = {}
    for item in interrupt_values(result):
        iid = getattr(item, "id", None)
        value = getattr(item, "value", None)
        if value is None:
            value = item
        payload = value if isinstance(value, dict) else {}
        dept = str(payload.get("department_id") or "")
        if not iid or not dept:
            continue
        for i, decision in enumerate(leftover):
            if str(decision.get("department_id") or "") == dept:
                mapping[str(iid)] = leftover.pop(i)
                break
    return mapping, leftover


def _is_interrupt_id_map(resume: Any) -> bool:
    if not isinstance(resume, dict) or not resume:
        return False
    if {"department_id", "decision", "approver"} & set(resume):
        return False
    return True


def graph_is_paused(snapshot: Any) -> bool:
    """True when the thread is waiting at ``interrupt()`` (or has ``next`` tasks)."""
    if interrupt_values(snapshot):
        return True
    return bool(getattr(snapshot, "next", None))


def _goto_apply_approval(
    *,
    ticket_id: str,
    decision: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> Command:
    """Route a resumed interrupt into ``apply_approval`` (not START)."""
    payload: dict[str, Any] = {
        "ticket_id": ticket_id,
        "department_id": str(decision.get("department_id") or ""),
        "resume_decision": decision,
        **(extra or {}),
    }
    return Command(goto=Send(APPLY_APPROVAL_NODE, payload))


def _pending_resume_departments(snapshot: Any) -> set[str]:
    return {
        str(payload.get("department_id") or "")
        for payload in interrupt_payloads(snapshot)
        if payload.get("department_id")
    }


def prepare_resume(resume: Any, snapshot: Any | None = None) -> Any:
    """Validate approve / reject / request_changes before Command(resume=).

    Invalid payloads never reach ``graph.invoke``. Canonicalizes aliases
    (``approve`` → ``approved``) and requires the CONTEXT-named owner.
    """
    waiting = _pending_resume_departments(snapshot) if snapshot is not None else set()

    def _one(payload: Any) -> dict[str, Any]:
        decision = validate_human_resume(payload)
        dept = decision["department_id"]
        if waiting and dept not in waiting:
            raise InvalidResumeDecisionError(
                f"{dept!r} is not waiting for a human decision"
            )
        return decision

    if _is_interrupt_id_map(resume):
        return {str(iid): _one(value) for iid, value in resume.items()}
    return _one(resume if isinstance(resume, dict) else {"decision": resume})


def _applied_resume_update(
    snapshot: Any, decision: dict[str, Any]
) -> dict[str, Any]:
    """Persist a validated decision on the resume Command itself.

    ``apply_approval`` can still run (idempotent). Sibling interrupts
    otherwise skip that node and leave SQL/state as ``pending``.
    """
    values = dict(getattr(snapshot, "values", None) or {})
    dept = str(decision.get("department_id") or "").strip()
    if dept == CEO_DEPARTMENT_ID:
        applied = _apply_ceo_decision(values, decision)
    else:
        applied = _apply_department_decision(values, decision)
    return {**applied, "resume_decision": decision}


def resume_command(graph: Any, config: dict[str, Any], resume: Any) -> Any:
    """Enter ``apply_approval`` on the existing checkpoint — never START.

    Pending interrupts are resumed by id so only that Send branch continues.
    A single decision is persisted on ``Command.update`` (and SQL) here so
    the write lands even when sibling department interrupts stay open and
    ``apply_approval`` is skipped. ``goto=apply_approval`` remains so the
    node can still run when LangGraph schedules it. A multi-id resume map
    lets each paused node ``Command(goto=apply_approval)`` itself.
    """
    if resume is None:
        return None
    if _is_interrupt_id_map(resume):
        return Command(resume=resume)
    snapshot = graph.get_state(config)
    decision = dict(resume) if isinstance(resume, dict) else {"decision": resume}
    mapping, _leftover = match_interrupt_resumes(snapshot, [decision])
    update = _applied_resume_update(snapshot, decision)
    if mapping:
        return Command(resume=mapping, goto=APPLY_APPROVAL_NODE, update=update)
    return Command(goto=APPLY_APPROVAL_NODE, update=update)


def enrich_interrupt_state(final: dict[str, Any]) -> dict[str, Any]:
    """Mark HITL pause on invoke results that stopped at ``interrupt()``."""
    payloads = interrupt_payloads(final)
    if not payloads:
        return final
    out = dict(final)
    out["paused"] = True
    out["status"] = str(out.get("status") or STATUS_WAITING_FOR_APPROVAL)
    pending: list[dict[str, Any]] = []
    for payload in payloads:
        extra = payload.get("pending")
        if extra:
            pending.extend(list(extra))
        elif payload.get("department_id"):
            pending.append(payload)
    if pending:
        out["pending_approvals"] = pending
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
    load_input = {
        "ticket_id": ticket_id,
        "status": state.get("status"),
        "section_count": len(state.get("sections") or []),
    }
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
            "trace": _event(
                state,
                "load_handoff",
                input=load_input,
                output={"error": str(exc)},
                error=str(exc),
            ),
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
        current = dict(approvals.get(dept) or {})
        normalized = normalize_section_approval_status(current.get("approval_status"))
        approvals[dept] = {
            "department_id": dept,
            "approval_status": normalized,
            "approver": current.get("approver"),
            "approved_at": current.get("approved_at"),
        }
    # Align section rows with normalized approvals (no status jump / data loss).
    for section in sections:
        dept = str(section.get("department_id") or "")
        if dept in approvals:
            section["approval_status"] = approvals[dept]["approval_status"]
    iterations = dict(state.get("approval_iterations") or {})
    max_iters = int(
        state.get("max_approval_iterations") or MAX_DEPARTMENT_APPROVAL_ITERATIONS
    )
    _persist(
        ticket_id,
        status=STATUS_WAITING_FOR_APPROVAL,
        approvals=approvals,
        requires_ceo_approval=ceo_needed,
        approval_iterations=iterations,
    )
    out = {
        "ticket_id": ticket_id,
        "departments": needed,
        "requires_ceo_approval": ceo_needed,
        "reparse_pdf_required": False,
        "max_approval_iterations": max_iters,
    }
    return {
        "ticket_id": ticket_id,
        "status": STATUS_WAITING_FOR_APPROVAL,
        "sections": sections,
        "departments_needed": needed,
        "requires_ceo_approval": ceo_needed,
        "approvals": approvals,
        "approval_iterations": iterations,
        "max_approval_iterations": max_iters,
        "paused": False,
        "error_message": None,
        "trace": _event(
            state,
            "load_handoff",
            input=load_input,
            output=out,
            ticket_id=ticket_id,
            departments=needed,
            requires_ceo_approval=ceo_needed,
            reparse_pdf_required=False,
        ),
    }


def surface_conflicts_node(state: RfpApprovalState) -> dict[str, Any]:
    if state.get("error_message"):
        return {}
    sections = list(state.get("sections") or [])
    metadata = dict(state.get("metadata") or {})
    surface_input = {
        "departments": [s.get("department_id") for s in sections],
        "requires_ceo_approval": bool(state.get("requires_ceo_approval")),
    }
    conflicts = conflict_surface_agent(
        sections=sections,
        metadata=metadata,
        requires_ceo_flag=bool(state.get("requires_ceo_approval")),
        ceo_approval=state.get("ceo_approval"),
    )
    trigger_ids = [c.get("trigger_id") for c in conflicts]
    return {
        "conflicts": conflicts,
        "trace": _event(
            state,
            "surface_conflicts",
            agent="conflict_surface_agent",
            input=surface_input,
            output={"trigger_ids": trigger_ids, "conflict_count": len(conflicts)},
            trigger_ids=trigger_ids,
            agent_name="conflict_surface_agent",
            resolved=False,
        ),
    }


def arbitration_node(state: RfpApprovalState) -> dict[str, Any]:
    """Dedicated graph node: CONTEXT §7 table, not LLM consensus."""
    if state.get("error_message"):
        return {}
    conflicts = list(state.get("conflicts") or [])
    arb_input = {
        "trigger_ids": [c.get("trigger_id") for c in conflicts],
        "mode": "fixed_arbiter_table",
    }
    resolutions = apply_fixed_arbitration(conflicts)
    # Hard guard: arbitration never marks itself as LLM-resolved.
    for row in resolutions:
        row["llm_resolved"] = False
    approvals = dict(state.get("approvals") or {})
    forced = request_changes_departments(resolutions)
    iterations = dict(state.get("approval_iterations") or {})
    limit = int(
        state.get("max_approval_iterations") or MAX_DEPARTMENT_APPROVAL_ITERATIONS
    )
    exceeded: list[str] = []
    if forced:
        iterations, exceeded = bump_department_iterations(
            iterations, forced, limit=limit
        )
    for dept in forced:
        current = dict(approvals.get(dept) or {"department_id": dept})
        if current.get("approval_status") != "approved":
            current["approval_status"] = RESOLUTION_ACTION_REQUEST_CHANGES
            current["arbiter_forced"] = True
            approvals[dept] = current
    ceo_status = str((state.get("ceo_approval") or {}).get("approval_status") or "pending")
    blocked = synthesizer_blocked_by_arbitration(
        resolutions, ceo_approval_status=ceo_status
    )
    if exceeded:
        message = iteration_limit_error(exceeded)
        _persist(
            str(state.get("ticket_id") or ""),
            status=STATUS_NEEDS_HUMAN_REVIEW,
            approvals=approvals,
            arbitration=resolutions,
            conflicts=conflicts,
            approval_iterations=iterations,
            synthesizer_blocked=True,
        )
        return {
            "arbitration": resolutions,
            "approvals": approvals,
            "approval_iterations": iterations,
            "synthesizer_blocked": True,
            "status": STATUS_NEEDS_HUMAN_REVIEW,
            "error_message": message,
            "block_reason": message,
            "paused": False,
            "trace": _event(
                state,
                "arbitration",
                agent="fixed_arbitration",
                input=arb_input,
                output={
                    "trigger_ids": [r.get("trigger_id") for r in resolutions],
                    "arbiters": [r.get("arbiter") for r in resolutions],
                    "llm_resolved": False,
                    "exceeded_departments": exceeded,
                    "approval_iterations": iterations,
                },
                trigger_ids=[r.get("trigger_id") for r in resolutions],
                arbiters=[r.get("arbiter") for r in resolutions],
                llm_resolved=False,
                exceeded=exceeded,
            ),
        }
    _persist(
        str(state.get("ticket_id") or ""),
        status=STATUS_WAITING_FOR_APPROVAL,
        approvals=approvals,
        arbitration=resolutions,
        conflicts=conflicts,
        approval_iterations=iterations,
    )
    return {
        "arbitration": resolutions,
        "approvals": approvals,
        "approval_iterations": iterations,
        "synthesizer_blocked": blocked,
        "trace": _event(
            state,
            "arbitration",
            agent="fixed_arbitration",
            input=arb_input,
            output={
                "trigger_ids": [r.get("trigger_id") for r in resolutions],
                "arbiters": [r.get("arbiter") for r in resolutions],
                "llm_resolved": False,
                "request_changes_departments": forced,
                "approval_iterations": iterations,
            },
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
            "trace": _event(
                state,
                "apply_approval",
                input={"department_id": dept, "decision": decision.get("decision")},
                output={"error": str(exc)},
                error=str(exc),
            ),
        }
    stamp = _now()
    iterations = dict(state.get("approval_iterations") or {})
    limit = int(
        state.get("max_approval_iterations") or MAX_DEPARTMENT_APPROVAL_ITERATIONS
    )
    if mapped == RESOLUTION_ACTION_REQUEST_CHANGES:
        iterations, exceeded = bump_department_iterations(
            iterations, [dept], limit=limit
        )
        if exceeded:
            message = iteration_limit_error(exceeded)
            record = {
                "department_id": dept,
                "approval_status": mapped,
                "approver": approver,
                "approved_at": None,
                "decided_at": stamp,
                "comment": decision.get("comment"),
            }
            _persist(
                str(state.get("ticket_id") or ""),
                status=STATUS_NEEDS_HUMAN_REVIEW,
                approvals={dept: record},
                approval_iterations=iterations,
                synthesizer_blocked=True,
            )
            return {
                "approvals": {dept: record},
                "approval_iterations": iterations,
                "status": STATUS_NEEDS_HUMAN_REVIEW,
                "error_message": message,
                "block_reason": message,
                "paused": False,
                "trace": _event(
                    state,
                    "apply_approval",
                    input={
                        "department_id": dept,
                        "decision": mapped,
                        "approver": approver,
                    },
                    output={
                        "exceeded": True,
                        "approval_iterations": iterations,
                        "error": message,
                    },
                    department_id=dept,
                    decision=mapped,
                    approver=approver,
                    exceeded=True,
                ),
            }
    record = {
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
        approvals={dept: record},
        approval_iterations=iterations,
    )
    return {
        "approvals": {dept: record},
        "approval_iterations": iterations,
        "trace": _event(
            state,
            "apply_approval",
            input={"department_id": dept, "decision": mapped, "approver": approver},
            output={"approval_status": mapped, "approver": approver},
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
            "trace": _event(state, "apply_approval", error=str(exc)),
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
            "apply_approval",
            decision=mapped,
            approver=approver,
        ),
    }


def collect_approvals_node(state: RfpApprovalState) -> Any:
    """One department branch. Interrupt only if this section is still pending.

    After ``interrupt()`` returns, route into ``apply_approval`` — do not
    persist the decision in this node, and do not fall through a static edge.
    """
    if state.get("error_message"):
        return Command(goto=END)
    dept = str(state.get("department_id") or "").strip()
    if not dept:
        pending = _pending_department_signoffs(state)
        if not pending:
            return Command(
                goto="join_approvals",
                update={
                    "pending_approvals": [],
                    "paused": False,
                    "trace": _event(state, "collect_approvals", pending=0),
                },
            )
        dept = str(pending[0]["department_id"])

    status = _dept_status(state, dept)
    if status != "pending":
        # Already decided — do not interrupt this branch or sibling branches.
        return Command(
            goto="join_approvals",
            update={
                "trace": _event(
                    state,
                    "collect_approvals",
                    department_id=dept,
                    skipped=True,
                    status=status,
                ),
            },
        )

    signoffs = {
        s.department_id: s
        for s in signoffs_for_ticket([dept], requires_ceo=False)
    }
    target = signoffs.get(dept)
    approver = target.approver if target else ""
    ticket_id = str(state.get("ticket_id") or "")
    resumed = _interrupt(
        {
            "kind": "department_approval",
            "ticket_id": ticket_id,
            "department_id": dept,
            "approver": approver,
            "pending": [
                {
                    "department_id": dept,
                    "approver": approver,
                    "role": "department_owner",
                    "approval_status": "pending",
                }
            ],
        }
    )
    resumed.setdefault("department_id", dept)
    if not resumed.get("approver"):
        resumed["approver"] = approver
    return _goto_apply_approval(ticket_id=ticket_id, decision=resumed)


def fanout_department_approvals(state: RfpApprovalState) -> list[Send] | str:
    """Send one collect_approvals task per *pending* department.

    Departments already approved / rejected / request_changes are not sent,
    so their completed work is not paused by another department's interrupt.
    """
    if state.get("error_message"):
        return END
    pending = _pending_department_signoffs(state)
    if not pending:
        return "ceo_gate"
    ticket_id = str(state.get("ticket_id") or "")
    approvals = dict(state.get("approvals") or {})
    return [
        Send(
            "collect_approvals",
            {
                "ticket_id": ticket_id,
                "department_id": row["department_id"],
                "departments_needed": list(state.get("departments_needed") or []),
                "approvals": approvals,
            },
        )
        for row in pending
    ]


def ceo_gate_node(state: RfpApprovalState) -> Any:
    """CEO interrupt, then ``Command(goto=apply_approval)`` — never apply here."""
    if state.get("error_message"):
        return Command(goto=END)
    if not state.get("requires_ceo_approval"):
        return Command(
            goto="synthesizer",
            update={
                "synthesizer_blocked": False,
                "trace": _event(state, "ceo_gate", required=False),
            },
        )

    ceo = dict(state.get("ceo_approval") or {})
    status = str(ceo.get("approval_status") or "pending")
    if status == "approved":
        return Command(
            goto="synthesizer",
            update={
                "synthesizer_blocked": False,
                "paused": False,
                "trace": _event(state, "ceo_gate", required=True, status="approved"),
            },
        )
    if status == "rejected":
        return Command(
            goto=END,
            update={
                "synthesizer_blocked": True,
                "paused": False,
                "status": STATUS_WAITING_FOR_APPROVAL,
                "block_reason": f"CEO {CEO_NAME} rejected",
                "trace": _event(state, "ceo_gate", required=True, status="rejected"),
            },
        )
    if status != "pending":
        return Command(
            goto="synthesizer",
            update={
                "synthesizer_blocked": True,
                "paused": False,
                "status": STATUS_WAITING_FOR_APPROVAL,
                "block_reason": f"CEO {CEO_NAME} {status}",
                "trace": _event(state, "ceo_gate", required=True, status=status),
            },
        )

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
    return _goto_apply_approval(
        ticket_id=ticket_id,
        decision=resumed,
        extra={"requires_ceo_approval": True},
    )


def synthesizer_node(state: RfpApprovalState) -> dict[str, Any]:
    """Completion: after every required approval, consolidate approved sections."""
    if state.get("error_message"):
        return {"status": "failed"}
    approvals = state.get("approvals") or {}
    needed = list(state.get("departments_needed") or [])
    dept_status = {
        dept: str((approvals.get(dept) or {}).get("approval_status") or "pending")
        for dept in needed
    }
    ceo_status = str((state.get("ceo_approval") or {}).get("approval_status") or "pending")
    changes = [
        dept for dept, status in dept_status.items() if status == "request_changes"
    ]
    synth_input = {
        "departments_needed": needed,
        "department_approvals": dept_status,
        "requires_ceo_approval": bool(state.get("requires_ceo_approval")),
        "ceo_approval_status": ceo_status if state.get("requires_ceo_approval") else None,
    }
    ready, blocker = synthesizer_ready(
        department_approvals=dept_status,
        departments_needed=needed,
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
            "trace": _event(
                state,
                "synthesizer",
                input=synth_input,
                output={"blocked": True, "reason": blocker},
                blocked=True,
                reason=blocker,
            ),
        }

    document = build_final_document(
        ticket_id=str(state.get("ticket_id") or ""),
        sections=list(state.get("sections") or []),
        metadata=dict(state.get("metadata") or {}),
        departments_needed=needed,
        approvals=approvals,
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
            input=synth_input,
            output={
                "ticket_id": document["ticket_id"],
                "section_ids": [s["department_id"] for s in document.get("sections") or []],
                "total_estimated_value": document.get("total_estimated_value"),
                "generated_at": document.get("generated_at"),
                "completion": "consolidated_approved_sections",
            },
            ticket_id=document["ticket_id"],
            total_estimated_value=document.get("total_estimated_value"),
            consolidated_departments=[
                s["department_id"] for s in document.get("sections") or []
            ],
        ),
    }


def apply_approval_node(state: RfpApprovalState) -> dict[str, Any]:
    """Explicit resume entry: persist one named-owner (or CEO) decision."""
    decision = dict(state.get("resume_decision") or {})
    if not decision:
        return {
            "resume_decision": {},
            "trace": _event(state, APPLY_APPROVAL_NODE, skipped=True),
        }
    dept = str(decision.get("department_id") or state.get("department_id") or "").strip()
    if dept:
        decision["department_id"] = dept
    if dept == CEO_DEPARTMENT_ID:
        out = _apply_ceo_decision(state, decision)
    else:
        out = _apply_department_decision(state, decision)
    out["resume_decision"] = {}
    return out


def join_approvals_node(state: RfpApprovalState) -> dict[str, Any]:
    """Wait until every department branch has finished (done or still interrupted)."""
    pending = _pending_department_signoffs(state)
    if pending:
        return {
            "status": STATUS_WAITING_FOR_APPROVAL,
            "paused": True,
            "pending_approvals": pending,
            "trace": _event(
                state,
                "join_approvals",
                pending=[p["department_id"] for p in pending],
            ),
        }
    return {
        "paused": False,
        "pending_approvals": [],
        "trace": _event(state, "join_approvals", pending=0),
    }


def _after_join(state: RfpApprovalState) -> str:
    if state.get("error_message"):
        return "end"
    if _pending_department_signoffs(state):
        return "end"
    return "ceo_gate"


def _after_load(state: RfpApprovalState) -> str:
    if state.get("error_message"):
        return "end"
    return "surface_conflicts"


def build_rfp_approval_graph(*, checkpointer: Any | None = None) -> Any:
    graph = StateGraph(RfpApprovalState)
    graph.add_node("load_handoff", load_handoff_node)
    graph.add_node("surface_conflicts", surface_conflicts_node)
    graph.add_node("arbitration", arbitration_node)
    graph.add_node("collect_approvals", collect_approvals_node)
    graph.add_node(APPLY_APPROVAL_NODE, apply_approval_node)
    graph.add_node("join_approvals", join_approvals_node)
    graph.add_node("ceo_gate", ceo_gate_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.add_edge(START, "load_handoff")
    graph.add_conditional_edges(
        "load_handoff",
        _after_load,
        {"surface_conflicts": "surface_conflicts", "end": END},
    )
    graph.add_edge("surface_conflicts", "arbitration")
    graph.add_conditional_edges("arbitration", fanout_department_approvals)
    # collect_approvals / ceo_gate route with Command.goto so resume cannot
    # also fall through a static edge into synthesizer or join.
    graph.add_edge(APPLY_APPROVAL_NODE, "join_approvals")
    graph.add_conditional_edges(
        "join_approvals",
        _after_join,
        {"ceo_gate": "ceo_gate", "end": END},
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
    department_id: str | None = None,
) -> dict[str, Any]:
    """Always pass a ticket-namespaced ``thread_id``.

    Identity is ``RFP-{ticket_id}`` (HTTP start/resume) or
    ``RFP-{ticket_id}:{department}`` when a branch is checkpointed alone.
    Concurrent tickets never share a checkpoint. Fresh non-HTTP runs use
    ``RFP-{ticket_id}:run-{uuid}``.
    """
    if thread_id:
        tid = ensure_rfp_thread_id(thread_id, ticket_id)
    elif department_id:
        tid = rfp_checkpoint_thread_id(ticket_id, department_id=department_id)
    elif resume is not None:
        tid = approval_thread_id(ticket_id)
    else:
        tid = ephemeral_rfp_thread_id(ticket_id)
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
    approval_iterations: dict[str, int] | None = None,
    max_approval_iterations: int | None = None,
    queued_decisions: list[dict[str, Any]] | None = None,
    use_interrupt: bool = True,
    thread_id: str | None = None,
    resume: Any | None = None,
) -> RfpApprovalState:
    graph = get_compiled_rfp_approval_graph(use_interrupt=use_interrupt)
    meta = dict(metadata or {})
    seeded_iters = dict(approval_iterations or {})
    if not seeded_iters and isinstance(meta.get("approval_iterations"), dict):
        seeded_iters = {
            str(k): int(v) for k, v in meta.get("approval_iterations", {}).items()
        }
    max_iters = int(
        max_approval_iterations
        if max_approval_iterations is not None
        else MAX_DEPARTMENT_APPROVAL_ITERATIONS
    )
    initial: RfpApprovalState = {
        "ticket_id": ticket_id,
        "status": status,
        "sections": list(sections or []),
        "metadata": meta,
        "departments_needed": list(departments_needed or []),
        "part3_handoff": dict(part3_handoff or {}),
        "requires_ceo_approval": requires_ceo_approval,
        "approvals": dict(approvals or {}),
        "ceo_approval": dict(ceo_approval or {}),
        "approval_iterations": seeded_iters,
        "max_approval_iterations": max_iters,
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
        snapshot = graph.get_state(config)
        if not graph_is_paused(snapshot):
            return {
                "ticket_id": ticket_id,
                "status": status,
                "error_message": RESUME_NOT_PAUSED,
                "block_reason": RESUME_NOT_PAUSED_MESSAGE,
                "paused": False,
                "trace": [],
                "approvals": dict(approvals or {}),
                "ceo_approval": dict(ceo_approval or {}),
                "final_document": {},
                "pending_approvals": [],
            }
        try:
            resume = prepare_resume(resume, snapshot)
        except (UnknownApproverError, InvalidResumeDecisionError, ValueError) as exc:
            return {
                "ticket_id": ticket_id,
                "status": STATUS_WAITING_FOR_APPROVAL,
                "error_message": str(exc),
                "paused": True,
                "trace": [],
                "approvals": dict(approvals or {}),
                "ceo_approval": dict(ceo_approval or {}),
                "final_document": {},
                "pending_approvals": [],
            }
        return graph.invoke(resume_command(graph, config, resume), config=config)
    return graph.invoke(initial, config=config)
