"""Evaluate: each CONTEXT department has its own generator agent, clearly separated.

A single generic generator with a department switch is not accepted.
Agents must be distinct classes/instances, refuse other departments' Part 1
summaries, and emit that department's §2.1 section — not a copy of another.
"""

from __future__ import annotations

import ast
import inspect
from itertools import permutations
from pathlib import Path

import pytest

from data.pipelines.rfp_intake.constants import DEPARTMENT_IDS
from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_DEPARTMENT_IDS,
    CONTEXT_DEPARTMENT_OWNERS,
    CONTEXT_SECTION_REQUIRED_HEADINGS,
    FORBIDDEN_DEPARTMENT_IDS,
    parse_context_department_table,
)
from data.pipelines.rfp_response.agents import (
    GENERATOR_AGENTS,
    DepartmentGeneratorAgent,
    MarketingGeneratorAgent,
    OperacionesGeneratorAgent,
    Part1DepartmentSummary,
    ProcurementGeneratorAgent,
    TrainingGeneratorAgent,
    get_generator_agent,
    run_generator_agent,
)
from data.pipelines.rfp_response.compliance_rules import SECTION_REQUIRED_HEADINGS
from data.pipelines.rfp_response.loop import run_section_loop

REPO = Path(__file__).resolve().parents[2]
AGENTS_SRC = REPO / "data" / "pipelines" / "rfp_response" / "agents.py"
LOOP_SRC = REPO / "data" / "pipelines" / "rfp_response" / "loop.py"
GRAPH_SRC = REPO / "data" / "pipelines" / "rfp_response" / "graph.py"

_EXPECTED_CLASSES = {
    "marketing": MarketingGeneratorAgent,
    "operaciones": OperacionesGeneratorAgent,
    "procurement": ProcurementGeneratorAgent,
    "training": TrainingGeneratorAgent,
}


def _summary(department_id: str) -> Part1DepartmentSummary:
    owner = CONTEXT_DEPARTMENT_OWNERS[department_id]
    return Part1DepartmentSummary(
        department_id=department_id,
        owner=owner,
        key_aspects=[
            f"{department_id} key aspects for Synthetic Co — {owner}",
            "Part 1 handoff summary only; do not re-read the PDF",
        ],
        metadata={
            "client_name": "Synthetic Co",
            "location": "Bogotá",
            "service_type": "co-branding",
        },
    )


def test_context_section_2_1_has_four_departments_each_with_an_agent() -> None:
    rows = parse_context_department_table()
    parsed_ids = tuple(r["department_id"] for r in rows)
    assert parsed_ids == CONTEXT_DEPARTMENT_IDS
    assert set(parsed_ids) == set(DEPARTMENT_IDS)
    assert set(GENERATOR_AGENTS) == set(parsed_ids)
    assert len(GENERATOR_AGENTS) == 4


def test_each_department_maps_to_a_distinct_generator_class_and_instance() -> None:
    seen_types: set[type] = set()
    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    for dept_id, cls in _EXPECTED_CLASSES.items():
        agent = get_generator_agent(dept_id)
        assert agent is GENERATOR_AGENTS[dept_id]
        assert type(agent) is cls
        assert isinstance(agent, DepartmentGeneratorAgent)
        assert agent.department_id == dept_id
        assert agent.agent_name == f"{dept_id}_generator_agent"
        assert id(agent) not in seen_ids
        assert type(agent) not in seen_types
        assert agent.agent_name not in seen_names
        seen_types.add(type(agent))
        seen_ids.add(id(agent))
        seen_names.add(agent.agent_name)
    assert len(seen_types) == 4
    assert len(seen_ids) == 4


def test_agents_source_defines_four_separate_subclasses() -> None:
    """Physical separation: four class statements, each with its own body method."""
    source = AGENTS_SRC.read_text(encoding="utf-8")
    tree = ast.parse(source)
    subclasses: dict[str, ast.ClassDef] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = [
            b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")
            for b in node.bases
        ]
        if "DepartmentGeneratorAgent" in bases and node.name != "DepartmentGeneratorAgent":
            subclasses[node.name] = node
    assert set(subclasses) == {
        "MarketingGeneratorAgent",
        "OperacionesGeneratorAgent",
        "ProcurementGeneratorAgent",
        "TrainingGeneratorAgent",
    }
    for name, cls in subclasses.items():
        methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
        assert "build_pricing_proposal_section" in methods, name
        segment = ast.get_source_segment(source, cls)
        assert segment is not None
        assert "build_pricing_proposal_section" in segment


def test_no_generic_or_forbidden_department_generator() -> None:
    src = AGENTS_SRC.read_text(encoding="utf-8")
    for banned in ("GenericGeneratorAgent", "SharedGeneratorAgent", "DefaultGeneratorAgent"):
        assert banned not in src
    names = {a.agent_name for a in GENERATOR_AGENTS.values()}
    for forbidden in FORBIDDEN_DEPARTMENT_IDS:
        with pytest.raises(KeyError):
            get_generator_agent(forbidden)
        assert f"{forbidden}_generator_agent" not in names


@pytest.mark.parametrize(
    "agent_dept,other_dept",
    list(permutations(CONTEXT_DEPARTMENT_IDS, 2)),
)
def test_agent_refuses_another_department_part1_summary(
    agent_dept: str, other_dept: str
) -> None:
    agent = get_generator_agent(agent_dept)
    with pytest.raises(ValueError, match=f"expected '{agent_dept}'"):
        agent.receive_part1_summary(_summary(other_dept))
    with pytest.raises(ValueError, match=f"expected '{agent_dept}'"):
        agent.generate(_summary(other_dept))


def test_generated_sections_are_not_interchangeable() -> None:
    """Each agent emits its own §2.1 headings and must not emit another dept's."""
    drafts: dict[str, str] = {}
    for dept_id in CONTEXT_DEPARTMENT_IDS:
        result = run_generator_agent(_summary(dept_id))
        assert result.generator_agent == f"{dept_id}_generator_agent"
        assert result.department_id == dept_id
        assert CONTEXT_DEPARTMENT_OWNERS[dept_id] in result.draft_content
        drafts[dept_id] = result.draft_content
        for heading in SECTION_REQUIRED_HEADINGS[dept_id]:
            assert f"## {heading}" in result.draft_content

    for dept_id, other in permutations(CONTEXT_DEPARTMENT_IDS, 2):
        assert drafts[dept_id] != drafts[other]
        for heading in CONTEXT_SECTION_REQUIRED_HEADINGS[other]:
            assert f"## {heading}" not in drafts[dept_id], (
                f"{dept_id} draft unexpectedly contains {other} heading {heading!r}"
            )


def test_loop_and_graph_dispatch_the_matching_department_agent() -> None:
    loop_src = LOOP_SRC.read_text(encoding="utf-8")
    graph_src = GRAPH_SRC.read_text(encoding="utf-8")
    assert "get_generator_agent(summary.department_id)" in loop_src
    assert "Always the corresponding department generator" in loop_src
    assert "get_generator_agent(dept)" in graph_src
    assert "run_section_loop" in graph_src

    result = run_section_loop(
        summary=_summary("procurement"),
        max_iterations=1,
    )
    assert result.generator_agent == "procurement_generator_agent"
    assert result.department_id == "procurement"
    assert result.history[0]["generator_agent"] == "procurement_generator_agent"


def test_each_agent_class_is_defined_in_agents_module() -> None:
    for cls in _EXPECTED_CLASSES.values():
        module = inspect.getmodule(cls)
        assert module is not None
        assert module.__name__ == "data.pipelines.rfp_response.agents"
        assert cls.__name__.endswith("GeneratorAgent")
        assert cls is not DepartmentGeneratorAgent
        assert inspect.isabstract(DepartmentGeneratorAgent)
        assert not inspect.isabstract(cls)
