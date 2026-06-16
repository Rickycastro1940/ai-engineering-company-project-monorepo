from __future__ import annotations

import csv
import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_INPUT_FILE = "scripts/incidents-COMPANY.csv"
DEFAULT_OUTPUT_FILE = "results.csv"
CONVERSATION_LOG = Path("conversation_log.csv")
LOG_HEADERS = ["timestamp", "session_id", "role", "message"]


def append_conversation(session_id: str, role: str, message: str) -> None:
    file_exists = CONVERSATION_LOG.exists() and CONVERSATION_LOG.stat().st_size > 0
    with CONVERSATION_LOG.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "role": role,
                "message": message,
            }
        )


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
    session_id = str(uuid.uuid4())
    print(f"Agent connected to API at {API_BASE_URL}")
    print(f"Session: {session_id}")
    append_conversation(session_id, "system", f"Started new session at {API_BASE_URL}")

    print(f"Analyzing {DEFAULT_INPUT_FILE} ...")
    append_conversation(session_id, "agent", f"Analyzing {DEFAULT_INPUT_FILE}")

    try:
        summary = analyze_summary()
    except urllib.error.URLError as error:
        message = (
            "Could not reach the API. Start it first with: uvicorn api.app:app --reload"
        )
        print(message, file=sys.stderr)
        print(f"Details: {error}", file=sys.stderr)
        append_conversation(session_id, "system", f"Error: {error}")
        return 1

    summary_text = json.dumps(summary, indent=2)
    print(f"Summary: {summary_text}")
    append_conversation(session_id, "agent", summary_text)
    append_conversation(session_id, "system", "Session completed")
    print(f"Conversation appended to {CONVERSATION_LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
