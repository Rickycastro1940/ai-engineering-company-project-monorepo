"""RFP intake upload — markitdown conversion + readability (deterministic)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.rfp import router as rfp_router


def _app(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("RFP_INTAKE_DIR", str(tmp_path / "rfp-intake"))
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_rfp_upload_accepts_markdown_and_scores(tmp_path: Path, monkeypatch) -> None:
    client = _app(tmp_path, monkeypatch)
    # ≥100 words so Flesch can score.
    body = (
        "Brasaland grilled restaurants operate in Colombia and Florida. "
        "Lucía Fernández approves emergency protein orders over 500 USD. "
        "Felipe Guerrero escalates waste protocol issues. "
        "Keep USD and COP exactly as written and never convert currencies. "
        "Never claim zero risk or 100 percent safe for allergens. "
    ) * 8
    files = {"file": ("sample-rfp.md", body.encode("utf-8"), "text/markdown")}
    data = {"title": "Sample supplier RFP"}
    res = client.post("/rfp/upload", files=files, data=data)
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["title"] == "Sample supplier RFP"
    assert payload["filename"] == "sample-rfp.md"
    assert payload["markdown_chars"] > 100
    assert payload["readability_score"] is not None
    assert payload["status"] == "uploaded"
    stored = tmp_path / "rfp-intake" / payload["id"] / "sample-rfp.md"
    assert stored.is_file()


def test_rfp_upload_rejects_unsupported_type(tmp_path: Path, monkeypatch) -> None:
    client = _app(tmp_path, monkeypatch)
    files = {"file": ("notes.exe", b"MZ", "application/octet-stream")}
    res = client.post("/rfp/upload", files=files)
    assert res.status_code == 400
