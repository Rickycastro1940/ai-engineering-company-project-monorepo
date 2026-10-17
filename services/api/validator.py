"""CSV row validation for the incident analyzer. Shared with the seed script."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from packages.shared.incident_rules import ValidationResult, validate_record  # noqa: E402

__all__ = ["ValidationResult", "validate_record"]
