"""Load historical Brasaland incidents into the incident manager.

Reads the analyzer CSV, reuses packages.shared.incident_rules, maps rows onto
the live model, and skips invalid rows. Running twice does not duplicate rows.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "services" / "api"
for path in (REPO_ROOT, API_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from incident_store import seed_csv  # noqa: E402

DEFAULT_CSV = REPO_ROOT / "scripts" / "incidents-brasaland.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed Brasaland incidents from the analyzer CSV")
    parser.add_argument("csv_path", nargs="?", default=str(DEFAULT_CSV))
    parser.add_argument("--database", default=None, help="SQLite path (default: data/company_api.db)")
    args = parser.parse_args(argv)
    csv_path = Path(args.csv_path)
    if not csv_path.is_absolute():
        csv_path = REPO_ROOT / csv_path
    if not csv_path.exists():
        print(f"CSV not found: {csv_path.name}", file=sys.stderr)
        return 1
    database = Path(args.database) if args.database else None
    report = seed_csv(csv_path, database)
    print(report.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
