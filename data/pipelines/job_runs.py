"""Job run state machine and persistence for pipeline executions.

Aligned with live Supabase `public.job_runs`:
  pending → processing → completed | failed

`processing` is the distributed lock for (job_name, target_date).
There is no separate lock table or mutex — a second instance that sees an
existing `processing` row for the same key must not run.

Idempotency: if a `completed` row already exists for (job_name, target_date),
a later run returns that job and does not re-execute work.
"""
from __future__ import annotations

import fcntl
import json
import logging
import sys
import threading
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Protocol, Set, Union


STATUSES = ("pending", "processing", "completed", "failed")

ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    "pending": {"processing", "failed"},
    "processing": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}

DEFAULT_JOB_NAME = "brasaland_weekly_performance_pipeline"
DEFAULT_STORE_PATH = Path(__file__).resolve().parent / "job_runs.json"
JobId = Union[str, int]

logger = logging.getLogger("data.pipelines.job_runs")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_job_event(
    event: str,
    *,
    job_name: str,
    status: str,
    target_date: Optional[str] = None,
    job_id: Optional[JobId] = None,
    message: Optional[str] = None,
    **extra: Any,
) -> None:
    """Log a lifecycle event with timestamp, job_name, and status on every call."""
    payload: Dict[str, Any] = {
        "timestamp": _utcnow(),
        "event": event,
        "job_name": job_name,
        "status": status,
    }
    if target_date is not None:
        payload["target_date"] = target_date
    if job_id is not None:
        payload["job_id"] = job_id
    if message is not None:
        payload["message"] = message
    payload.update(extra)
    logger.info(
        "timestamp=%s job_name=%s status=%s event=%s%s",
        payload["timestamp"],
        job_name,
        status,
        event,
        "".join(
            " %s=%s" % (key, payload[key])
            for key in ("target_date", "job_id", "message")
            if key in payload and payload[key] is not None
        ),
        extra={"job_event": payload},
    )


class InvalidTransitionError(ValueError):
    """Raised when a status transition is not allowed by the state machine."""


class ProcessingLockHeld(RuntimeError):
    """Raised when another execution already holds status=processing for the key."""

    def __init__(self, holder: "JobRun"):
        self.holder = holder
        super().__init__(
            "processing lock held for job_name=%s target_date=%s by job_id=%s"
            % (holder.job_name, holder.target_date, holder.id)
        )


@dataclass
class JobRun:
    """Mirrors public.job_runs in Supabase."""

    id: JobId
    job_name: str
    target_date: str
    status: str
    error_message: Optional[str] = None
    created_at: str = field(default_factory=_utcnow)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_supabase_row(self) -> Dict[str, Any]:
        """Only columns that exist on the live Supabase table."""
        row = {
            "job_name": self.job_name,
            "target_date": self.target_date,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        if isinstance(self.id, int) or (isinstance(self.id, str) and self.id.isdigit()):
            row["id"] = int(self.id)
        return row

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobRun":
        return cls(
            id=data["id"],
            job_name=data.get("job_name") or DEFAULT_JOB_NAME,
            target_date=str(data["target_date"]),
            status=data["status"],
            error_message=data.get("error_message"),
            created_at=data.get("created_at") or _utcnow(),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
        )


def validate_transition(current: str, new_status: str) -> None:
    if current not in ALLOWED_TRANSITIONS:
        raise InvalidTransitionError("Unknown current status: %s" % current)
    if new_status not in STATUSES:
        raise InvalidTransitionError("Unknown target status: %s" % new_status)
    if new_status not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransitionError(
            "Invalid transition %s → %s" % (current, new_status)
        )


def _apply_transition(job: JobRun, new_status: str, error_message: Optional[str] = None) -> JobRun:
    validate_transition(job.status, new_status)
    now = _utcnow()
    job.status = new_status
    if new_status == "processing":
        job.started_at = now
    if new_status in {"completed", "failed"}:
        job.finished_at = now
    if error_message is not None:
        job.error_message = error_message
    if new_status == "completed":
        job.error_message = None
    return job


class JobRunStore(Protocol):
    def create(
        self,
        target_date: str,
        job_name: str = DEFAULT_JOB_NAME,
        job_id: Optional[JobId] = None,
    ) -> JobRun:
        ...

    def get(self, job_id: JobId) -> Optional[JobRun]:
        ...

    def list(self) -> List[JobRun]:
        ...

    def find_processing(self, job_name: str, target_date: str) -> Optional[JobRun]:
        ...

    def find_completed(self, job_name: str, target_date: str) -> Optional[JobRun]:
        """Latest completed job for the key, if any."""
        ...

    def claim_processing(
        self,
        target_date: str,
        job_name: str = DEFAULT_JOB_NAME,
    ) -> JobRun:
        """Atomically create pending and move to processing, or raise ProcessingLockHeld."""
        ...

    def transition(
        self,
        job_id: JobId,
        new_status: str,
        error_message: Optional[str] = None,
    ) -> JobRun:
        ...


def _pick_latest(jobs: List[JobRun]) -> Optional[JobRun]:
    if not jobs:
        return None
    return sorted(jobs, key=lambda j: j.created_at, reverse=True)[0]


class InMemoryJobRunStore:
    """In-memory store for unit tests (thread-safe claim)."""

    def __init__(self) -> None:
        self._jobs: Dict[str, JobRun] = {}
        self._next_id = 1
        self._lock = threading.Lock()

    def create(
        self,
        target_date: str,
        job_name: str = DEFAULT_JOB_NAME,
        job_id: Optional[JobId] = None,
    ) -> JobRun:
        with self._lock:
            return self._create_unlocked(target_date, job_name, job_id)

    def _create_unlocked(
        self,
        target_date: str,
        job_name: str = DEFAULT_JOB_NAME,
        job_id: Optional[JobId] = None,
    ) -> JobRun:
        now = _utcnow()
        assigned = job_id if job_id is not None else self._next_id
        if job_id is None:
            self._next_id += 1
        job = JobRun(
            id=assigned,
            job_name=job_name,
            target_date=target_date,
            status="pending",
            created_at=now,
        )
        self._jobs[str(job.id)] = job
        return deepcopy(job)

    def get(self, job_id: JobId) -> Optional[JobRun]:
        with self._lock:
            job = self._jobs.get(str(job_id))
            return deepcopy(job) if job else None

    def list(self) -> List[JobRun]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return [deepcopy(j) for j in jobs]

    def find_processing(self, job_name: str, target_date: str) -> Optional[JobRun]:
        with self._lock:
            return self._find_status_unlocked(job_name, target_date, "processing")

    def find_completed(self, job_name: str, target_date: str) -> Optional[JobRun]:
        with self._lock:
            return self._find_status_unlocked(job_name, target_date, "completed")

    def _find_status_unlocked(
        self, job_name: str, target_date: str, status: str
    ) -> Optional[JobRun]:
        matches = [
            deepcopy(job)
            for job in self._jobs.values()
            if (
                job.job_name == job_name
                and job.target_date == target_date
                and job.status == status
            )
        ]
        return _pick_latest(matches)

    def _find_processing_unlocked(self, job_name: str, target_date: str) -> Optional[JobRun]:
        return self._find_status_unlocked(job_name, target_date, "processing")

    def claim_processing(
        self,
        target_date: str,
        job_name: str = DEFAULT_JOB_NAME,
    ) -> JobRun:
        with self._lock:
            holder = self._find_processing_unlocked(job_name, target_date)
            if holder is not None:
                raise ProcessingLockHeld(holder)
            job = self._create_unlocked(target_date, job_name)
            job = _apply_transition(self._jobs[str(job.id)], "processing")
            return deepcopy(job)

    def transition(
        self,
        job_id: JobId,
        new_status: str,
        error_message: Optional[str] = None,
    ) -> JobRun:
        with self._lock:
            job = self._jobs.get(str(job_id))
            if job is None:
                raise KeyError("job_run not found: %s" % job_id)
            if new_status == "processing":
                holder = self._find_processing_unlocked(job.job_name, job.target_date)
                if holder is not None and str(holder.id) != str(job_id):
                    raise ProcessingLockHeld(holder)
            _apply_transition(job, new_status, error_message)
            return deepcopy(job)


class FileJobRunStore:
    """JSON-backed store; flock makes processing claim safe across processes."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else DEFAULT_STORE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        if not self.path.exists():
            self._write([])

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read(self) -> List[Dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return []

    def _write(self, rows: List[Dict[str, Any]]) -> None:
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2)

    def create(
        self,
        target_date: str,
        job_name: str = DEFAULT_JOB_NAME,
        job_id: Optional[JobId] = None,
    ) -> JobRun:
        with self._exclusive():
            return self._create_unlocked(target_date, job_name, job_id)

    def _create_unlocked(
        self,
        target_date: str,
        job_name: str = DEFAULT_JOB_NAME,
        job_id: Optional[JobId] = None,
    ) -> JobRun:
        now = _utcnow()
        job = JobRun(
            id=job_id if job_id is not None else str(uuid.uuid4()),
            job_name=job_name,
            target_date=target_date,
            status="pending",
            created_at=now,
        )
        rows = self._read()
        rows.append(job.to_dict())
        self._write(rows)
        return job

    def get(self, job_id: JobId) -> Optional[JobRun]:
        with self._exclusive():
            for row in self._read():
                if str(row.get("id")) == str(job_id):
                    return JobRun.from_dict(row)
        return None

    def list(self) -> List[JobRun]:
        with self._exclusive():
            jobs = [JobRun.from_dict(row) for row in self._read()]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def find_processing(self, job_name: str, target_date: str) -> Optional[JobRun]:
        with self._exclusive():
            return self._find_status_unlocked(job_name, target_date, "processing")

    def find_completed(self, job_name: str, target_date: str) -> Optional[JobRun]:
        with self._exclusive():
            return self._find_status_unlocked(job_name, target_date, "completed")

    def _find_status_unlocked(
        self, job_name: str, target_date: str, status: str
    ) -> Optional[JobRun]:
        matches = [
            JobRun.from_dict(row)
            for row in self._read()
            if (
                row.get("job_name") == job_name
                and str(row.get("target_date")) == str(target_date)
                and row.get("status") == status
            )
        ]
        return _pick_latest(matches)

    def _find_processing_unlocked(self, job_name: str, target_date: str) -> Optional[JobRun]:
        return self._find_status_unlocked(job_name, target_date, "processing")

    def claim_processing(
        self,
        target_date: str,
        job_name: str = DEFAULT_JOB_NAME,
    ) -> JobRun:
        with self._exclusive():
            holder = self._find_processing_unlocked(job_name, target_date)
            if holder is not None:
                raise ProcessingLockHeld(holder)
            job = self._create_unlocked(target_date, job_name)
            return self._transition_unlocked(job.id, "processing")

    def transition(
        self,
        job_id: JobId,
        new_status: str,
        error_message: Optional[str] = None,
    ) -> JobRun:
        with self._exclusive():
            return self._transition_unlocked(job_id, new_status, error_message)

    def _transition_unlocked(
        self,
        job_id: JobId,
        new_status: str,
        error_message: Optional[str] = None,
    ) -> JobRun:
        rows = self._read()
        for index, row in enumerate(rows):
            if str(row.get("id")) != str(job_id):
                continue
            job = JobRun.from_dict(row)
            if new_status == "processing":
                holder = self._find_processing_unlocked(job.job_name, job.target_date)
                if holder is not None and str(holder.id) != str(job_id):
                    raise ProcessingLockHeld(holder)
            _apply_transition(job, new_status, error_message)
            rows[index] = job.to_dict()
            self._write(rows)
            return job
        raise KeyError("job_run not found: %s" % job_id)


class SupabaseJobRunStore:
    """Persists job_runs to Supabase; processing row is the distributed lock."""

    def __init__(self, client: Any, fallback: Optional[FileJobRunStore] = None) -> None:
        self.client = client
        self.fallback = fallback or FileJobRunStore()

    def create(
        self,
        target_date: str,
        job_name: str = DEFAULT_JOB_NAME,
        job_id: Optional[JobId] = None,
    ) -> JobRun:
        now = _utcnow()
        payload = {
            "job_name": job_name,
            "target_date": target_date,
            "status": "pending",
            "created_at": now,
        }
        try:
            response = self.client.table("job_runs").insert(payload).execute()
            if response.data:
                job = JobRun.from_dict(response.data[0])
                self.fallback.create(
                    target_date=job.target_date,
                    job_name=job.job_name,
                    job_id=job.id,
                )
                return job
        except Exception:
            pass
        return self.fallback.create(
            target_date=target_date,
            job_name=job_name,
            job_id=job_id,
        )

    def get(self, job_id: JobId) -> Optional[JobRun]:
        try:
            response = (
                self.client.table("job_runs").select("*").eq("id", job_id).limit(1).execute()
            )
            if response.data:
                return JobRun.from_dict(response.data[0])
        except Exception:
            pass
        return self.fallback.get(job_id)

    def list(self) -> List[JobRun]:
        try:
            response = (
                self.client.table("job_runs")
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            if response.data is not None:
                return [JobRun.from_dict(row) for row in response.data]
        except Exception:
            pass
        return self.fallback.list()

    def find_processing(self, job_name: str, target_date: str) -> Optional[JobRun]:
        try:
            response = (
                self.client.table("job_runs")
                .select("*")
                .eq("job_name", job_name)
                .eq("target_date", target_date)
                .eq("status", "processing")
                .limit(1)
                .execute()
            )
            if response.data:
                return JobRun.from_dict(response.data[0])
        except Exception:
            pass
        return self.fallback.find_processing(job_name, target_date)

    def find_completed(self, job_name: str, target_date: str) -> Optional[JobRun]:
        try:
            response = (
                self.client.table("job_runs")
                .select("*")
                .eq("job_name", job_name)
                .eq("target_date", target_date)
                .eq("status", "completed")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if response.data:
                return JobRun.from_dict(response.data[0])
        except Exception:
            pass
        return self.fallback.find_completed(job_name, target_date)

    def claim_processing(
        self,
        target_date: str,
        job_name: str = DEFAULT_JOB_NAME,
    ) -> JobRun:
        holder = self.find_processing(job_name, target_date)
        if holder is not None:
            raise ProcessingLockHeld(holder)

        # Atomic claim: insert directly as processing. Unique partial index
        # job_runs_one_processing_per_target enforces the distributed lock.
        now = _utcnow()
        payload = {
            "job_name": job_name,
            "target_date": target_date,
            "status": "processing",
            "created_at": now,
            "started_at": now,
        }
        try:
            response = self.client.table("job_runs").insert(payload).execute()
            if response.data:
                job = JobRun.from_dict(response.data[0])
                try:
                    self.fallback.create(
                        target_date=job.target_date,
                        job_name=job.job_name,
                        job_id=job.id,
                    )
                    self.fallback.transition(job.id, "processing")
                except Exception:
                    pass
                return job
        except Exception as exc:
            # Unique violation or race — treat as lock held.
            holder = self.find_processing(job_name, target_date)
            if holder is not None:
                raise ProcessingLockHeld(holder) from exc
            return self.fallback.claim_processing(target_date, job_name)

        return self.fallback.claim_processing(target_date, job_name)

    def transition(
        self,
        job_id: JobId,
        new_status: str,
        error_message: Optional[str] = None,
    ) -> JobRun:
        current = self.get(job_id)
        if current is None:
            raise KeyError("job_run not found: %s" % job_id)
        validate_transition(current.status, new_status)

        if new_status == "processing":
            holder = self.find_processing(current.job_name, current.target_date)
            if holder is not None and str(holder.id) != str(job_id):
                raise ProcessingLockHeld(holder)

        now = _utcnow()
        updates: Dict[str, Any] = {"status": new_status}
        if new_status == "processing":
            updates["started_at"] = now
        if new_status in {"completed", "failed"}:
            updates["finished_at"] = now
        if error_message is not None:
            updates["error_message"] = error_message
        if new_status == "completed":
            updates["error_message"] = None

        try:
            response = (
                self.client.table("job_runs").update(updates).eq("id", job_id).execute()
            )
            if response.data:
                job = JobRun.from_dict(response.data[0])
                try:
                    self.fallback.transition(
                        job_id, new_status, error_message=error_message
                    )
                except Exception:
                    pass
                return job
        except Exception as exc:
            if new_status == "processing":
                holder = self.find_processing(current.job_name, current.target_date)
                if holder is not None and str(holder.id) != str(job_id):
                    raise ProcessingLockHeld(holder) from exc
            pass
        return self.fallback.transition(
            job_id, new_status, error_message=error_message
        )


_default_store: Optional[JobRunStore] = None


def get_job_run_store(client: Any = None) -> JobRunStore:
    """Return a process-wide store; prefer Supabase when a client is provided."""
    global _default_store
    if _default_store is not None:
        return _default_store
    if client is not None:
        _default_store = SupabaseJobRunStore(client)
    else:
        _default_store = FileJobRunStore()
    return _default_store


def reset_job_run_store() -> None:
    """Clear the cached default store (for tests)."""
    global _default_store
    _default_store = None


def _fail_if_still_processing(
    store: JobRunStore,
    job: Optional[JobRun],
    on_update=None,
) -> Optional[JobRun]:
    """Ensure no job remains in processing after an abort (used from finally)."""
    if job is None:
        return None
    current = store.get(job.id)
    if current is None or current.status != "processing":
        return current

    err = sys.exc_info()[1]
    if err is None:
        message = "execution aborted while processing"
    else:
        message = str(err) or type(err).__name__
    failed = store.transition(job.id, "failed", error_message=message)
    log_job_event(
        "failed",
        job_name=failed.job_name,
        status=failed.status,
        target_date=failed.target_date,
        job_id=failed.id,
        message=failed.error_message,
    )
    if on_update:
        on_update(failed)
    return failed


def execute_with_job_tracking(
    store: JobRunStore,
    target_date: str,
    execute_fn,
    job_name: str = DEFAULT_JOB_NAME,
    on_update=None,
) -> JobRun:
    """Claim processing lock, run execute_fn, then complete or fail.

    Idempotent per (job_name, target_date): if a completed job already exists,
    return it and skip execute_fn (no duplicate pipeline/CSV work).

    The processing status itself is the distributed lock — if another instance
    already holds processing for (job_name, target_date), this raises
    ProcessingLockHeld and does not execute.

    try/except/finally guarantees: after any failure (including BaseException),
    a claimed job does not remain in status=processing — finally transitions it
    to failed unless it already reached completed.

    Every relevant lifecycle event is logged with timestamp, job_name, and status.
    """
    existing = store.find_completed(job_name, target_date)
    if existing is not None:
        log_job_event(
            "idempotent_skip",
            job_name=existing.job_name,
            status=existing.status,
            target_date=existing.target_date,
            job_id=existing.id,
            message="already completed for target_date",
        )
        if on_update:
            on_update(existing)
        return existing

    job: Optional[JobRun] = None
    try:
        job = store.claim_processing(target_date=target_date, job_name=job_name)
        log_job_event(
            "processing",
            job_name=job.job_name,
            status=job.status,
            target_date=job.target_date,
            job_id=job.id,
            message="acquired processing lock",
        )
        if on_update:
            on_update(job)

        execute_fn()
        job = store.transition(job.id, "completed")
        log_job_event(
            "completed",
            job_name=job.job_name,
            status=job.status,
            target_date=job.target_date,
            job_id=job.id,
        )
        if on_update:
            on_update(job)
        return job
    except ProcessingLockHeld as exc:
        holder = exc.holder
        log_job_event(
            "lock_held",
            job_name=holder.job_name,
            status=holder.status,
            target_date=holder.target_date,
            job_id=holder.id,
            message=str(exc),
        )
        raise
    finally:
        # Always release the processing lock on abort; no-op if completed/failed.
        try:
            _fail_if_still_processing(store, job, on_update=on_update)
        except Exception:
            # Do not mask the original failure from the try block.
            pass
