"""``python -m services.agent.harness`` → guardrail session summary CLI."""

from services.agent.harness.observability import main

if __name__ == "__main__":
    raise SystemExit(main())
