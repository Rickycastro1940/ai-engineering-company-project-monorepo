#!/usr/bin/env python3
"""Launch two job instances at once to prove processing is the distributed lock."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_pipeline_job.py"


def main() -> int:
    target_date = "2026-07-08"
    with tempfile.TemporaryDirectory(prefix="job-lock-demo-") as tmp:
        store_path = Path(tmp) / "job_runs.json"
        store_path.write_text("[]", encoding="utf-8")

        common = [
            sys.executable,
            str(RUNNER),
            "--target-date",
            target_date,
            "--store-path",
            str(store_path),
        ]

        print("Starting instance A (holds processing for 5s)...")
        proc_a = subprocess.Popen(
            common + ["--hold-seconds", "5", "--instance-label", "A"],
            cwd=str(ROOT),
        )
        time.sleep(0.4)

        print("Starting instance B (should be locked out)...")
        proc_b = subprocess.Popen(
            common + ["--hold-seconds", "1", "--instance-label", "B"],
            cwd=str(ROOT),
        )

        code_a = proc_a.wait()
        code_b = proc_b.wait()

        print("---")
        print("instance A exit:", code_a, "(expect 0 = completed)")
        print("instance B exit:", code_b, "(expect 2 = ProcessingLockHeld)")

        if code_a == 0 and code_b == 2:
            print("PASS: processing status acted as the distributed lock.")
            return 0

        print("FAIL: unexpected exit codes.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
