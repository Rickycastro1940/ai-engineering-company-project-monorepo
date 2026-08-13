"""Evaluate: orchestrator / worker / synthesizer are separate agents on a dedicated rfp_intake graph.

CONTEXT §2.4: RFP pipeline/graph lives under data/pipelines/rfp_intake/ and must
not be mixed into services.agent.graph (CX support agent).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from data.pipelines.rfp_intake import (
    REQUIRED_RFP_NODES,
    build_rfp_intake_graph,
    get_compiled_rfp_intake_graph,
    invoke_rfp_intake_graph,
    run_intake_pipeline,
)
from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_TRAINING,
    STATUS_DISCARDED,
    STATUS_INTAKE_COMPLETE,
)
from data.pipelines.rfp_intake.context_rules import CONTEXT_SEED_EXPECTATIONS
from data.pipelines.rfp_intake.graph import (
    CX_GRAPH_FORBIDDEN_RFP_NODES,
    classifier_agent_node,
    convert_node,
    department_worker_node,
    orchestrator_node,
    readability_node,
    synthesizer_node,
)
from data.pipelines.rfp_intake.orchestration import (
    department_worker,
    orchestrator,
    synthesizer,
)
from services.agent.graph import REQUIRED_NODES as CX_REQUIRED_NODES

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
PIPELINE = REPO / "data" / "pipelines" / "rfp_intake"
CX_GRAPH = REPO / "services" / "agent" / "graph.py"


def test_separate_agent_callables_are_distinct() -> None:
    """Orchestrator, department_worker, and synthesizer are separate callables."""
    assert callable(orchestrator)
    assert callable(department_worker)
    assert callable(synthesizer)
    assert orchestrator is not department_worker
    assert department_worker is not synthesizer
    assert orchestrator is not synthesizer
    assert inspect.getmodule(orchestrator).__name__.endswith("orchestration")
    assert inspect.getmodule(department_worker).__name__.endswith("orchestration")
    assert inspect.getmodule(synthesizer).__name__.endswith("orchestration")


def test_graph_nodes_are_separate_callables() -> None:
    """Each dedicated-graph node is its own function (not one mega-node)."""
    nodes = (
        convert_node,
        readability_node,
        classifier_agent_node,
        orchestrator_node,
        department_worker_node,
        synthesizer_node,
    )
    assert len({id(n) for n in nodes}) == len(nodes)
    for name, fn in zip(REQUIRED_RFP_NODES, nodes, strict=True):
        assert callable(fn)
        assert name.replace("_agent", "") in fn.__name__ or name in fn.__name__


def test_required_rfp_nodes_include_orch_worker_synth() -> None:
    assert "orchestrator" in REQUIRED_RFP_NODES
    assert "department_worker" in REQUIRED_RFP_NODES
    assert "synthesizer" in REQUIRED_RFP_NODES
    assert "classifier_agent" in REQUIRED_RFP_NODES


def test_compiled_dedicated_graph_registers_separate_nodes() -> None:
    compiled = build_rfp_intake_graph()
    registered = set(compiled.get_graph().nodes)
    for name in REQUIRED_RFP_NODES:
        assert name in registered, f"missing dedicated graph node: {name}"
    # Same compiled singleton for runtime
    assert get_compiled_rfp_intake_graph() is not None
    assert set(get_compiled_rfp_intake_graph().get_graph().nodes) >= set(REQUIRED_RFP_NODES)


def test_cx_agent_graph_has_no_rfp_nodes_or_imports() -> None:
    """CX support-agent graph must stay free of RFP intake agents."""
    for name in CX_REQUIRED_NODES:
        assert "rfp" not in name.casefold()
        assert name not in CX_GRAPH_FORBIDDEN_RFP_NODES

    src = CX_GRAPH.read_text(encoding="utf-8")
    assert "rfp_intake" not in src
    assert "department_worker" not in src
    assert "orchestrator" not in src or "rfp" not in src.casefold()
    tree = ast.parse(src)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert not any("rfp_intake" in m for m in imports)


def test_graph_module_lives_under_data_pipelines_rfp_intake() -> None:
    assert (PIPELINE / "graph.py").is_file()
    src = (PIPELINE / "graph.py").read_text(encoding="utf-8")
    assert "StateGraph" in src
    assert "orchestrator_node" in src
    assert "department_worker_node" in src
    assert "synthesizer_node" in src
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("services.agent")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("services.agent")


def test_pipeline_trace_shows_separate_agent_nodes() -> None:
    result = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-1.pdf")
    assert result.status == STATUS_INTAKE_COMPLETE
    nodes = [e["node"] for e in result.trace]
    for required in (
        "convert",
        "readability",
        "classifier_agent",
        "orchestrator",
        "department_worker",
        "synthesizer",
    ):
        assert required in nodes, f"trace missing node {required}: {nodes}"
    # Workers are separate invocations (one trace event per department)
    worker_events = [e for e in result.trace if e["node"] == "department_worker"]
    assert len(worker_events) == len(result.departments_needed) >= 3


@pytest.mark.parametrize(
    "filename,expected_status",
    [
        ("CONTEXT-brasaland-request-1.pdf", STATUS_INTAKE_COMPLETE),
        ("CONTEXT-brasaland-request-2.pdf", STATUS_INTAKE_COMPLETE),
        ("CONTEXT-brasaland-request-3.pdf", STATUS_DISCARDED),
    ],
)
def test_invoke_dedicated_graph_matches_seed_outcomes(
    filename: str, expected_status: str
) -> None:
    path = SEEDS / filename
    final = invoke_rfp_intake_graph(pdf_path=path)
    assert final.get("status") == expected_status
    expectation = CONTEXT_SEED_EXPECTATIONS[filename]
    if expected_status == STATUS_DISCARDED:
        assert final.get("discard_reason")
        assert "orchestrator" not in [e["node"] for e in (final.get("trace") or [])]
    else:
        depts = set(final.get("departments_needed") or [])
        assert depts == set(expectation["departments"])
        if DEPARTMENT_TRAINING not in expectation["departments"]:
            assert DEPARTMENT_TRAINING not in (final.get("sections") or {})
        nodes = [e["node"] for e in (final.get("trace") or [])]
        assert nodes.index("orchestrator") < nodes.index("department_worker")
        assert nodes.index("department_worker") < nodes.index("synthesizer")
