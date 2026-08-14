"""Evaluate: evaluators run in parallel and do not block other departments.

Three evaluator agents (readability, relevance, compliance) fan out concurrently
per section. Department generate/evaluate loops also fan out so a slow
department does not block the others.
"""

from __future__ import annotations

import threading
from pathlib import Path

from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_OWNERS,
    DEPARTMENT_PROCUREMENT,
)
from data.pipelines.rfp_response.evaluators import (
    EVALUATOR_AGENTS,
    DimensionResult,
    EvaluationResult,
    EvaluatorContext,
    evaluate_section,
    run_evaluators_parallel,
)
from data.pipelines.rfp_response.graph import generate_evaluate_sections_node
from data.pipelines.rfp_response.loop import SectionLoopResult

REPO = Path(__file__).resolve().parents[2]
EVALUATORS_SRC = REPO / "data" / "pipelines" / "rfp_response" / "evaluators.py"
GRAPH_SRC = REPO / "data" / "pipelines" / "rfp_response" / "graph.py"


def _ok_dim(name: str, agent: str) -> DimensionResult:
    return DimensionResult(
        name=name, passed=True, score=1.0, evaluator_agent=agent
    )


def _ok_evaluation(department_id: str) -> EvaluationResult:
    return EvaluationResult(
        department_id=department_id,
        passed=True,
        readability=_ok_dim("readability", "readability_evaluator_agent"),
        relevance=_ok_dim("relevance", "relevance_evaluator_agent"),
        compliance=_ok_dim("compliance", "compliance_evaluator_agent"),
        parallel=True,
        evaluator_agents=[a.agent_name for a in EVALUATOR_AGENTS],
    )


def test_evaluator_and_department_pools_use_threadpoolexecutor() -> None:
    ev = EVALUATORS_SRC.read_text(encoding="utf-8")
    graph = GRAPH_SRC.read_text(encoding="utf-8")
    assert "ThreadPoolExecutor" in ev
    assert "as_completed" in ev
    assert "rfp-eval" in ev
    assert "def run_evaluators_parallel" in ev
    assert "ThreadPoolExecutor" in graph
    assert "as_completed" in graph
    assert "rfp-section-eval" in graph
    assert "max_workers" in graph


def test_three_evaluator_agents_rendezvous_in_parallel(monkeypatch) -> None:
    """If agents ran serially, Barrier(3) would time out."""
    barrier = threading.Barrier(parties=len(EVALUATOR_AGENTS), timeout=2.0)
    started: list[str] = []
    lock = threading.Lock()

    for agent in EVALUATOR_AGENTS:

        def _eval(ctx: EvaluatorContext, _agent=agent) -> DimensionResult:
            with lock:
                started.append(_agent.agent_name)
            barrier.wait()
            return _ok_dim(_agent.dimension, _agent.agent_name)

        monkeypatch.setattr(agent, "evaluate", _eval)

    ctx = EvaluatorContext(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content="# operaciones\nKitchen/staff capacity. Setup times. Cost per event.",
        key_aspects=["Operational feasibility for Andes Tech"],
        metadata={"client_name": "Andes Tech"},
    )
    dims = run_evaluators_parallel(ctx)
    assert set(dims) == {"readability", "relevance", "compliance"}
    assert set(started) == {a.agent_name for a in EVALUATOR_AGENTS}
    result = evaluate_section(
        department_id=DEPARTMENT_OPERACIONES,
        draft_content=ctx.draft_content,
        key_aspects=list(ctx.key_aspects),
        metadata=dict(ctx.metadata),
    )
    assert result.parallel is True


def test_department_loops_rendezvous_so_one_dept_does_not_block_others(
    monkeypatch,
) -> None:
    """Marketing sleeping cannot prevent operaciones/procurement from starting."""
    import data.pipelines.rfp_response.graph as graph_mod

    depts = (DEPARTMENT_MARKETING, DEPARTMENT_OPERACIONES, DEPARTMENT_PROCUREMENT)
    barrier = threading.Barrier(parties=len(depts), timeout=2.0)
    started: list[str] = []
    lock = threading.Lock()

    def _loop(*, summary, max_iterations=2, **_kwargs):
        dept = summary.department_id
        with lock:
            started.append(dept)
        barrier.wait()
        return SectionLoopResult(
            department_id=dept,
            owner=DEPARTMENT_OWNERS[dept],
            draft_content=f"# {dept} draft\n",
            evaluation=_ok_evaluation(dept),
            iterations=1,
            exhausted=False,
            generator_agent=f"{dept}_generator_agent",
            history=[{"generator_agent": f"{dept}_generator_agent", "passed": True}],
        )

    monkeypatch.setattr(graph_mod, "run_section_loop", _loop)

    state = generate_evaluate_sections_node(
        {
            "ticket_id": "parallel-depts",
            "synthesizer_payload": {
                "ticket_id": "parallel-depts",
                "metadata": {"client_name": "Andes Tech", "location": "Medellín"},
                "work_streams": [
                    {
                        "department_id": dept,
                        "owner": DEPARTMENT_OWNERS[dept],
                        "key_aspects": [f"{dept} key aspects for Andes Tech"],
                    }
                    for dept in depts
                ],
            },
            "max_iterations": 1,
            "trace": [],
        }
    )
    assert set(started) == set(depts)
    drafted = {r["department_id"] for r in state["section_results"]}
    assert drafted == set(depts)
    assert all(r["evaluation_results"]["parallel"] for r in state["section_results"])
    gen = [e for e in state["trace"] if e["node"] == "generate_evaluate_sections"]
    assert len(gen) == 3
    assert all(e["payload"]["evaluators_parallel"] is True for e in gen)
