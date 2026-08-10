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


def test_incident_create_and_status_lifecycle(api_base: str) -> None:
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


def test_acceptance_domain_fields_match_company_apis(api_base: str) -> None:
    """Rubric: MCP field names/IDs/domain values must match existing company APIs."""
    from services.api.constants import VALID_CATEGORIES, VALID_STATUSES
    from services.api.incidents_store import IncidentCreateInput, IncidentRecord
    from services.api.inventory import InventoryProduct as ApiInventoryProduct

    from mcps.company_tools.schemas import IncidentTicket, InventoryProduct as McpInventoryProduct

    assert set(IncidentTicket.model_fields) == set(IncidentRecord.model_fields)
    assert set(McpInventoryProduct.model_fields) == set(ApiInventoryProduct.model_fields)
    assert VALID_STATUSES == {"ABIERTO", "CERRADO", "DESCARTADO"}
    assert "QUEJA_CLIENTE" in VALID_CATEGORIES

    created = manage_incident_ticket(
        action="create",
        category="CALIDAD_ALIMENTO",
        description="Acceptance: MCP create uses IncidentCreateInput fields",
        location_id="FLA-02",
        customer_id="CUST-9",
        reporter_id="REP-1",
        satisfaction_score=4.5,
        status="ABIERTO",
    )
    assert created["ok"] is True, created
    ticket = created["ticket"]
    assert set(ticket) >= set(IncidentRecord.model_fields)
    assert ticket["incident_id"].startswith("BRS-")
    assert ticket["category"] == "CALIDAD_ALIMENTO"
    assert ticket["location_id"] == "FLA-02"
    assert ticket["customer_id"] == "CUST-9"
    assert ticket["reporter_id"] == "REP-1"
    assert ticket["satisfaction_score"] == 4.5
    assert ticket["source"] == "incident_manager"
    assert set(IncidentCreateInput.model_fields) <= {
        "category",
        "description",
        "status",
        "date",
        "location_id",
        "customer_id",
        "satisfaction_score",
        "reporter_id",
    }

    products = query_inventory(action="list")
    assert products["ok"] is True
    assert products["products"]
    product = products["products"][0]
    assert set(product) >= set(ApiInventoryProduct.model_fields)
    assert product["source"] == "inventory_manager"


def test_acceptance_status_update_uses_lifecycle_endpoint_only(api_base: str, monkeypatch) -> None:
    """Rubric: status changes MUST use PATCH /api/incidents/{id}/status."""
    import mcps.company_tools.http_clients as clients

    assert clients.INCIDENT_STATUS_PATH == "/api/incidents/{incident_id}/status"
    assert not hasattr(clients, "update_incident")
    assert not hasattr(clients, "patch_incident")

    created = manage_incident_ticket(
        action="create",
        category="PERSONAL",
        description="Acceptance: lifecycle endpoint only for status changes",
        status="ABIERTO",
    )
    assert created["ok"] is True
    ticket_id = created["ticket"]["incident_id"]

    seen: list[str] = []
    real_patch = httpx.Client.patch

    def tracking_patch(self, url, *args, **kwargs):  # noqa: ANN001
        seen.append(str(url))
        return real_patch(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "patch", tracking_patch)
    updated = manage_incident_ticket(action="update", ticket_id=ticket_id, status="CERRADO")
    assert updated["ok"] is True, updated
    assert updated["ticket"]["status"] == "CERRADO"
    assert seen, "expected at least one PATCH"
    assert all(url.endswith(f"/api/incidents/{ticket_id}/status") for url in seen), seen
    assert not any(
        url.rstrip("/").endswith(f"/api/incidents/{ticket_id}") and not url.endswith("/status")
        for url in seen
    )


def test_acceptance_oauth_via_mcpauth_not_fastmcp_auth(mcp_base: str) -> None:
    """Rubric: MCP Server must use OAuth via MCP Auth (mcpauth)."""
    import mcps.company_tools.auth as auth_mod
    import mcps.company_tools.server as server_mod

    assert auth_mod.MCPAuth.__module__.startswith("mcpauth")
    assert auth_mod.SCOPE_INCIDENTS_MANAGE == "incidents:manage"
    assert auth_mod.SCOPE_INVENTORY_READ == "inventory:read"
    # FastMCP is the tool host only — no FastMCP AuthSettings / built-in auth wiring.
    assert not hasattr(server_mod.mcp, "auth") or server_mod.mcp.auth is None
    source = Path(server_mod.__file__).read_text(encoding="utf-8")
    assert "from mcpauth" in Path(auth_mod.__file__).read_text(encoding="utf-8")
    assert "AuthSettings" not in source
    assert "mcp.server.auth" not in source

    meta = httpx.get(f"{mcp_base}/.well-known/oauth-protected-resource/mcp", timeout=5.0)
    assert meta.status_code == 200
    payload = meta.json()
    assert "incidents:manage" in (payload.get("scopes_supported") or [])
    assert "inventory:read" in (payload.get("scopes_supported") or [])
