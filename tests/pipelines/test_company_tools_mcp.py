"""Tests for company-tools MCP server (auth, tools, write rejection)."""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn

from mcps.company_tools.auth import clear_auth_cache
from mcps.company_tools.dev_issuer import mint_access_token
from mcps.company_tools.errors import ErrorCode
from mcps.company_tools.tools.incidents import manage_incident_ticket
from mcps.company_tools.tools.inventory import query_inventory
from services.api.incidents_store import reset_runtime

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


@pytest.fixture(scope="module")
def api_base() -> Iterator[str]:
    """Start the company FastAPI app on an ephemeral port."""
    from api.app import app as api_app

    reset_runtime()
    config = uvicorn.Config(api_app, host="127.0.0.1", port=18000, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            httpx.get("http://127.0.0.1:18000/api/incidents", timeout=0.5)
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    else:
        pytest.fail("company API did not start")
    os.environ["COMPANY_API_BASE"] = "http://127.0.0.1:18000"
    os.environ["INCIDENT_API_BASE"] = "http://127.0.0.1:18000"
    yield "http://127.0.0.1:18000"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def issuer_base() -> Iterator[str]:
    from mcps.company_tools.dev_issuer import app as issuer_app

    config = uvicorn.Config(issuer_app, host="127.0.0.1", port=13002, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            httpx.get("http://127.0.0.1:13002/.well-known/openid-configuration", timeout=0.5).raise_for_status()
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    else:
        pytest.fail("dev issuer did not start")
    os.environ["MCP_AUTH_ISSUER"] = "http://127.0.0.1:13002"
    os.environ["MCP_RESOURCE_ID"] = "http://127.0.0.1:13001/mcp"
    clear_auth_cache()
    yield "http://127.0.0.1:13002"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def mcp_base(issuer_base: str, api_base: str) -> Iterator[str]:
    from mcps.company_tools.server import create_app

    clear_auth_cache()
    asgi = create_app()
    config = uvicorn.Config(asgi, host="127.0.0.1", port=13001, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            # Unauthenticated should be 401, proving the server is up.
            response = httpx.get("http://127.0.0.1:13001/mcp", timeout=0.5)
            if response.status_code in {401, 404, 405, 406}:
                break
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    else:
        pytest.fail("MCP server did not start")
    os.environ["MCP_SERVER_URL"] = "http://127.0.0.1:13001/mcp"
    yield "http://127.0.0.1:13001"
    server.should_exit = True
    thread.join(timeout=5)


def test_mcp_http_clients_only_call_company_api_paths(api_base: str) -> None:
    """MCP tools must rely on the live Incidents/Inventory HTTP API — not replace it."""
    import mcps.company_tools.http_clients as clients

    assert clients.INCIDENTS_COLLECTION_PATH == "/api/incidents"
    assert clients.INCIDENT_STATUS_PATH == "/api/incidents/{incident_id}/status"
    assert clients.PRODUCTS_COLLECTION_PATH == "/inventory/products"

    # Live round-trip against the running company API (same process as other fixtures).
    created = clients.create_incident(
        {
            "category": "EQUIPAMIENTO",
            "description": "MCP relies on Incidents Manager HTTP",
            "status": "ABIERTO",
        },
        base_url=api_base,
    )
    assert created.status_code == 201, created.text
    ticket_id = created.json()["incident_id"]

    got = clients.get_incident(ticket_id, base_url=api_base)
    assert got.status_code == 200
    assert got.json()["incident_id"] == ticket_id

    patched = clients.update_incident_status(ticket_id, "CERRADO", base_url=api_base)
    assert patched.status_code == 200
    assert patched.json()["status"] == "CERRADO"

    products = clients.list_products(base_url=api_base)
    assert products.status_code == 200
    assert isinstance(products.json(), list)
    assert len(products.json()) >= 1

    one = clients.get_product(products.json()[0]["product_id"], base_url=api_base)
    assert one.status_code == 200
    assert one.json()["source"] == "inventory_manager"

    created = manage_incident_ticket(
        action="create",
        category="EQUIPAMIENTO",
        description="MCP test grill fault",
        location_id="COL-01",
        status="ABIERTO",
    )
    assert created["ok"] is True
    ticket_id = created["ticket"]["incident_id"]
    assert ticket_id.startswith("BRS-")

    status = manage_incident_ticket(action="get_status", ticket_id=ticket_id)
    assert status["ok"] is True
    assert status["ticket"]["status"] == "ABIERTO"

    updated = manage_incident_ticket(action="update", ticket_id=ticket_id, status="CERRADO")
    assert updated["ok"] is True
    assert updated["ticket"]["status"] == "CERRADO"


def test_inventory_query_and_write_rejection(api_base: str) -> None:
    ok = query_inventory(action="query", product_id="1")
    assert ok["ok"] is True
    assert ok["products"][0]["product_id"] == "1"

    # Playground often sends blank optional strings — those must still read.
    blank_ok = query_inventory(
        action="",
        product_id="1",
        unit="",
        name="",
        name_contains="",
    )
    assert blank_ok["ok"] is True
    assert blank_ok["products"][0]["product_id"] == "1"

    forbidden = query_inventory(action="update", product_id="1", quantity=99)
    assert forbidden["ok"] is False
    assert forbidden["error_code"] == ErrorCode.INVENTORY_WRITE_FORBIDDEN
    assert forbidden["tool"] == "query_inventory"

    forbidden_fields = query_inventory(action="query", product_id="1", name="Tomatoes", unit="kg")
    assert forbidden_fields["error_code"] == ErrorCode.INVENTORY_WRITE_FORBIDDEN


def test_mcp_rejects_unauthenticated_client(mcp_base: str) -> None:
    response = httpx.post(
        f"{mcp_base}/mcp",
        headers={"Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        timeout=5.0,
    )
    assert response.status_code == 401
    body = response.json()
    # MCP Auth returns RFC-style error; map to our documented codes in README.
    assert body.get("error") in {"invalid_request", "invalid_token", "unauthorized"} or "error" in body


def test_mcp_discovery_with_token(mcp_base: str, issuer_base: str) -> None:
    token = mint_access_token(
        audience="http://127.0.0.1:13001/mcp",
        scopes="incidents:manage inventory:read",
    )
    meta = httpx.get(
        f"{mcp_base}/.well-known/oauth-protected-resource/mcp",
        timeout=5.0,
    )
    assert meta.status_code == 200, meta.text
    payload = meta.json()
    assert payload.get("resource") == "http://127.0.0.1:13001/mcp"
    assert "incidents:manage" in (payload.get("scopes_supported") or [])
    assert "inventory:read" in (payload.get("scopes_supported") or [])
    assert token


def test_incident_api_status_endpoint(api_base: str) -> None:
    create = httpx.post(
        f"{api_base}/api/incidents",
        json={
            "category": "ABASTECIMIENTO",
            "description": "API lifecycle check",
            "status": "ABIERTO",
        },
        timeout=5.0,
    )
    assert create.status_code == 201
    ticket_id = create.json()["incident_id"]
    patch = httpx.patch(
        f"{api_base}/api/incidents/{ticket_id}/status",
        json={"status": "DESCARTADO"},
        timeout=5.0,
    )
    assert patch.status_code == 200
    assert patch.json()["status"] == "DESCARTADO"
    bad = httpx.patch(
        f"{api_base}/api/incidents/{ticket_id}/status",
        json={"status": "CERRADO"},
        timeout=5.0,
    )
    assert bad.status_code == 400
