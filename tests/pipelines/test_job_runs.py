from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from data.pipelines.job_runs import (
    DEFAULT_JOB_NAME,
    FileJobRunStore,
    InMemoryJobRunStore,
    InvalidTransitionError,
    ProcessingLockHeld,
    execute_with_job_tracking,
    validate_transition,
)

ROOT = Path(__file__).resolve().parents[2]


def test_validate_transition_allows_happy_path():
    validate_transition("pending", "processing")
    validate_transition("processing", "completed")


def test_validate_transition_allows_failure_paths():
    validate_transition("pending", "failed")
    validate_transition("processing", "failed")


def test_validate_transition_rejects_illegal_moves():
    with pytest.raises(InvalidTransitionError):
        validate_transition("completed", "failed")
    with pytest.raises(InvalidTransitionError):
        validate_transition("failed", "processing")
    with pytest.raises(InvalidTransitionError):
        validate_transition("pending", "completed")


def test_job_run_records_include_target_date_and_status():
    store = InMemoryJobRunStore()
    job = store.claim_processing(target_date="2026-07-08", job_name="weekly_kpis")
    assert job.status == "processing"
    assert job.target_date == "2026-07-08"
    assert job.job_name == "weekly_kpis"
    assert job.started_at is not None

    job = store.transition(job.id, "completed")
    assert job.status == "completed"
    assert job.finished_at is not None
    assert job.target_date == "2026-07-08"


def test_execute_with_job_tracking_completed_status_matches_execution(tmp_path: Path):
    store = FileJobRunStore(tmp_path / "job_runs.json")
    seen = []

    job = execute_with_job_tracking(
        store=store,
        target_date="2026-07-01",
        execute_fn=lambda: None,
        on_update=seen.append,
    )

    assert job.status == "completed"
    assert job.target_date == "2026-07-01"
    assert [j.status for j in seen] == ["processing", "completed"]

    persisted = store.get(job.id)
    assert persisted is not None
    assert persisted.status == "completed"
    assert persisted.target_date == "2026-07-01"


def test_execute_with_job_tracking_failed_status_matches_execution():
    store = InMemoryJobRunStore()

    def boom():
        raise RuntimeError("supabase timeout")

    with pytest.raises(RuntimeError, match="supabase timeout"):
        execute_with_job_tracking(
            store=store,
            target_date="2026-07-01",
            execute_fn=boom,
        )

    jobs = store.list()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.status == "failed"
    assert job.target_date == "2026-07-01"
    assert "supabase timeout" in (job.error_message or "")
    assert job.finished_at is not None
    assert store.find_processing(job.job_name, job.target_date) is None


def test_no_processing_left_after_keyboard_interrupt():
    """finally must mark failed even for BaseException (not only Exception)."""
    store = InMemoryJobRunStore()

    def boom():
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        execute_with_job_tracking(
            store=store,
            target_date="2026-07-01",
            execute_fn=boom,
        )

    jobs = store.list()
    assert len(jobs) == 1
    assert jobs[0].status == "failed"
    assert store.find_processing(jobs[0].job_name, "2026-07-01") is None
    assert "KeyboardInterrupt" in (jobs[0].error_message or "")


def test_completed_path_not_overwritten_by_finally():
    store = InMemoryJobRunStore()
    job = execute_with_job_tracking(
        store=store,
        target_date="2026-07-01",
        execute_fn=lambda: None,
    )
    assert job.status == "completed"
    assert store.get(job.id).status == "completed"
    assert store.find_processing(job.job_name, "2026-07-01") is None


def test_second_claim_blocked_while_processing():
    store = InMemoryJobRunStore()
    first = store.claim_processing(target_date="2026-07-08")
    assert first.status == "processing"

    with pytest.raises(ProcessingLockHeld) as excinfo:
        store.claim_processing(target_date="2026-07-08")
    assert str(excinfo.value.holder.id) == str(first.id)

    store.transition(first.id, "completed")
    # Low-level claim still allows a new attempt after completion (retries / force).
    second = store.claim_processing(target_date="2026-07-08")
    assert second.status == "processing"
    assert str(second.id) != str(first.id)


def test_execute_idempotent_per_target_date_skips_second_run(tmp_path: Path):
    store = FileJobRunStore(tmp_path / "job_runs.json")
    calls = {"n": 0}
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def work():
        calls["n"] += 1
        # Simulate a dated artifact — second run must not create another file.
        (output_dir / ("results-%s.csv" % "2026-07-08")).write_text(
            "day,value\n2026-07-08,%s\n" % calls["n"],
            encoding="utf-8",
        )

    first = execute_with_job_tracking(
        store=store,
        target_date="2026-07-08",
        execute_fn=work,
    )
    second = execute_with_job_tracking(
        store=store,
        target_date="2026-07-08",
        execute_fn=work,
    )

    assert first.status == "completed"
    assert second.status == "completed"
    assert str(first.id) == str(second.id)
    assert calls["n"] == 1
    assert len(store.list()) == 1
    assert list(output_dir.glob("*.csv")) == [output_dir / "results-2026-07-08.csv"]
    assert (output_dir / "results-2026-07-08.csv").read_text(encoding="utf-8") == (
        "day,value\n2026-07-08,1\n"
    )


def test_failed_run_can_be_retried():
    store = InMemoryJobRunStore()
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("transient")

    with pytest.raises(RuntimeError):
        execute_with_job_tracking(store, target_date="2026-07-08", execute_fn=boom)

    def ok():
        calls["n"] += 1

    job = execute_with_job_tracking(store, target_date="2026-07-08", execute_fn=ok)
    assert job.status == "completed"
    assert calls["n"] == 2
    assert len([j for j in store.list() if j.status == "completed"]) == 1


def test_concurrent_threads_only_one_holds_processing():
    store = InMemoryJobRunStore()
    winners = []
    errors = []

    def worker():
        try:
            job = store.claim_processing(target_date="2026-07-08")
            winners.append(job.id)
            time.sleep(0.05)
            store.transition(job.id, "completed")
        except ProcessingLockHeld as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(winners) == 1
    assert len(errors) == 7


def test_lifecycle_logs_include_timestamp_job_name_and_status(caplog):
    store = InMemoryJobRunStore()
    with caplog.at_level("INFO", logger="data.pipelines.job_runs"):
        first = execute_with_job_tracking(
            store, target_date="2026-07-08", execute_fn=lambda: None
        )
        execute_with_job_tracking(
            store, target_date="2026-07-08", execute_fn=lambda: None
        )
        with pytest.raises(ProcessingLockHeld):
            # Force a lock_held event by claiming while another run is processing.
            holder = store.claim_processing(target_date="2026-07-09")
            try:
                execute_with_job_tracking(
                    store, target_date="2026-07-09", execute_fn=lambda: None
                )
            finally:
                store.transition(holder.id, "completed")

        with pytest.raises(RuntimeError):
            execute_with_job_tracking(
                store,
                target_date="2026-07-10",
                execute_fn=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            )

    messages = [record.getMessage() for record in caplog.records]
    assert any("event=processing" in msg and "status=processing" in msg for msg in messages)
    assert any("event=completed" in msg and "status=completed" in msg for msg in messages)
    assert any("event=idempotent_skip" in msg and "status=completed" in msg for msg in messages)
    assert any("event=lock_held" in msg and "status=processing" in msg for msg in messages)
    assert any("event=failed" in msg and "status=failed" in msg for msg in messages)

    for record in caplog.records:
        msg = record.getMessage()
        assert "timestamp=" in msg
        assert "job_name=" in msg
        assert "status=" in msg
        assert DEFAULT_JOB_NAME in msg or "job_name=" in msg

    assert first.status == "completed"


def test_two_processes_processing_is_distributed_lock():
    """Demonstrable proof: two script instances, only one acquires processing."""
    with tempfile.TemporaryDirectory() as tmp:
        store_path = Path(tmp) / "job_runs.json"
        store_path.write_text("[]", encoding="utf-8")
        runner = ROOT / "scripts" / "run_pipeline_job.py"
        common = [
            sys.executable,
            str(runner),
            "--target-date",
            "2026-07-08",
            "--store-path",
            str(store_path),
        ]

        proc_a = subprocess.Popen(
            common + ["--hold-seconds", "2", "--instance-label", "A"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        time.sleep(0.3)
        proc_b = subprocess.Popen(
            common + ["--hold-seconds", "0.1", "--instance-label", "B"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        out_a, _ = proc_a.communicate(timeout=15)
        out_b, _ = proc_b.communicate(timeout=15)

        assert proc_a.returncode == 0, out_a
        assert proc_b.returncode == 2, out_b
        assert "acquired processing lock" in out_a
        assert "LOCKED OUT" in out_b

        rows = json.loads(store_path.read_text())
        processing_or_done = [r for r in rows if r["status"] in {"processing", "completed"}]
        assert len([r for r in rows if r["status"] == "completed"]) == 1
        assert all(r["target_date"] == "2026-07-08" for r in processing_or_done)
