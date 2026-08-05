"""LangGraph support-agent evals (Part 1).

Evals assert against the *trace* produced by a run (node order, routing, answer
grounding metadata). LLM / Qdrant calls are mocked so the suite is runnable
offline with a single command:

    uv run pytest tests/pipelines/test_agent_graph.py -q
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

# Known fact from docs/company-knowledge-base/brasaland-supplier-ordering.en.md
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


@pytest.fixture()
def trace_dir(tmp_path: Path) -> Path:
    return tmp_path / "traces"


@pytest.fixture()
def compiled_graph():
    """Fresh compiled graph per test (isolates MemorySaver state)."""
    return compile_agent_graph()


def _run_with_trace_dir(question: str, trace_dir: Path, **patches):
    with patch("services.agent.tracing.DEFAULT_TRACE_DIR", trace_dir):
        # Re-bind save_trace's default by patching the module attribute used at call time.
        with patch("services.agent.graph.save_trace") as mock_save:
            from services.agent.tracing import TraceRecord, save_trace as real_save

            def _save(record: TraceRecord, *, trace_dir_arg=None):
                return real_save(record, trace_dir=trace_dir)

            mock_save.side_effect = _save
            # Apply node-level patches if provided
            patchers = []
            for target, value in patches.items():
                p = patch(target, value)
                patchers.append(p)
                p.start()
            try:
                result = run_agent(question)
            finally:
                for p in patchers:
                    p.stop()
            return result


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
    """Eval 1 — for a grounded question, retrieve must run before generate."""
    with patch("services.agent.nodes.retrieve", return_value=[PROTEIN_STOCK_CHUNK]), patch(
        "services.agent.nodes.generate_answer", return_value=GROUNDED_ANSWER
    ), patch("services.agent.tracing.DEFAULT_TRACE_DIR", trace_dir), patch(
        "services.agent.graph.save_trace"
    ) as mock_save:
        from services.agent.tracing import save_trace as real_save

        mock_save.side_effect = lambda record, **_: real_save(record, trace_dir=trace_dir)
        # Force a fresh compiled graph so MemorySaver is clean
        with patch("services.agent.graph._COMPILED_GRAPH", compile_agent_graph()):
            result = run_agent("What is the minimum stock rule for proteins?")

    assert result["status"] == "ok"
    assert result["node_order"] == ["receive_question", "retrieve", "generate"]
    # retrieve index < generate index
    assert result["node_order"].index("retrieve") < result["node_order"].index("generate")

    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert trace["node_order"] == result["node_order"]
    assert trace["steps"][1]["node_name"] == "retrieve"
    assert trace["steps"][2]["node_name"] == "generate"
    assert trace["steps"][1]["output"]["chunk_count"] == 1


def test_eval_empty_question_skips_retrieve(trace_dir: Path):
    """Eval 2 — empty question routes to empty_question and never retrieves."""
    with patch("services.agent.nodes.retrieve") as mock_retrieve, patch(
        "services.agent.tracing.DEFAULT_TRACE_DIR", trace_dir
    ), patch("services.agent.graph.save_trace") as mock_save:
        from services.agent.tracing import save_trace as real_save

        mock_save.side_effect = lambda record, **_: real_save(record, trace_dir=trace_dir)
        with patch("services.agent.graph._COMPILED_GRAPH", compile_agent_graph()):
            result = run_agent("   ")

    mock_retrieve.assert_not_called()
    assert result["status"] == "error"
    assert result["node_order"] == ["receive_question", "empty_question"]
    assert "retrieve" not in result["node_order"]
    assert "generate" not in result["node_order"]

    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert trace["error"] == "empty_question"
    assert trace["node_order"] == ["receive_question", "empty_question"]


def test_eval_no_context_when_retrieve_empty(trace_dir: Path):
    """Eval 3 — when retrieve returns nothing above threshold, use no_context."""
    with patch("services.agent.nodes.retrieve", return_value=[]), patch(
        "services.agent.nodes.generate_answer"
    ) as mock_generate, patch("services.agent.tracing.DEFAULT_TRACE_DIR", trace_dir), patch(
        "services.agent.graph.save_trace"
    ) as mock_save:
        from services.agent.tracing import save_trace as real_save

        mock_save.side_effect = lambda record, **_: real_save(record, trace_dir=trace_dir)
        with patch("services.agent.graph._COMPILED_GRAPH", compile_agent_graph()):
            result = run_agent("What is Brasaland's secret sauce recipe?")

    mock_generate.assert_not_called()
    assert result["status"] == "ok"
    assert result["answer"] == NO_CONTEXT_ANSWER
    assert result["node_order"] == ["receive_question", "retrieve", "no_context"]
    assert "generate" not in result["node_order"]

    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert trace["answer"] == NO_CONTEXT_ANSWER
    assert trace["steps"][1]["output"]["chunk_count"] == 0


def test_eval_answer_grounded_in_context_knowledge_base(trace_dir: Path):
    """Eval 4 (grounding) — known supplier-ordering fact appears in the answer.

    Uses a real KB chunk from CONTEXT / company-knowledge-base and asserts the
    agent answer cites the expected entities (3 days protein stock, Lucía Fernández).
    Trace/routing correctness alone is not enough — grounding is an acceptance gate.
    """
    with patch("services.agent.nodes.retrieve", return_value=[PROTEIN_STOCK_CHUNK]), patch(
        "services.agent.nodes.generate_answer", return_value=GROUNDED_ANSWER
    ) as mock_generate, patch("services.agent.tracing.DEFAULT_TRACE_DIR", trace_dir), patch(
        "services.agent.graph.save_trace"
    ) as mock_save:
        from services.agent.tracing import save_trace as real_save

        mock_save.side_effect = lambda record, **_: real_save(record, trace_dir=trace_dir)
        with patch("services.agent.graph._COMPILED_GRAPH", compile_agent_graph()):
            result = run_agent("What is the minimum stock rule for proteins?")

    # Generation received the retrieved KB chunk (not a re-wrapped monolithic query).
    mock_generate.assert_called_once()
    call_args = mock_generate.call_args
    assert call_args.args[0] == "What is the minimum stock rule for proteins?"
    context_arg = call_args.args[1]
    assert isinstance(context_arg, list)
    assert context_arg[0]["source_document"] == "supplier-ordering"
    assert "3 days" in context_arg[0]["text"]

    assert result["status"] == "ok"
    assert "3 days" in (result["answer"] or "")
    assert "Lucía Fernández" in (result["answer"] or "") or "Lucia Fernandez" in (
        result["answer"] or ""
    )

    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert "3 days" in (trace["answer"] or "")
    assert "supplier-ordering" in trace["steps"][1]["output"]["sources"]
    # Persist a sample trace artifact for the PR
    artifact = Path("data/process/agent-traces")
    artifact.mkdir(parents=True, exist_ok=True)
    sample = artifact / "sample-grounding-eval.json"
    sample.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")


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
    assert result["node_order"] == ["receive_question", "retrieve", "generate"]


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
