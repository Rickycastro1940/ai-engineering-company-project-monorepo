"""Grounding acceptance-gate evals for the LangGraph agent.

Migrating to LangGraph is not an excuse for answers to stop being grounded in
Brasaland's knowledge base (CONTEXT-company.md + docs/company-knowledge-base/).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.agent.graph import compile_agent_graph, run_agent
from services.agent.grounding import (
    ALLOWED_SOURCE_DOCUMENTS,
    assert_allergen_answer_follows_context_policy,
    assert_answer_grounded_in_supplier_policy,
    assert_sources_from_company_kb,
    assert_trace_grounded,
    supplier_ordering_facts,
)
from services.agent.tracing import load_trace

REPO_ROOT = Path(__file__).resolve().parents[2]

PROTEIN_STOCK_CHUNK = {
    "source_document": "supplier-ordering",
    "section": "Minimum stock rule",
    "text": (
        "Minimum stock rule: no location should operate with less than 3 days of "
        "main protein inventory. An emergency order requires approval from "
        "Lucía Fernández (Procurement Manager) if it exceeds 500 USD. "
        "Emergency orders carry an 8% surcharge over list price."
    ),
    "_score": 0.91,
}
GROUNDED_ANSWER = (
    "Every Brasaland location must keep at least 3 days of main protein inventory. "
    "Emergency orders over 500 USD need approval from Lucía Fernández."
)
UNGROUNDED_ANSWER = (
    "Brasaland locations should always keep two weeks of frozen protein and can "
    "approve emergency orders without Lucía Fernández."
)


@pytest.fixture()
def trace_dir(tmp_path: Path) -> Path:
    return tmp_path / "traces"


def _run(question: str, trace_dir: Path, *, chunks, answer: str) -> dict:
    with patch("services.agent.nodes.retrieve", return_value=chunks), patch(
        "services.agent.nodes.generate_answer", return_value=answer
    ), patch("services.agent.tracing.DEFAULT_TRACE_DIR", trace_dir), patch(
        "services.agent.graph.save_trace"
    ) as mock_save:
        from services.agent.tracing import save_trace as real_save

        mock_save.side_effect = lambda record, **_: real_save(record, trace_dir=trace_dir)
        with patch("services.agent.graph._COMPILED_GRAPH", compile_agent_graph()):
            return run_agent(question)


def test_grounding_facts_exist_in_context_company_and_kb():
    facts = supplier_ordering_facts()
    assert facts["source_document"] in ALLOWED_SOURCE_DOCUMENTS
    assert facts["stock_rule"] == "3 days"
    assert facts["person"] == "Lucía Fernández"


def test_agent_and_rag_share_generate_answer_function():
    """LangGraph generate node must reuse the RAG pipeline's generate_answer."""
    import data.pipelines.rag as rag
    import services.agent.nodes as nodes

    assert nodes.generate_answer is rag.generate_answer
    assert nodes.retrieve is rag.retrieve


def test_grounded_trace_passes_acceptance_gate(trace_dir: Path):
    result = _run(
        "What is the minimum stock rule for proteins?",
        trace_dir,
        chunks=[PROTEIN_STOCK_CHUNK],
        answer=GROUNDED_ANSWER,
    )
    trace = load_trace(result["trace_id"], trace_dir=trace_dir)
    assert_trace_grounded(trace)
    assert_sources_from_company_kb(trace["steps"][1]["output"]["sources"])
    assert_answer_grounded_in_supplier_policy(trace["answer"])


def test_ungrounded_answer_fails_even_with_perfect_trace():
    """Acceptance gate: perfect node order is not enough if answer ignores CONTEXT."""
    perfect_looking_trace = {
        "node_order": ["receive_question", "retrieve", "generate"],
        "answer": UNGROUNDED_ANSWER,
        "steps": [
            {"node_name": "receive_question", "output": {}},
            {
                "node_name": "retrieve",
                "output": {"sources": ["supplier-ordering"], "chunk_count": 1},
            },
            {"node_name": "generate", "output": {"grounded": True}},
        ],
    }
    with pytest.raises(AssertionError, match="not grounded"):
        assert_trace_grounded(perfect_looking_trace)


def test_allergen_policy_forbids_zero_risk_claims():
    # Refusing to guarantee safety is OK (matches KB wording).
    assert_allergen_answer_follows_context_policy(
        "Classic Grilled Chicken is gluten-free; we never guarantee zero cross-contamination."
    )
    with pytest.raises(AssertionError, match="allergen policy"):
        assert_allergen_answer_follows_context_policy(
            "Don't worry — there is zero risk of cross-contamination."
        )


def test_foreign_source_document_fails_grounding_gate():
    with pytest.raises(AssertionError, match="not in the Brasaland knowledge base"):
        assert_sources_from_company_kb(["wikipedia-protein"])


def test_sample_grounding_artifact_remains_grounded():
    sample = REPO_ROOT / "data" / "process" / "agent-traces" / "sample-grounding-eval.json"
    trace = json.loads(sample.read_text(encoding="utf-8"))
    assert_trace_grounded(trace)
