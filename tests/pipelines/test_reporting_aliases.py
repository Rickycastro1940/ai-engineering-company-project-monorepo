"""Verify pipeline-runs HTTP surface is an alias over job_runs (no parallel store)."""
from __future__ import annotations

from data.pipelines.job_runs import (
    DEFAULT_JOB_NAME,
    InMemoryJobRunStore,
    execute_with_job_tracking,
    reset_job_run_store,
)


def test_pipeline_jobs_filter_by_job_name_only():
    reset_job_run_store()
    store = InMemoryJobRunStore()

    execute_with_job_tracking(
        store,
        target_date="2026-07-08",
        job_name=DEFAULT_JOB_NAME,
        execute_fn=lambda: None,
    )
    execute_with_job_tracking(
        store,
        target_date="2026-07-08",
        job_name="other_job",
        execute_fn=lambda: None,
    )

    pipeline_only = [j for j in store.list() if j.job_name == DEFAULT_JOB_NAME]
    assert len(pipeline_only) == 1
    assert pipeline_only[0].status == "completed"
    assert len(store.list()) == 2


def test_no_last_run_json_dependency_in_reporting_module():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "services" / "reporting" / "main.py"
    ).read_text(encoding="utf-8")
    assert "open(" not in source or "last_run" not in source
    assert "last_run" not in source
    assert '"source": "job_runs"' in source
    assert "get_job_run_store" in source
    assert "thin HTTP alias" in source
