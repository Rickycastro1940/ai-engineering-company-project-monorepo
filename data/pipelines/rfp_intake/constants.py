"""Brasaland RFP intake constants — mirrored from CONTEXT-company.md (Milestone 9).

Re-exports CONTEXT §2.1 department ids/owners/labels. Do not redefine alternate
department names here.
"""

from __future__ import annotations

from typing import Final

from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_CEO_NAME,
    CONTEXT_CEO_USD_THRESHOLD,
    CONTEXT_DEPARTMENT_CONTRIBUTIONS,
    CONTEXT_DEPARTMENT_IDS,
    CONTEXT_DEPARTMENT_LABELS,
    CONTEXT_DEPARTMENT_OWNERS,
    CONTEXT_RFP_METADATA_FIELDS,
    CONTEXT_TICKET_OWNER,
)

# Ticket status (Part 1) — CONTEXT §2.3
STATUS_ANALYZING: Final = "analyzing"
STATUS_INTAKE_COMPLETE: Final = "intake_complete"
STATUS_DISCARDED: Final = "discarded"
STATUS_FAILED: Final = "failed"

P1_TERMINAL: Final = frozenset(
    {STATUS_INTAKE_COMPLETE, STATUS_DISCARDED, STATUS_FAILED}
)

# Departments — exact CONTEXT §2.1 ids (use operaciones, never the English id)
DEPARTMENT_MARKETING: Final = "marketing"
DEPARTMENT_OPERACIONES: Final = "operaciones"
DEPARTMENT_PROCUREMENT: Final = "procurement"
DEPARTMENT_TRAINING: Final = "training"

DEPARTMENT_IDS: Final = frozenset(CONTEXT_DEPARTMENT_IDS)
DEPARTMENT_OWNERS: Final = dict(CONTEXT_DEPARTMENT_OWNERS)
DEPARTMENT_LABELS: Final = dict(CONTEXT_DEPARTMENT_LABELS)
DEPARTMENT_CONTRIBUTIONS: Final = dict(CONTEXT_DEPARTMENT_CONTRIBUTIONS)

CEO_USD_THRESHOLD: Final = CONTEXT_CEO_USD_THRESHOLD
CEO_NAME: Final = CONTEXT_CEO_NAME
TICKET_OWNER: Final = CONTEXT_TICKET_OWNER

RFP_METADATA_FIELDS: Final = CONTEXT_RFP_METADATA_FIELDS

MIN_MARKDOWN_CHARS: Final = 40

# Classifier discard rules (never discard without a rule id + reason)
DISCARD_EMPTY_DOCUMENT: Final = "empty_document"
DISCARD_NOT_AN_RFP: Final = "not_an_rfp"
DISCARD_MISSING_CORE_FIELDS: Final = "missing_core_fields"

# Part 2 handoff contract
HANDOFF_SCHEMA_VERSION: Final = "1.0"
PART2_READY_STATUS: Final = STATUS_INTAKE_COMPLETE
