#!/usr/bin/env python3
"""Run one pipeline job instance using processing status as the distributed lock.

Demo (two terminals, same target_date):

  # Terminal 1 — holds the processing lock
  python3 scripts/run_pipeline_job.py --target-date 2026-07-08 --hold-seconds 8

  # Terminal 2 — started while Terminal 1 is still processing
  python3 scripts/run_pipeline_job.py --target-date 2026-07-08 --hold-seconds 1

Expected: instance 1 completes; instance 2 exits with ProcessingLockHeld.

Idempotent re-run (after first completed):

  python3 scripts/run_pipeline_job.py --target-date 2026-07-08 --hold-seconds 1
  python3 scripts/run_pipeline_job.py --target-date 2026-07-08 --hold-seconds 1

Expected: second run prints IDEMPOTENT SKIP and does not re-execute work.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.pipelines.job_runs import (  # noqa: E402
    DEFAULT_JOB_NAME,
    FileJobRunStore,
    ProcessingLockHeld,
    execute_with_job_tracking,
    get_job_run_store,
    reset_job_run_store,
)


def _build_store(store_path: Path, use_supabase: bool):
    if use_supabase:
        try:
            from dotenv import load_dotenv
            from supabase import create_client

            load_dotenv(ROOT / ".env")
            url = os.environ.get("SUPABASE_URL")
            key = os.environ.get("SUPABASE_KEY")
            if url and key:
                reset_job_run_store()
                return get_job_run_store(create_client(url, key))
        except Exception as exc:
            print("Supabase unavailable (%s); using file store." % exc, file=sys.stderr)
    return FileJobRunStore(store_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-date", required=True, help="Business date / lock key")
    parser.add_argument("--job-name", default=DEFAULT_JOB_NAME)
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=2.0,
        help="Sleep while status=processing to allow a second instance to collide",
    )
    parser.add_argument(
        "--store-path",
        default=str(ROOT / "data" / "pipelines" / "job_runs.json"),
        help="Shared file store path (used when Supabase is off)",
    )
    parser.add_argument(
        "--supabase",
        action="store_true",
        help="Use Supabase job_runs as the lock store when credentials exist",
    )
    parser.add_argument(
        "--instance-label",
        default=str(os.getpid()),
        help="Label printed in logs (defaults to PID)",
    )
    args = parser.parse_args()

    store = _build_store(Path(args.store_path), use_supabase=args.supabase)
    label = args.instance_label

    def work() -> None:
        print(
            "[%s] acquired processing lock for %s / %s — holding %.1fs"
            % (label, args.job_name, args.target_date, args.hold_seconds),
            flush=True,
        )
        time.sleep(args.hold_seconds)
        print("[%s] work finished" % label, flush=True)

    prior = store.find_completed(args.job_name, args.target_date)
    try:
        job = execute_with_job_tracking(
            store=store,
            target_date=args.target_date,
            job_name=args.job_name,
            execute_fn=work,
        )
    except ProcessingLockHeld as exc:
        print("[%s] LOCKED OUT: %s" % (label, exc), flush=True)
        return 2

    if prior is not None and str(prior.id) == str(job.id):
        print(
            "[%s] IDEMPOTENT SKIP: already completed job_id=%s target_date=%s — no re-execution"
            % (label, job.id, job.target_date),
            flush=True,
        )
        return 0

    print(
        "[%s] done status=%s job_id=%s target_date=%s"
        % (label, job.status, job.id, job.target_date),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
