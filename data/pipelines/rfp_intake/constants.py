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
