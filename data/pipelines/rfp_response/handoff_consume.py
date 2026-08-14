"""Consume Part 1 routing handoff — sole Part 2 entry contract.

Part 2 entry reads Part 1's routing handoff via **all** of:

| Mechanism | Where |
| --------- | ----- |
| Queue flag | ``rfp_tickets.part2_ready`` |
| DB field | ``rfp_tickets.part2_handoff_json`` |
| Documented contract | ``data/pipelines/rfp_intake/PART2_HANDOFF.md`` + |
|  | ``routing.validate_part2_handoff`` |

Required payload for generators (primary input — **not** the raw PDF):

1. ``ticket_id``
2. Synthesizer / ``work_streams[].key_aspects`` (+ metadata, open_questions)

Do not re-parse the PDF. Do not invent a parallel summary path.
See also ``services.rfp.store.load_ready_part2_handoff``.
"""

from __future__ import annotations

from typing import Any, Final

from data.pipelines.rfp_intake.constants import STATUS_INTAKE_COMPLETE
from data.pipelines.rfp_intake.routing import validate_part2_handoff

# Fields that may appear on the handoff for audit only — never primary generator input
_NON_PRIMARY_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "source_pdf_path",
        "markdown_available_in_db",
        "markdown_text",
        "pdf_path",
        "raw_pdf",
    }
)

PRIMARY_GENERATOR_INPUT: Final[str] = (
    "part1_handoff:ticket_id+work_streams.key_aspects+metadata"
)


class Part1HandoffNotReady(ValueError):
    """Ticket is not ready for Part 2 response generation."""


def assert_part1_routing_ready(
    *,
    ticket_id: str,
    status: str,
    part2_ready: bool,
    handoff: dict[str, Any] | None,
) -> dict[str, Any]:
    """Refuse anything that is not the Part 1 routing handoff contract."""
    tid = (ticket_id or "").strip()
    if not tid:
        raise Part1HandoffNotReady("Part 2 requires ticket_id from Part 1")

    if status != STATUS_INTAKE_COMPLETE:
        raise Part1HandoffNotReady(
            f"Part 2 requires status={STATUS_INTAKE_COMPLETE!r}; got {status!r}"
        )
    if not part2_ready:
        raise Part1HandoffNotReady(
            f"Part 2 requires part2_ready=True queue flag for ticket {tid}"
        )
    if not handoff:
        raise Part1HandoffNotReady(
            f"Part 2 requires part2_handoff_json / handoff contract for ticket {tid}"
        )

    contract = dict(handoff)
    if contract.get("reparse_pdf_required") is True:
        raise Part1HandoffNotReady(
            "Part 2 forbids reparse_pdf_required=True — use key_aspects handoff only"
        )

    # Ensure ticket_id is present and consistent before schema validate
    if not (contract.get("ticket_id") or "").strip():
        contract["ticket_id"] = tid
    if contract["ticket_id"] != tid:
        raise Part1HandoffNotReady(
            f"Handoff ticket_id {contract['ticket_id']!r} != request {tid!r}"
        )

    try:
        validate_part2_handoff(contract)
    except ValueError as exc:
        raise Part1HandoffNotReady(f"Invalid Part 1 handoff contract: {exc}") from exc

    streams = contract.get("work_streams") or []
    if not streams:
        raise Part1HandoffNotReady("Handoff missing work_streams synthesizer payload")
    for stream in streams:
        if not stream.get("department_id"):
            raise Part1HandoffNotReady("work_stream missing department_id")
        aspects = stream.get("key_aspects")
        if not isinstance(aspects, list) or not aspects:
            raise Part1HandoffNotReady(
                f"work_stream {stream.get('department_id')} missing key_aspects "
                "(Part 2 input is synthesizer payload, not a PDF re-summary)"
            )

    return contract


def synthesizer_payload_from_handoff(handoff: dict[str, Any]) -> dict[str, Any]:
    """Extract synthesizer / workstream structure Part 2 generators consume.

    Explicitly omits ``source_pdf_path`` and other raw-PDF fields so generators
    cannot treat the PDF as primary input.
    """
    metadata = dict(handoff.get("metadata") or {})
    for banned in _NON_PRIMARY_FIELDS:
        metadata.pop(banned, None)
    if handoff.get("requires_ceo_approval"):
        metadata["requires_ceo_approval"] = True
    if handoff.get("ceo_approver"):
        metadata.setdefault("ceo_approver", handoff["ceo_approver"])

    return {
        "ticket_id": handoff.get("ticket_id"),
        "primary_input": PRIMARY_GENERATOR_INPUT,
        "metadata": metadata,
        "departments_needed": list(handoff.get("departments_needed") or []),
        "ask_whom": list(handoff.get("ask_whom") or []),
        "open_questions": list(handoff.get("open_questions") or []),
        "requires_ceo_approval": bool(handoff.get("requires_ceo_approval")),
        "synthesizer": dict(handoff.get("synthesizer") or {}),
        "work_streams": list(handoff.get("work_streams") or []),
        # Audit-only pointer from Part 1 (must not be opened by generators)
        "source_pdf_path_audit_only": handoff.get("source_pdf_path"),
    }
