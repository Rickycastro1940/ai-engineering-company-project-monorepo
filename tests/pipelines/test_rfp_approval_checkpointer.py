"""Part 3 checkpointer: SQLite file or Postgres — not in-memory by default."""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_approval.checkpointer import (
    approval_thread_id,
    checkpoint_backend,
    checkpointer_kind,
    ensure_rfp_thread_id,
    ephemeral_rfp_thread_id,
    get_approval_checkpointer,
    postgres_conninfo,
    reset_approval_checkpointer,
    rfp_checkpoint_thread_id,
    sqlite_checkpoint_path,
)
from data.pipelines.rfp_approval.graph import (
    get_compiled_rfp_approval_graph,
    invoke_rfp_approval_graph,
)
from data.pipelines.rfp_intake.constants import STATUS_WAITING_FOR_APPROVAL

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "checkpoints.sqlite"))
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()


def test_thread_id_is_namespaced_by_ticket_and_optional_department() -> None:
    assert approval_thread_id("abc123") == "RFP-abc123"
    assert rfp_checkpoint_thread_id("abc123") == "RFP-abc123"
    assert rfp_checkpoint_thread_id("abc123", department_id="marketing") == (
        "RFP-abc123:marketing"
    )
    assert approval_thread_id("abc123", department_id="operaciones") == (
        "RFP-abc123:operaciones"
    )
    # Already-prefixed ticket_id does not double-prefix.
    assert approval_thread_id("RFP-abc123") == "RFP-abc123"
    ephemeral = ephemeral_rfp_thread_id("abc123")
    assert ephemeral.startswith("RFP-abc123:run-")
    assert ensure_rfp_thread_id(None, "abc123") == "RFP-abc123"
    assert ensure_rfp_thread_id("hitl-sqlite-thread", "abc123") == (
        "RFP-abc123:hitl-sqlite-thread"
    )
    assert ensure_rfp_thread_id("RFP-abc123", "abc123") == "RFP-abc123"
    assert ensure_rfp_thread_id("RFP-other:x", "abc123").startswith("RFP-abc123:")


def test_concurrent_tickets_do_not_share_checkpoint_identity() -> None:
    """Two tickets pause independently; approving one must not clear the other."""
    sections = [
        {
            "department_id": "marketing",
            "draft_content": "## Brand terms\nOffer validity period: 30 days.\n",
        }
    ]
    a = "ticket-concurrent-a"
    b = "ticket-concurrent-b"
    assert approval_thread_id(a) != approval_thread_id(b)
    assert approval_thread_id(a) == "RFP-ticket-concurrent-a"
    assert approval_thread_id(b) == "RFP-ticket-concurrent-b"

    kwargs_a = dict(
        ticket_id=a,
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=sections,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id=approval_thread_id(a),
    )
    kwargs_b = dict(
        ticket_id=b,
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=sections,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id=approval_thread_id(b),
    )
    paused_a = invoke_rfp_approval_graph(**kwargs_a)
    paused_b = invoke_rfp_approval_graph(**kwargs_b)
    assert paused_a.get("__interrupt__")
    assert paused_b.get("__interrupt__")

    done_a = invoke_rfp_approval_graph(
        **kwargs_a,
        resume={
            "department_id": "marketing",
            "decision": "approved",
            "approver": "Camila Ospina",
        },
    )
    assert done_a.get("status") == "done"

    graph = get_compiled_rfp_approval_graph()
    still_b = graph.get_state(
        {"configurable": {"thread_id": approval_thread_id(b)}}
    )
    assert still_b.interrupts or still_b.next, (
        "ticket B checkpoint must remain paused after ticket A completes"
    )
    done_b = invoke_rfp_approval_graph(
        **kwargs_b,
        resume={
            "department_id": "marketing",
            "decision": "approved",
            "approver": "Camila Ospina",
        },
    )
    assert done_b.get("status") == "done"
    assert done_a.get("final_document", {}).get("ticket_id") == a
    assert done_b.get("final_document", {}).get("ticket_id") == b


def test_department_scoped_threads_and_concurrent_runs_do_not_collide(
    tmp_path: Path,
) -> None:
    """``RFP-{ticket}`` and ``RFP-{ticket}:{department}`` are distinct; runs stay isolated."""
    import json

    ticket = "ns-ticket-1"
    other = "ns-ticket-2"
    tid_ticket = approval_thread_id(ticket)
    tid_mkt = approval_thread_id(ticket, department_id="marketing")
    tid_ops = approval_thread_id(ticket, department_id="operaciones")
    tid_other = approval_thread_id(other)

    assert tid_ticket == "RFP-ns-ticket-1"
    assert tid_mkt == "RFP-ns-ticket-1:marketing"
    assert tid_ops == "RFP-ns-ticket-1:operaciones"
    assert tid_other == "RFP-ns-ticket-2"
    assert len({tid_ticket, tid_mkt, tid_ops, tid_other}) == 4
    assert tid_mkt.startswith(tid_ticket + ":")
    assert tid_ops.startswith(tid_ticket + ":")
    assert not tid_other.startswith(tid_ticket)

    # Foreign / ephemeral overrides are nested under the ticket namespace.
    assert ensure_rfp_thread_id("custom-run", ticket) == "RFP-ns-ticket-1:custom-run"
    assert ensure_rfp_thread_id("RFP-ns-ticket-2:x", ticket).startswith(
        "RFP-ns-ticket-1:"
    )
    eph_a = ephemeral_rfp_thread_id(ticket)
    eph_b = ephemeral_rfp_thread_id(ticket)
    assert eph_a != eph_b
    assert eph_a.startswith("RFP-ns-ticket-1:run-")
    assert eph_b.startswith("RFP-ns-ticket-1:run-")

    sections = [
        {
            "department_id": "marketing",
            "draft_content": "## Brand terms\nOffer validity period: 30 days.\n",
        }
    ]
    # Concurrent department-scoped branches on the *same* ticket id namespace
    # must not share one undifferentiated checkpoint key.
    paused_mkt = invoke_rfp_approval_graph(
        ticket_id=ticket,
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=sections,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id=tid_mkt,
    )
    paused_ops = invoke_rfp_approval_graph(
        ticket_id=ticket,
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=[
            {
                "department_id": "operaciones",
                "draft_content": "## Setup times\nSetup in 12 business days.\n",
            }
        ],
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["operaciones"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id=tid_ops,
    )
    assert paused_mkt.get("__interrupt__")
    assert paused_ops.get("__interrupt__")

    done_mkt = invoke_rfp_approval_graph(
        ticket_id=ticket,
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=sections,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id=tid_mkt,
        resume={
            "department_id": "marketing",
            "decision": "approved",
            "approver": "Camila Ospina",
        },
    )
    assert done_mkt.get("status") == "done"

    graph = get_compiled_rfp_approval_graph()
    ops_state = graph.get_state({"configurable": {"thread_id": tid_ops}})
    assert ops_state.interrupts or ops_state.next, (
        "operaciones department thread must stay paused after marketing thread completes"
    )

    artifact = Path("/opt/cursor/artifacts/rfp_thread_id_namespace.json")
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {
                "claim": (
                    "thread_id is namespaced by ticket (and department if applicable); "
                    "concurrent runs do not share checkpoints"
                ),
                "ids": {
                    "ticket": tid_ticket,
                    "marketing": tid_mkt,
                    "operaciones": tid_ops,
                    "other_ticket": tid_other,
                    "ephemeral_a": eph_a,
                    "ephemeral_b": eph_b,
                },
                "after_marketing_done": {
                    "marketing_status": done_mkt.get("status"),
                    "operaciones_thread_still_paused": bool(
                        ops_state.interrupts or ops_state.next
                    ),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

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
    assert type(saver).__name__ in {"MemorySaver", "InMemorySaver"}


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
