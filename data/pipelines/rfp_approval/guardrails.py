"""Part 3 guardrails and flow control (CONTEXT §3 / §7).

1. Maximum iteration limit on department request_changes loops.
2. Explicit arbitration is in ``arbitration.py`` (fixed arbiter table, not LLM).
3. Per-node trace fields (agent / input / output / timestamp) live in ``graph._event``.
"""

from __future__ import annotations

from typing import Any, Final

# Align with CONTEXT §3 KPI (average iterations per section < 2) and Part 2's
# ``MAX_SECTION_ITERATIONS``. Caps how many times a department can be forced
# (or asked) into ``request_changes`` before the graph stops bouncing.
MAX_DEPARTMENT_APPROVAL_ITERATIONS: Final[int] = 2

ITERATION_LIMIT_MESSAGE: Final = (
    "Maximum department approval iterations exceeded "
    f"({MAX_DEPARTMENT_APPROVAL_ITERATIONS}); needs human review"
)


def merge_iteration_counts(
    left: dict[str, int] | None, right: dict[str, int] | None
) -> dict[str, int]:
    """Reducer: keep the higher per-department count across parallel writes."""
    out = {str(k): int(v) for k, v in dict(left or {}).items()}
    for key, value in dict(right or {}).items():
        dept = str(key)
        out[dept] = max(int(out.get(dept, 0)), int(value))
    return out


def bump_department_iterations(
    current: dict[str, int] | None,
    departments: list[str] | tuple[str, ...] | set[str],
    *,
    limit: int = MAX_DEPARTMENT_APPROVAL_ITERATIONS,
) -> tuple[dict[str, int], list[str]]:
    """Increment iteration counts for departments entering another change loop.

    Returns ``(updated_counts, exceeded_departments)``.
    """
    counts = {str(k): int(v) for k, v in dict(current or {}).items()}
    exceeded: list[str] = []
    for dept in departments:
        name = str(dept or "").strip()
        if not name:
            continue
        counts[name] = int(counts.get(name, 0)) + 1
        if counts[name] > limit:
            exceeded.append(name)
    return counts, exceeded


def iteration_limit_error(exceeded: list[str]) -> str:
    depts = ", ".join(exceeded)
    return f"{ITERATION_LIMIT_MESSAGE}: {depts}"


def trace_has_required_fields(event: dict[str, Any]) -> bool:
    """Every node execution must log agent, input, output, and timestamp."""
    return all(
        key in event for key in ("node", "agent", "input", "output", "timestamp")
    )
