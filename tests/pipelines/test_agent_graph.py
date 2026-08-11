"""LangGraph support-agent evals (Part 1).

Evals assert against the *trace* produced by a run (node order, routing, answer
grounding metadata). LLM / Qdrant calls are mocked so the suite is runnable
offline with a single command:

    uv run pytest tests/pipelines/ -q
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from data.pipelines.rag import NO_CONTEXT_ANSWER
from services.agent.graph import (
    GraphStructureError,
    build_agent_graph,
    compile_agent_graph,
    run_agent,
    validate_graph_structure,
)
from services.agent.tracing import load_trace

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTEXT_COMPANY = REPO_ROOT / "CONTEXT-company.md"
SUPPLIER_ORDERING_DOC = (
    REPO_ROOT / "docs" / "company-knowledge-base" / "brasaland-supplier-ordering.en.md"
)

# Known fact from docs/company-knowledge-base/brasaland-supplier-ordering.en.md
# and CONTEXT-company.md (Lucía Fernández / emergency approval > 500 USD).
PROTEIN_STOCK_CHUNK = {
    "source_document": "supplier-ordering",
    "section": "Minimum stock rule",
    "text": (
        "Minimum stock rule: no location should operate with less than 3 days of "
        "main protein inventory. An emergency order requires approval from "
        "Lucía Fernández (Procurement Manager) if it exceeds 500 USD."
    ),
    "_score": 0.91,
}
GROUNDED_ANSWER = (
    "Every Brasaland location must keep at least 3 days of main protein inventory. "
    "Emergency orders over 500 USD need approval from Lucía Fernández."
)


def _context_grounding_facts() -> dict[str, str]:
    """Load expected grounding entities from CONTEXT-company.md + KB source."""
    context_text = CONTEXT_COMPANY.read_text(encoding="utf-8")
    kb_text = SUPPLIER_ORDERING_DOC.read_text(encoding="utf-8")
    assert "Lucía Fernández" in context_text
    assert "500 USD" in context_text
    assert "3 days" in kb_text
    assert "Lucía Fernández" in kb_text
    return {
        "person": "Lucía Fernández",
        "threshold": "500 USD",
        "stock_rule": "3 days",
        "source_document": "supplier-ordering",
    }


def _assert_trace_retrieve_before_generate(trace: dict) -> None:
    order = trace["node_order"]
    assert "retrieve" in order and "generate" in order
    assert order.index("retrieve") < order.index("generate")


@pytest.fixture()
def trace_dir(tmp_path: Path) -> Path:
    return tmp_path / "traces"


@pytest.fixture()
def compiled_graph():
    """Fresh compiled graph per test (isolates MemorySaver state)."""
    return compile_agent_graph()


def _run_and_save_trace(question: str, trace_dir: Path, **node_patches) -> dict:
    """Run once (mocked), persist a trace, return the run result.

    Subsequent assertions should use ``load_trace`` — evals run against the
    saved trace, not a second live graph execution.
    """
    patchers = []
    for target, value in node_patches.items():
        p = patch(target, value)
        patchers.append(p)
        p.start()
    try:
        with patch("services.agent.tracing.DEFAULT_TRACE_DIR", trace_dir), patch(
            "services.agent.graph.save_trace"
        ) as mock_save:
            from services.agent.tracing import save_trace as real_save

            mock_save.side_effect = lambda record, **_: real_save(record, trace_dir=trace_dir)
            with patch("services.agent.graph._COMPILED_GRAPH", compile_agent_graph()):
                return run_agent(question)
    finally:
        for p in reversed(patchers):
            p.stop()


def test_graph_compiles_successfully(compiled_graph):
    """Compilation must succeed for a valid topology (fails loudly otherwise)."""
    assert compiled_graph is not None
    assert hasattr(compiled_graph, "invoke")


def test_compile_fails_clearly_on_missing_required_node():
    """Structural errors are caught before invoke — missing node → GraphStructureError."""
    graph = build_agent_graph()
    # Simulate a mistyped / incomplete topology
    del graph.nodes["retrieve"]
    with pytest.raises(GraphStructureError, match="missing required node"):
        validate_graph_structure(graph)


def test_agent_state_is_minimal_and_has_no_history_field():
    """State carries question / retrieved / answer — not full conversation history."""
    from services.agent.state import AgentState

    annotations = AgentState.__annotations__
    assert "question" in annotations
    assert "retrieved" in annotations
    assert "answer" in annotations
    # Full chat history must not sneak into Part 1 state
    assert "messages" not in annotations
    assert "history" not in annotations
    assert "conversation" not in annotations


def test_eval_retrieve_runs_before_generate(trace_dir: Path):
    """Eval 1 — for a grounded question, retrieve must run before generate (trace)."""
    result = _run_and_save_trace(
        "What is the minimum stock rule for proteins?",
        trace_dir,
        **{
            "services.agent.nodes.retrieve": lambda q: [PROTEIN_STOCK_CHUNK],
            "services.agent.nodes.generate_answer": lambda q, ctx: GROUNDED_ANSWER,
        },
    )
    # Evals run against the persisted trace — not a second live execution.
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    _assert_trace_retrieve_before_generate(trace)
    assert "decide_route" in trace["node_order"]
    retrieve_step = next(s for s in trace["steps"] if s["node_name"] == "retrieve")
    generate_step = next(s for s in trace["steps"] if s["node_name"] == "generate")
    assert retrieve_step["output"]["chunk_count"] == 1
    assert generate_step["node_name"] == "generate"


def test_eval_empty_question_skips_retrieve(trace_dir: Path):
    """Eval 2 — empty question routes to empty_question and never retrieves."""
    with patch("services.agent.nodes.retrieve") as mock_retrieve:
        result = _run_and_save_trace("   ", trace_dir)

    mock_retrieve.assert_not_called()
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert trace["status"] == "error"
    assert trace["error"] == "empty_question"
    assert trace["node_order"] == ["receive_question", "empty_question"]
    assert "decide_route" not in trace["node_order"]
    assert "retrieve" not in trace["node_order"]
    assert "generate" not in trace["node_order"]


def test_eval_no_context_when_retrieve_empty(trace_dir: Path):
    """Eval 3 — when retrieve returns nothing above threshold, use no_context."""
    with patch("services.agent.nodes.generate_answer") as mock_generate:
        result = _run_and_save_trace(
            "What is Brasaland's secret sauce recipe?",
            trace_dir,
            **{"services.agent.nodes.retrieve": lambda q: []},
        )

    mock_generate.assert_not_called()
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert trace["status"] == "ok"
    assert trace["answer"] == NO_CONTEXT_ANSWER
    assert trace["node_order"] == [
        "receive_question",
        "decide_route",
        "recall_memory",
        "retrieve",
        "no_context",
    ]
    assert "generate" not in trace["node_order"]
    retrieve_step = next(s for s in trace["steps"] if s["node_name"] == "retrieve")
    assert retrieve_step["output"]["chunk_count"] == 0


def test_eval_answer_grounded_in_context_knowledge_base(trace_dir: Path):
    """Eval 4 (grounding) — answer must cite CONTEXT-company.md / KB facts.

    Grounding remains an acceptance gate: a perfect trace that ignores CONTEXT
    policies is still a failure. Facts come from CONTEXT-company.md and
    brasaland-supplier-ordering.en.md (3 days protein stock, Lucía Fernández, 500 USD).
    """
    facts = _context_grounding_facts()
    result = _run_and_save_trace(
        "What is the minimum stock rule for proteins?",
        trace_dir,
        **{
            "services.agent.nodes.retrieve": lambda q: [PROTEIN_STOCK_CHUNK],
            "services.agent.nodes.generate_answer": lambda q, ctx: GROUNDED_ANSWER,
        },
    )

    # Assert against the saved trace (not a re-invoke).
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    _assert_trace_retrieve_before_generate(trace)
    answer = trace["answer"] or ""
    assert facts["stock_rule"] in answer
    assert facts["person"] in answer
    assert facts["threshold"] in answer
    retrieve_step = next(s for s in trace["steps"] if s["node_name"] == "retrieve")
    assert facts["source_document"] in retrieve_step["output"]["sources"]

    artifact = Path("data/process/agent-traces")
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact / "sample-grounding-eval.json").write_text(
        json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def test_eval_grounding_from_saved_trace_artifact():
    """Eval against an already-saved trace file (no live graph execution)."""
    facts = _context_grounding_facts()
    sample = REPO_ROOT / "data" / "process" / "agent-traces" / "sample-grounding-eval.json"
    assert sample.is_file(), "sample grounding trace artifact must exist"
    trace = json.loads(sample.read_text(encoding="utf-8"))
    _assert_trace_retrieve_before_generate(trace)
    answer = trace.get("answer") or ""
    assert facts["stock_rule"] in answer
    assert facts["person"] in answer or "Lucia Fernandez" in answer
    retrieve_step = next(s for s in trace["steps"] if s["node_name"] == "retrieve")
    assert facts["source_document"] in (retrieve_step["output"].get("sources") or [])


def test_generate_answer_is_separate_from_retrieve():
    """Contract: generate_answer must not call retrieve (node separation)."""
    from data.pipelines.rag import generate_answer

    with patch("data.pipelines.rag.retrieve") as mock_retrieve, patch(
        "data.pipelines.rag.client"
    ) as mock_client:
        mock_client.chat.completions.create.return_value.choices = [
            type("C", (), {"message": type("M", (), {"content": "ok"})()})()
        ]
        answer = generate_answer("Q?", [PROTEIN_STOCK_CHUNK])

    mock_retrieve.assert_not_called()
    assert answer == "ok"


def test_node_contract_graph_never_calls_monolithic_query():
    """Node contract: retrieve node → retrieve(); generate node → generate_answer(q, ctx).

    The monolithic ``query()`` (retrieve + generate) must not run inside any node.
    """
    import services.agent.nodes as nodes_mod

    assert not hasattr(nodes_mod, "query"), "nodes must not import monolithic query()"

    with patch("services.agent.nodes.retrieve", return_value=[PROTEIN_STOCK_CHUNK]) as mock_retrieve, patch(
        "services.agent.nodes.generate_answer", return_value=GROUNDED_ANSWER
    ) as mock_generate, patch("data.pipelines.rag.query") as mock_query, patch(
        "services.agent.graph._COMPILED_GRAPH", compile_agent_graph()
    ), patch("services.agent.graph.save_trace"):
        result = run_agent("What is the minimum stock rule for proteins?")

    mock_query.assert_not_called()
    mock_retrieve.assert_called_once_with("What is the minimum stock rule for proteins?")
    mock_generate.assert_called_once()
    question_arg, context_arg = mock_generate.call_args.args[:2]
    assert question_arg == "What is the minimum stock rule for proteins?"
    assert context_arg == [PROTEIN_STOCK_CHUNK]
    assert result["node_order"] == [
        "receive_question",
        "decide_route",
        "recall_memory",
        "retrieve",
        "generate",
        "write_memory",
    ]


def test_query_skips_retrieve_when_chunks_provided():
    """If query() is reused with already-retrieved chunks, it must not re-retrieve."""
    from data.pipelines.rag import query

    with patch("data.pipelines.rag.retrieve") as mock_retrieve, patch(
        "data.pipelines.rag.generate_answer", return_value=GROUNDED_ANSWER
    ) as mock_generate:
        answer = query(
            "What is the minimum stock rule for proteins?",
            chunks=[PROTEIN_STOCK_CHUNK],
        )

    mock_retrieve.assert_not_called()
    mock_generate.assert_called_once_with(
        "What is the minimum stock rule for proteins?",
        [PROTEIN_STOCK_CHUNK],
    )
    assert answer == GROUNDED_ANSWER


def test_checkpointing_persists_thread_state():
    """Verifiable checkpointing: the same thread_id can be inspected after a run."""
    from services.agent.graph import inspect_checkpoints

    graph = compile_agent_graph()
    thread_id = "checkpoint-eval-thread"
    with patch("services.agent.nodes.retrieve", return_value=[PROTEIN_STOCK_CHUNK]), patch(
        "services.agent.nodes.generate_answer", return_value=GROUNDED_ANSWER
    ):
        graph.invoke(
            {
                "question": "What is the minimum stock rule for proteins?",
                "retrieved": [],
                "answer": None,
                "error": None,
                "route": "",
                "steps": [],
            },
            config={"configurable": {"thread_id": thread_id}},
        )

    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    assert snapshot is not None
    assert snapshot.values.get("answer") == GROUNDED_ANSWER
    assert len(snapshot.values.get("retrieved") or []) == 1

    # Checkpointing at every meaningful transition → multiple history entries.
    history = inspect_checkpoints(thread_id, graph=graph)
    assert len(history) >= 3  # receive → retrieve → generate (at least)
    assert history[-1]["answer"] == GROUNDED_ANSWER
    assert "retrieve" in history[-1]["node_order"]
    assert "generate" in history[-1]["node_order"]


def test_every_run_produces_queryable_trace(trace_dir: Path):
    """Tracing: each run persists node order + outputs loadable after the fact."""
    from services.agent.tracing import query_traces

    with patch("services.agent.nodes.retrieve", return_value=[PROTEIN_STOCK_CHUNK]), patch(
        "services.agent.nodes.generate_answer", return_value=GROUNDED_ANSWER
    ), patch("services.agent.tracing.DEFAULT_TRACE_DIR", trace_dir), patch(
        "services.agent.graph.save_trace"
    ) as mock_save:
        from services.agent.tracing import save_trace as real_save

        mock_save.side_effect = lambda record, **_: real_save(record, trace_dir=trace_dir)
        with patch("services.agent.graph._COMPILED_GRAPH", compile_agent_graph()):
            result = run_agent("What is the minimum stock rule for proteins?")

    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert trace["trace_id"] == result["trace_id"]
    assert trace["node_order"] == [
        "receive_question",
        "decide_route",
        "recall_memory",
        "retrieve",
        "generate",
        "write_memory",
    ]
    assert len(trace["steps"]) == 6
    assert trace["steps"][0]["node_name"] == "receive_question"
    assert trace["steps"][1]["node_name"] == "decide_route"
    retrieve_step = next(s for s in trace["steps"] if s["node_name"] == "retrieve")
    assert retrieve_step["output"]["chunk_count"] == 1
    generate_step = next(s for s in trace["steps"] if s["node_name"] == "generate")
    assert generate_step["notes"].startswith("grounded answer from retrieved KB context")
    # Trace file is queryable from disk (not just console print).
    assert (trace_dir / f"{result['trace_id']}.json").is_file()

    # Structured query after the run (filter by node / question).
    hits = query_traces(
        node="retrieve",
        question_contains="protein",
        trace_dir=trace_dir,
    )
    assert any(t["trace_id"] == result["trace_id"] for t in hits)
