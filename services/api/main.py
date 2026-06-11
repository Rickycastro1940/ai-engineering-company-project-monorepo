from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INCIDENT_ANALYZER_ROOT = ROOT / "incident-analyzer"
if str(INCIDENT_ANALYZER_ROOT) not in sys.path:
    sys.path.insert(0, str(INCIDENT_ANALYZER_ROOT))

from src.api import app  # pylint: disable=wrong-import-position, import-error


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
