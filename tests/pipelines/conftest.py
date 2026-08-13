"""Pipeline test configuration for LangGraph / RAG / tool evals."""

from __future__ import annotations

import pytest

collect_ignore = [
    # Prefects/Supabase telemetry pipeline — unrelated to LangGraph agent evals;
    # requires optional deps not installed in the agent eval environment.
    "test_pipeline.py",
]


@pytest.fixture(autouse=True)
def _reset_agent_singletons() -> None:
    """Do not leak pending memory / guardrail audit across tests."""
    import services.agent.harness.audit as guardrail_audit
    import services.agent.memory.audit as memory_audit
    import services.agent.memory.interface as memory_interface
    import services.agent.memory.pending as pending_mod

    def _reset() -> None:
        pending_mod._PENDING = None
        memory_interface._MEMORY = None
        memory_audit._AUDIT = None
        guardrail_audit._AUDIT = None
        if pending_mod.DEFAULT_PENDING_PATH.is_file():
            pending_mod.DEFAULT_PENDING_PATH.unlink()

    _reset()
    yield
    _reset()

