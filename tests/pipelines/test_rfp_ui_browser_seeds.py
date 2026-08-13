"""Browser UI: upload CONTEXT sample PDFs via uis/backoffice/rfp-upload.html.

Drives the real form (file input + submit + status poll) with Playwright.
Starts a local uvicorn if ``RFP_UI_BASE_URL`` is not already healthy.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
ARTIFACTS = Path(os.getenv("RFP_UI_ARTIFACTS", "/opt/cursor/artifacts/screenshots"))

pytest.importorskip("playwright.sync_api")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def ui_base_url(tmp_path_factory):
    """Use RFP_UI_BASE_URL if healthy; otherwise boot uvicorn for this module."""
    import urllib.request

    configured = (os.getenv("RFP_UI_BASE_URL") or "").rstrip("/")
    if configured:
        try:
            with urllib.request.urlopen(f"{configured}/health", timeout=2) as resp:
                if resp.status == 200:
                    yield configured
                    return
        except Exception:
            pass

    db = tmp_path_factory.mktemp("ui-browser") / "rfp.sqlite"
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{db}",
            "RFP_ALLOW_SQLITE": "1",
            "RFP_INTAKE_SYNC": "1",
        }
    )
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "services.agent.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(REPO),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"{base}/health", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.25)
        else:
            proc.kill()
            pytest.skip("Could not start UI uvicorn for browser tests")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def browser_page(ui_base_url):
    from playwright.sync_api import sync_playwright

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        page._ui_base_url = ui_base_url  # type: ignore[attr-defined]
        yield page
        browser.close()


def _upload_via_ui(page, pdf: Path, screenshot_name: str) -> str:
    base = page._ui_base_url  # type: ignore[attr-defined]
    page.goto(f"{base}/rfp-upload.html", wait_until="networkidle")
    page.set_input_files("#file", str(pdf))
    page.fill("#title", f"UI browser {pdf.name}")
    page.click("#submit-btn")
    page.wait_for_function(
        """() => {
            const el = document.getElementById('status');
            if (!el || !el.textContent) return false;
            const t = el.textContent;
            return t.includes('status: intake_complete')
                || t.includes('status: discarded')
                || t.includes('status: failed');
        }""",
        timeout=120_000,
    )
    text = page.locator("#status").inner_text()
    page.screenshot(path=str(ARTIFACTS / screenshot_name), full_page=True)
    return text


def test_browser_ui_formal_accept(browser_page) -> None:
    text = _upload_via_ui(
        browser_page,
        SEEDS / "CONTEXT-brasaland-request-1.pdf",
        "rfp-ui-formal-result.png",
    )
    assert "status: intake_complete" in text
    assert "Sunset Bay" in text
    assert "training" in text
    assert "ticket_id:" in text


def test_browser_ui_informal_accept(browser_page) -> None:
    text = _upload_via_ui(
        browser_page,
        SEEDS / "CONTEXT-brasaland-request-2.pdf",
        "rfp-ui-informal-result.png",
    )
    assert "status: intake_complete" in text
    assert "Andes Tech" in text
    dept_line = next(
        (ln for ln in text.splitlines() if ln.startswith("departments:")), ""
    )
    assert dept_line
    assert "training" not in dept_line


def test_browser_ui_invalid_reject(browser_page) -> None:
    text = _upload_via_ui(
        browser_page,
        SEEDS / "CONTEXT-brasaland-request-3.pdf",
        "rfp-ui-invalid-result.png",
    )
    assert "status: discarded" in text
    assert "discard_reason:" in text
    assert "Franchise" in text or "franchise" in text.casefold()
