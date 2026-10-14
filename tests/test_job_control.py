"""Job control table client and nightly export scheduling rules."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_nightly():
    path = REPO_ROOT / "scripts" / "nightly_export.py"
    spec = importlib.util.spec_from_file_location("brasaland_nightly_export", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


nightly = _load_nightly()


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store: list[dict]):
        self.store = store
        self.op = None
        self.payload = None
        self.filters: dict = {}

    def insert(self, payload):
        self.op = "insert"
        self.payload = dict(payload)
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = dict(payload)
        return self

    def select(self, _columns):
        self.op = "select"
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def order(self, _key, desc=False):
        self.filters["_desc"] = desc
        return self

    def limit(self, _count):
        return self

    def execute(self):
        if self.op == "insert":
            clash = any(
                row.get("job_name") == self.payload.get("job_name")
                and str(row.get("target_date")) == str(self.payload.get("target_date"))
                and row.get("status") == "processing"
                and self.payload.get("status") == "processing"
                for row in self.store
            )
            if clash:
                error = Exception("duplicate key value violates unique constraint")
                error.code = "23505"
                raise error
            row = {"id": len(self.store) + 1, "error_message": None, **self.payload}
            self.store.append(row)
            return _Response([row])
        if self.op == "update":
            updated = []
            for row in self.store:
                if row.get("id") == self.filters.get("id"):
                    row.update(self.payload)
                    updated.append(dict(row))
            return _Response(updated)
        rows = [
            row
            for row in self.store
            if all(row.get(key) == value for key, value in self.filters.items() if not key.startswith("_"))
        ]
        if self.filters.get("_desc"):
            rows = sorted(rows, key=lambda row: row["id"], reverse=True)
        return _Response(rows[:1] if self.filters.get("_desc") else rows)


class _Client:
    def __init__(self, store: list[dict]):
        self.store = store

    def table(self, name):
        assert name == "job_runs"
        return _Query(self.store)


@pytest.fixture
def store(monkeypatch):
    import services.job_runner as job_runner

    rows: list[dict] = []
    monkeypatch.setattr(job_runner, "_client", lambda: _Client(rows))
    return rows


def test_create_run_claims_processing_with_started_at(store):
    import services.job_runner as job_runner

    run_id = job_runner.create_run("nightly_export", "2026-10-12")
    assert run_id == 1
    assert store[0]["status"] == "processing"
    assert store[0]["job_name"] == "nightly_export"
    assert store[0]["target_date"] == "2026-10-12"
    assert store[0]["started_at"]


def test_second_processing_claim_is_the_lock(store):
    import services.job_runner as job_runner

    job_runner.create_run("nightly_export", "2026-10-12")
    with pytest.raises(job_runner.JobAlreadyRunning):
        job_runner.create_run("nightly_export", "2026-10-12")


def test_complete_and_fail_set_finished_at(store):
    import services.job_runner as job_runner

    run_id = job_runner.create_run("nightly_export", "2026-10-12")
    job_runner.mark_completed(run_id)
    assert store[0]["status"] == "completed"
    assert store[0]["finished_at"]
    assert store[0]["error_message"] is None
    assert job_runner.has_completed_for_date("nightly_export", "2026-10-12") is True
    assert job_runner.has_processing_lock("nightly_export") is False

    failed_id = job_runner.create_run("nightly_export", "2026-10-11")
    job_runner.mark_failed(failed_id, "postgres://user:secret@db.example/brasaland")
    failed = next(row for row in store if row["id"] == failed_id)
    assert failed["status"] == "failed"
    assert failed["finished_at"]
    assert "postgres://" not in (failed["error_message"] or "")
    latest = job_runner.latest_run("nightly_export", "2026-10-11")
    assert latest["status"] == "failed"


def test_target_date_is_env_or_yesterday_utc():
    start, end = nightly.export_bounds("2026-10-12")
    assert nightly.TELEMETRY_TIME_COLUMN == "timestamp"
    assert nightly.TELEMETRY_TABLE == "telemetry_events"
    assert start == "2026-10-12T00:00:00Z"
    assert end == "2026-10-13T00:00:00Z"
    # 03:00 UTC on the 13th is still the evening of the 12th in Bogotá.
    # The contract date is yesterday in UTC, which is the 12th.
    assert nightly.default_target_date(datetime(2026, 10, 13, 3, 0, tzinfo=timezone.utc)) == "2026-10-12"
    assert nightly.resolve_target_date(["nightly_export.py"], {"TARGET_DATE": "2025-01-15"}) == "2025-01-15"
    assert nightly.resolve_target_date(["nightly_export.py", "2026-04-01"], {"TARGET_DATE": "2025-01-15"}) == "2026-04-01"


def test_existing_csv_skips_export_and_still_runs_pipeline(monkeypatch):
    import services.job_runner as job_runner

    csv_path = REPO_ROOT / "data" / "raw" / "telemetry_2099-02-02.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text("id,timestamp\n", encoding="utf-8")
    queried = {"hit": False}

    class _Supabase:
        def table(self, _name):
            queried["hit"] = True
            raise AssertionError("existing CSV must not be re-exported")

    monkeypatch.setattr(job_runner, "has_processing_lock", lambda _name: False)
    monkeypatch.setattr(job_runner, "has_completed_for_date", lambda _name, _date: False)
    monkeypatch.setattr(job_runner, "create_run", lambda _name, _date: 9)
    monkeypatch.setattr(job_runner, "mark_processing", lambda run_id: [{"id": run_id}])
    completed = {}
    monkeypatch.setattr(job_runner, "mark_completed", lambda run_id: completed.setdefault("id", run_id))
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "service-role-test")

    import supabase

    monkeypatch.setattr(supabase, "create_client", lambda _url, _key: _Supabase())
    ran = {}

    def _fake_run(cmd, capture_output, text):
        ran["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(nightly.subprocess, "run", _fake_run)
    monkeypatch.setattr(sys, "argv", ["nightly_export.py"])
    monkeypatch.setenv("TARGET_DATE", "2099-02-02")
    try:
        nightly.main()
    finally:
        csv_path.unlink(missing_ok=True)

    assert queried["hit"] is False
    assert ran["cmd"][-1].endswith("pipeline.py")
    assert completed["id"] == 9


def test_invalid_date_exits_on_stderr(capsys):
    sys.argv = ["nightly_export.py", "18-09-2026"]
    with pytest.raises(SystemExit) as exc:
        nightly.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "YYYY-MM-DD" in captured.err
    assert "YYYY-MM-DD" not in captured.out


def test_processing_lock_exits_without_export(monkeypatch):
    import services.job_runner as job_runner

    monkeypatch.setattr(job_runner, "has_processing_lock", lambda _name: True)
    monkeypatch.setattr(sys, "argv", ["nightly_export.py", "2026-10-12"])
    with pytest.raises(SystemExit) as exc:
        nightly.main()
    assert exc.value.code == 0


def test_export_filters_timestamp_then_marks_completed(monkeypatch, tmp_path):
    import services.job_runner as job_runner

    calls = []

    class _Table:
        def select(self, *_args):
            calls.append("select")
            return self

        def in_(self, column, values):
            calls.append(("in", column, tuple(values)))
            return self

        def gte(self, column, value):
            calls.append(("gte", column, value))
            return self

        def lt(self, column, value):
            calls.append(("lt", column, value))
            return self

        def execute(self):
            return SimpleNamespace(
                data=[
                    {
                        "id": "evt-1",
                        "timestamp": "2026-10-12T15:00:00Z",
                        "event_type": "stock_waste_registered",
                        "tags": {"location_id": "co-med-centro", "currency": "COP"},
                    }
                ]
            )

    class _Supabase:
        def table(self, name):
            calls.append(("table", name))
            return _Table()

    monkeypatch.setattr(job_runner, "has_processing_lock", lambda _name: False)
    monkeypatch.setattr(job_runner, "has_completed_for_date", lambda _name, _date: False)
    monkeypatch.setattr(job_runner, "create_run", lambda _name, _date: 7)
    monkeypatch.setattr(job_runner, "mark_processing", lambda run_id: [{"id": run_id}])
    completed = {}
    monkeypatch.setattr(job_runner, "mark_completed", lambda run_id: completed.setdefault("id", run_id))
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "service-role-test")

    import supabase

    monkeypatch.setattr(supabase, "create_client", lambda _url, _key: _Supabase())

    csv_path = REPO_ROOT / "data" / "raw" / "telemetry_2099-01-15.csv"
    if csv_path.exists():
        csv_path.unlink()

    def _fake_run(cmd, capture_output, text):
        assert cmd[-1].endswith("pipeline.py")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(nightly.subprocess, "run", _fake_run)
    monkeypatch.setattr(sys, "argv", ["nightly_export.py", "2099-01-15"])
    try:
        nightly.main()
    finally:
        if csv_path.exists():
            csv_path.unlink()

    assert ("table", "telemetry_events") in calls
    assert ("gte", "timestamp", "2099-01-15T00:00:00Z") in calls
    assert ("lt", "timestamp", "2099-01-16T00:00:00Z") in calls
    assert completed["id"] == 7
    assert "created_at" not in {item[1] for item in calls if isinstance(item, tuple) and item[0] in {"gte", "lt"}}
