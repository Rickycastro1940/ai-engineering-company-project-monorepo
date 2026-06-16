from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_INPUT_FILE = "scripts/incidents-COMPANY.csv"
DEFAULT_OUTPUT_FILE = "results.csv"


def analyze_summary(
    input_file: str = DEFAULT_INPUT_FILE,
    output_file: str = DEFAULT_OUTPUT_FILE,
    engine: str = "native",
) -> dict:
    payload = json.dumps(
        {
            "input_file": input_file,
            "output_file": output_file,
            "engine": engine,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE_URL}/api/incidents/analyze/summary",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    print(f"Agent connected to API at {API_BASE_URL}")
    print(f"Analyzing {DEFAULT_INPUT_FILE} ...")
    try:
        summary = analyze_summary()
    except urllib.error.URLError as error:
        print(
            "Could not reach the API. Start it first with: uvicorn api.app:app --reload",
            file=sys.stderr,
        )
        print(f"Details: {error}", file=sys.stderr)
        return 1

    print(f"Summary: {json.dumps(summary, indent=2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
