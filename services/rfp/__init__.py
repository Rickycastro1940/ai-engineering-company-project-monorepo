"""Brasaland RFP intake — upload, convert (markitdown), readability score."""

from __future__ import annotations

import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from markitdown import MarkItDown

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE_DIR = REPO_ROOT / "data" / "process" / "rfp-intake"

router = APIRouter(prefix="/rfp", tags=["rfp-intake"])

ALLOWED_SUFFIXES = frozenset(
    {".pdf", ".doc", ".docx", ".txt", ".md", ".html", ".htm", ".rtf"}
)


def _safe_filename(name: str) -> str:
    base = Path(name or "rfp.bin").name
    cleaned = re.sub(r"[^\w.\-]+", "_", base).strip("._") or "rfp.bin"
    return cleaned[:180]


def _extract_markdown(path: Path) -> str:
    md = MarkItDown()
    result = md.convert(str(path))
    text = getattr(result, "text_content", None) or str(result)
    return (text or "").strip()


def _readability_score(text: str) -> float | None:
    """Flesch reading-ease when text is long enough; otherwise None."""
    words = re.findall(r"\b\w+\b", text or "")
    if len(words) < 100:
        return None
    try:
        from readability import Readability

        return float(Readability(text).flesch().score)
    except Exception:  # noqa: BLE001 — short/odd text; intake still succeeds
        return None


def store_dir() -> Path:
    path = Path(
        __import__("os").environ.get("RFP_INTAKE_DIR", str(DEFAULT_STORE_DIR))
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.post("/upload")
async def upload_rfp(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
) -> dict[str, Any]:
    """Accept an RFP upload from the backoffice UI, convert, and score readability."""
    original = file.filename or "rfp.bin"
    suffix = Path(original).suffix.lower()
    if suffix and suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(ALLOWED_SUFFIXES)}",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")

    intake_id = uuid4().hex
    safe = _safe_filename(original)
    dest_dir = store_dir() / intake_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe
    dest_path.write_bytes(raw)

    with tempfile.NamedTemporaryFile(suffix=suffix or ".bin", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)

    try:
        markdown = _extract_markdown(tmp_path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=422,
            detail=f"Could not convert document with markitdown: {type(exc).__name__}",
        ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    md_path = dest_dir / "extracted.md"
    md_path.write_text(markdown + ("\n" if markdown else ""), encoding="utf-8")

    score = _readability_score(markdown)
    display_title = (title or "").strip() or safe

    def _rel(path: Path) -> str:
        try:
            return str(path.relative_to(REPO_ROOT))
        except ValueError:
            return str(path)

    meta = {
        "id": intake_id,
        "title": display_title,
        "filename": safe,
        "original_filename": original,
        "stored_path": _rel(dest_path),
        "markdown_path": _rel(md_path),
        "markdown_chars": len(markdown),
        "readability_score": score,
        "uploaded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "uploaded",
    }
    (dest_dir / "meta.json").write_text(
        __import__("json").dumps(meta, indent=2) + "\n",
        encoding="utf-8",
    )
    return meta
