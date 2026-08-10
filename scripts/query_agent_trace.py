#!/usr/bin/env python3
"""Query persisted agent traces after a run (not console-only).

Examples
--------
uv run python scripts/query_agent_trace.py --list
uv run python scripts/query_agent_trace.py --id <trace_id>
uv run python scripts/query_agent_trace.py --node retrieve --status ok
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.agent.tracing import load_trace, query_traces  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Query LangGraph agent run traces")
    parser.add_argument("--list", action="store_true", help="List recent traces")
    parser.add_argument("--id", dest="trace_id", help="Load one trace by id")
    parser.add_argument("--node", help="Filter runs that executed this node")
    parser.add_argument("--status", help="Filter by run status (ok|error)")
    parser.add_argument("--question-contains", help="Substring match on question")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    if args.trace_id:
        print(json.dumps(load_trace(args.trace_id), indent=2, ensure_ascii=False))
        return 0

    traces = query_traces(
        node=args.node,
        status=args.status,
        question_contains=args.question_contains,
        limit=args.limit,
    )
    if args.list or args.node or args.status or args.question_contains:
        summary = [
            {
                "trace_id": t.get("trace_id"),
                "status": t.get("status"),
                "question": t.get("question"),
                "node_order": t.get("node_order"),
                "answer": (t.get("answer") or "")[:120],
            }
            for t in traces
        ]
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
