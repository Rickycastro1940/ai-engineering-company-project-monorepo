from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _load_incident_analyzer():
    repo_root = Path(__file__).resolve().parents[1]
    api_root = repo_root / "services" / "api"
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))

    from analyzer import IncidentAnalyzer  # pylint: disable=import-error

    return IncidentAnalyzer


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1 incident analysis script")
    parser.add_argument(
        "input_csv",
        nargs="?",
        default="scripts/incidents-COMPANY.csv",
        help="Path to input incidents CSV file",
    )
    parser.add_argument(
        "--output",
        default="scripts/results.csv",
        help="Path for exported summary CSV",
    )
    parser.add_argument(
        "--engine",
        default="native",
        choices=["native", "pandas"],
        help="CSV load engine",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    input_path = (repo_root / args.input_csv).resolve() if not Path(args.input_csv).is_absolute() else Path(args.input_csv)
    output_path = (repo_root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)

    IncidentAnalyzer = _load_incident_analyzer()
    analyzer = IncidentAnalyzer.from_file(input_path, engine=args.engine)
    analyzer.export_summary_to_csv(output_path)

    print(analyzer.build_console_summary())
    print(f"Exported CSV: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
