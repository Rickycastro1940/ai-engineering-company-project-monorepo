"""Part 3 checkpointer: SQLite file or Postgres — not in-memory by default."""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_approval.checkpointer import (
    checkpoint_backend,
    checkpointer_kind,
    get_approval_checkpointer,
    postgres_conninfo,
    reset_approval_checkpointer,
    sqlite_checkpoint_path,
)
from data.pipelines.rfp_approval.graph import invoke_rfp_approval_graph
from data.pipelines.rfp_intake.constants import STATUS_WAITING_FOR_APPROVAL

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "checkpoints.sqlite"))
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()


def test_default_backend_is_sqlite_file_not_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'tickets.sqlite'}")
    monkeypatch.delenv("RFP_CHECKPOINT_SQLITE", raising=False)
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    assert checkpoint_backend() == "sqlite"
    path = sqlite_checkpoint_path()
    assert path.name.endswith(".sqlite")
    assert ":memory:" not in str(path)
    saver = get_approval_checkpointer()
    assert checkpointer_kind(saver) == "sqlite"
    assert type(saver).__name__ == "SqliteSaver"


def test_postgres_url_selects_postgres_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:pass@db.example.supabase.co:5432/postgres",
    )
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    assert checkpoint_backend() == "postgres"
    assert (
        postgres_conninfo(
            "postgresql+psycopg://user:pass@db.example.supabase.co:5432/postgres"
        )
        == "postgresql://user:pass@db.example.supabase.co:5432/postgres"
    )


def test_memory_saver_is_opt_in_local_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_MEMORY", "1")
    reset_approval_checkpointer()
    assert checkpoint_backend() == "memory"
    saver = get_approval_checkpointer()
    assert checkpointer_kind(saver) == "memory"
    assert type(saver).__name__ == "MemorySaver"


def test_graph_module_does_not_hardcode_memory_saver() -> None:
    src = (REPO / "data" / "pipelines" / "rfp_approval" / "graph.py").read_text(
        encoding="utf-8"
    )
    assert "from langgraph.checkpoint.memory import MemorySaver" not in src
    assert "checkpointer=MemorySaver" not in src
    assert "get_approval_checkpointer" in src


def test_compiled_graph_uses_sqlite_checkpointer_by_default() -> None:
    from data.pipelines.rfp_approval.graph import get_compiled_rfp_approval_graph

    graph = get_compiled_rfp_approval_graph(use_interrupt=True)
    saver = get_approval_checkpointer()
    assert checkpointer_kind(saver) == "sqlite"
    assert graph is not None


def test_interrupt_resume_works_with_sqlite_file_checkpointer() -> None:
    kwargs = dict(
        ticket_id="hitl-sqlite-checkpointer",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=[
            {
                "department_id": "marketing",
                "draft_content": "## Brand terms\nOffer validity period: 30 days.\n",
            }
        ],
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id="hitl-sqlite-thread",
    )
    paused = invoke_rfp_approval_graph(**kwargs)
    interrupts = paused.get("__interrupt__") or []
    assert interrupts, f"expected interrupt payload, got keys={list(paused)}"

    resumed = invoke_rfp_approval_graph(
        **kwargs,
        resume={
            "department_id": "marketing",
            "decision": "approved",
            "approver": "Camila Ospina",
        },
    )
    assert resumed.get("status") == "done"
    assert (resumed.get("final_document") or {}).get("ticket_id") == (
        "hitl-sqlite-checkpointer"
    )
    path = sqlite_checkpoint_path()
    assert path.is_file()
    assert path.stat().st_size > 0
