from __future__ import annotations
import sys
from pathlib import Path
API_ROOT = Path(__file__).resolve().parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
from app import app  # pylint: disable=wrong-import-position, import-error
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
