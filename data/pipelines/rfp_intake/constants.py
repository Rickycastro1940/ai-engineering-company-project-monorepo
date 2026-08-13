"""Brasaland RFP intake constants — from CONTEXT-company.md (Milestone 9)."""

from __future__ import annotations

from typing import Final

# Ticket status (Part 1)
STATUS_ANALYZING: Final = "analyzing"
STATUS_INTAKE_COMPLETE: Final = "intake_complete"
STATUS_DISCARDED: Final = "discarded"
STATUS_FAILED: Final = "failed"

P1_TERMINAL: Final = frozenset(
    {STATUS_INTAKE_COMPLETE, STATUS_DISCARDED, STATUS_FAILED}
)

# Departments — exact CONTEXT ids
DEPARTMENT_MARKETING: Final = "marketing"
DEPARTMENT_OPERACIONES: Final = "operaciones"
DEPARTMENT_PROCUREMENT: Final = "procurement"
DEPARTMENT_TRAINING: Final = "training"

DEPARTMENT_IDS: Final = frozenset(
    {
        DEPARTMENT_MARKETING,
        DEPARTMENT_OPERACIONES,
        DEPARTMENT_PROCUREMENT,
        DEPARTMENT_TRAINING,
    }
)

DEPARTMENT_OWNERS: Final = {
    DEPARTMENT_MARKETING: "Camila Ospina",
    DEPARTMENT_OPERACIONES: "Felipe Guerrero",
    DEPARTMENT_PROCUREMENT: "Lucía Fernández",
    DEPARTMENT_TRAINING: "Jake Morrison",
}

DEPARTMENT_LABELS: Final = {
    DEPARTMENT_MARKETING: "Marketing and Digital Experience",
    DEPARTMENT_OPERACIONES: "Restaurant Operations",
    DEPARTMENT_PROCUREMENT: "Procurement and Suppliers",
    DEPARTMENT_TRAINING: "Training and Quality Standards",
}

CEO_USD_THRESHOLD: Final = 50_000.0
CEO_NAME: Final = "Mariana Restrepo"

MIN_MARKDOWN_CHARS: Final = 40

# Classifier discard rules (never discard without a rule id + reason)
DISCARD_EMPTY_DOCUMENT: Final = "empty_document"
DISCARD_NOT_AN_RFP: Final = "not_an_rfp"
DISCARD_MISSING_CORE_FIELDS: Final = "missing_core_fields"

# Part 2 handoff contract
HANDOFF_SCHEMA_VERSION: Final = "1.0"
PART2_READY_STATUS: Final = STATUS_INTAKE_COMPLETE
