"""Analyzer CSV constants. The live manager enums live in packages.shared.incident_rules."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from packages.shared.incident_rules import (  # noqa: E402
    MIN_DESCRIPTION_LENGTH,
    REQUIRED_COLUMNS,
    VALID_CATEGORIES,
    VALID_STATUSES,
)

__all__ = [
    "MIN_DESCRIPTION_LENGTH",
    "REQUIRED_COLUMNS",
    "VALID_CATEGORIES",
    "VALID_STATUSES",
]
