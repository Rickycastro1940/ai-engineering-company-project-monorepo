"""Evaluate: Part 3 uses a dedicated rfp_approval LangGraph (not the CX agent)."""

from __future__ import annotations

import ast
from pathlib import Path

from data.pipelines.rfp_approval import (
    REQUIRED_APPROVAL_NODES,
    build_rfp_approval_graph,
    get_compiled_rfp_approval_graph,
)
from data.pipelines.rfp_approval.conflicts import conflict_surface_agent
from data.pipelines.rfp_approval.graph import (
    APPLY_APPROVAL_NODE,
    arbitration_node,
    apply_approval_node,
    ceo_gate_node,
    collect_approvals_node,
    load_handoff_node,
    surface_conflicts_node,
    synthesizer_node,
)

REPO = Path(__file__).resolve().parents[2]
PIPELINE = REPO / "data" / "pipelines" / "rfp_approval"
CX_GRAPH = REPO / "services" / "agent" / "graph.py"


def test_required_nodes_include_arbitration_hitl_and_synthesizer() -> None:
    assert REQUIRED_APPROVAL_NODES == (
        "load_handoff",
        "surface_conflicts",
        "arbitration",
        "collect_approvals",
        APPLY_APPROVAL_NODE,
        "ceo_gate",
        "synthesizer",
    )
    nodes = (
        load_handoff_node,
        surface_conflicts_node,
        arbitration_node,
        collect_approvals_node,
        apply_approval_node,
        ceo_gate_node,
        synthesizer_node,
    )
    assert len({id(n) for n in nodes}) == len(nodes)
    assert callable(conflict_surface_agent)


def test_compiled_graph_registers_separate_nodes() -> None:
    compiled = build_rfp_approval_graph()
    registered = set(compiled.get_graph().nodes)
    for name in REQUIRED_APPROVAL_NODES:
        assert name in registered, name
    assert get_compiled_rfp_approval_graph() is not None
    graph_src = (PIPELINE / "graph.py").read_text(encoding="utf-8")
    assert "Send(" in graph_src
    assert "fanout_department_approvals" in graph_src
    assert APPLY_APPROVAL_NODE in registered
    assert "Command(" in graph_src
    assert "goto=APPLY_APPROVAL_NODE" in graph_src or 'goto=Send(' in graph_src


def test_cx_graph_has_no_rfp_approval_nodes() -> None:
    src = CX_GRAPH.read_text(encoding="utf-8")
    assert "rfp_approval" not in src
    assert "collect_approvals" not in src
    assert "ceo_gate" not in src
    assert "surface_conflicts" not in src


def test_pipeline_lives_under_data_pipelines_and_has_no_http() -> None:
    assert (PIPELINE / "graph.py").is_file()
    for path in PIPELINE.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        lower = src.casefold()
        assert "fastapi" not in lower
        assert "apirouter" not in lower
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("services.agent")
