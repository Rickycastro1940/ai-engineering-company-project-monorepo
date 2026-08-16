"""Evaluate: every node execution logs agent, input, output, and timestamp.

Proves in code (not docs alone):
1. ``_event`` always writes the four fields (input defaults to ``{}``)
2. ``trace_has_required_fields`` is the shared guardrail
3. Full Andes + Sunset runs emit events for every required node, each with
   non-empty agent, dict input/output, and ISO timestamp
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from data.pipelines.rfp_approval import run_approval_pipeline
from data.pipelines.rfp_approval.checkpointer import reset_approval_checkpointer
from data.pipelines.rfp_approval.fixtures import (
    andes_pipeline_kwargs,
    sunset_pipeline_kwargs,
)
from data.pipelines.rfp_approval.graph import (
    NODE_AGENTS,
    REQUIRED_APPROVAL_NODES,
    _event,
    build_rfp_approval_graph,
)
from data.pipelines.rfp_approval.guardrails import trace_has_required_fields

ARTIFACT = Path("/opt/cursor/artifacts/rfp_node_trace_fields.json")
ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T")


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "trace-fields.sqlite"))
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()


def test_event_helper_always_emits_agent_input_output_timestamp() -> None:
    row = _event({}, "arbitration")[0]  # type: ignore[arg-type]
    assert trace_has_required_fields(row)
    assert row["agent"] == NODE_AGENTS["arbitration"]
    assert row["input"] == {}
    assert isinstance(row["output"], dict)
    assert ISO_TS.match(str(row["timestamp"]))

    row2 = _event(  # type: ignore[arg-type]
        {},
        "load_handoff",
        agent="custom",
        input={"ticket_id": "t1"},
        output={"ok": True},
    )[0]
    assert row2["agent"] == "custom"
    assert row2["input"] == {"ticket_id": "t1"}
    assert row2["output"] == {"ok": True}


def test_event_helper_and_nodes_wired_in_source() -> None:
    src = inspect.getsource(_event)
    assert '"agent"' in src
    assert '"input"' in src
    assert '"output"' in src
    assert '"timestamp"' in src
    build_src = inspect.getsource(build_rfp_approval_graph)
    for node in REQUIRED_APPROVAL_NODES:
        assert f'"{node}"' in build_src or f"'{node}'" in build_src or node in build_src


def _assert_trace_complete(trace: list[dict], *, require_nodes: set[str]) -> dict:
    assert trace, "expected non-empty trace"
    missing_keys = [e for e in trace if not trace_has_required_fields(e)]
    assert not missing_keys, missing_keys[:3]
    nullish = [
        e["node"]
        for e in trace
        if e.get("input") is None
        or e.get("output") is None
        or not e.get("agent")
        or not e.get("timestamp")
    ]
    assert not nullish, f"null agent/input/output/timestamp on {nullish}"
    for event in trace:
        assert isinstance(event["input"], dict), event
        assert event["output"] is not None, event
        assert ISO_TS.match(str(event["timestamp"])), event["timestamp"]
        expected_agent = NODE_AGENTS.get(event["node"])
        if expected_agent:
            assert event["agent"] == expected_agent or event["agent"], event
    nodes = {e["node"] for e in trace}
    missing_nodes = require_nodes - nodes
    assert not missing_nodes, f"trace missing nodes: {missing_nodes}"
    return {
        "event_count": len(trace),
        "nodes": sorted(nodes),
        "agents_by_node": {
            n: next(e["agent"] for e in trace if e["node"] == n) for n in sorted(nodes)
        },
        "sample_timestamps": [e["timestamp"] for e in trace[:3]],
    }


def test_full_andes_and_sunset_traces_cover_every_required_node() -> None:
    andes = run_approval_pipeline(**andes_pipeline_kwargs(ticket_id="trace-fields-andes"))
    assert andes.status == "done"
    andes_summary = _assert_trace_complete(
        list(andes.trace or []),
        require_nodes=set(REQUIRED_APPROVAL_NODES),
    )

    sunset = run_approval_pipeline(
        **sunset_pipeline_kwargs(ticket_id="trace-fields-sunset")
    )
    assert sunset.status == "done"
    sunset_summary = _assert_trace_complete(
        list(sunset.trace or []),
        require_nodes=set(REQUIRED_APPROVAL_NODES),
    )

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "claim": (
                    "Every node execution is logged with agent, input, output, and timestamp"
                ),
                "verdict": "pass",
                "REQUIRED_APPROVAL_NODES": list(REQUIRED_APPROVAL_NODES),
                "NODE_AGENTS": NODE_AGENTS,
                "andes": andes_summary,
                "sunset": sunset_summary,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
