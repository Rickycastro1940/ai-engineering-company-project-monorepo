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

EXPECTED_MCP_TOOLS = ("manage_incident_ticket", "query_inventory")


def test_mcp_server_lives_under_mcps_and_starts() -> None:
    """Rubric: MCP server lives under ``mcps/`` and ``create_app`` starts cleanly."""
    package_root = REPO_ROOT / "mcps" / "company_tools"
    assert package_root.is_dir()
    assert (package_root / "server.py").is_file()
    assert (package_root / "__main__.py").is_file()

    # Import path must be the monorepo ``mcps`` package (not a stray copy).
    import mcps.company_tools.server as server_mod

    assert Path(server_mod.__file__).resolve().is_relative_to(package_root.resolve())

    os.environ.setdefault("MCP_AUTH_ISSUER", "http://127.0.0.1:3002")
    os.environ.setdefault("MCP_RESOURCE_ID", "http://127.0.0.1:13001/mcp")
    app = server_mod.create_app()
    assert app is not None
    assert server_mod.mcp.name == "Brasaland Company Tools"
    assert getattr(server_mod.mcp.settings, "auth", None) is None


def test_mcp_standard_discovery_exposes_tools(mcp_base: str) -> None:
    """Rubric: tools are exposed via standard MCP ``tools/list`` discovery."""
    import asyncio

    from mcps.company_tools.server import mcp

    in_process = asyncio.run(mcp.list_tools())
    assert sorted(t.name for t in in_process) == sorted(EXPECTED_MCP_TOOLS)
    for tool in in_process:
        assert tool.description
        assert tool.inputSchema

    token = mint_access_token(
        audience="http://127.0.0.1:13001/mcp",
        scopes="incidents:read inventory:read",
        client_id="discovery-eval",
    )
    response, body = _mcp_rpc(mcp_base, token, "tools/list", {})
    assert response.status_code == 200
    discovered = body["result"]["tools"]
    names = sorted(t["name"] for t in discovered)
    assert names == sorted(EXPECTED_MCP_TOOLS)
    for entry in discovered:
        assert entry.get("description")
        assert entry.get("inputSchema")


def test_mcp_discovery_descriptions_and_schemas_self_explanatory(mcp_base: str) -> None:
    """Rubric: each tool's description + schema are verifiable from discovery alone.

    Assertions use only the ``tools/list`` payload (no source reads).
    """
    token = mint_access_token(
        audience="http://127.0.0.1:13001/mcp",
        scopes="incidents:read inventory:read",
        client_id="discovery-schema-eval",
    )
    response, body = _mcp_rpc(mcp_base, token, "tools/list", {})
    assert response.status_code == 200
    discovered = {t["name"]: t for t in body["result"]["tools"]}
    assert set(discovered) == set(EXPECTED_MCP_TOOLS)

    for name, entry in discovered.items():
        desc = (entry.get("description") or "").strip()
        assert len(desc) >= 40, f"{name} description too short for external clients"
        assert entry.get("title"), f"{name} missing discovery title"

        schema = entry.get("inputSchema")
        assert isinstance(schema, dict), f"{name} missing inputSchema"
        assert schema.get("type") == "object", f"{name} inputSchema.type"
        props = schema.get("properties") or {}
        assert props, f"{name} inputSchema has no properties"
        for prop, spec in props.items():
            assert isinstance(spec, dict), f"{name}.{prop}"
            assert (spec.get("description") or "").strip(), (
                f"{name}.{prop} missing property description in discovery"
            )

        output = entry.get("outputSchema")
        assert isinstance(output, dict) and output, f"{name} missing outputSchema"

    incidents = discovered["manage_incident_ticket"]
    incidents_blob = (
        incidents["description"] + " " + __import__("json").dumps(incidents["inputSchema"])
    ).casefold()
    for needle in (
        "create",
        "update",
        "get_status",
        "ticket_id",
        "abierto",
        "cerrado",
        "descartado",
        "incidents:manage",
        "incidents:read",
    ):
        assert needle in incidents_blob, f"manage_incident_ticket discovery missing {needle!r}"
    action = incidents["inputSchema"]["properties"]["action"]
    assert set(action.get("enum") or []) == {"create", "update", "get_status"}

    inventory = discovered["query_inventory"]
    inventory_blob = (
        inventory["description"] + " " + __import__("json").dumps(inventory["inputSchema"])
    ).casefold()
    for needle in (
        "inventory",
        "read-only",
        "product_id",
        "inventory_write_forbidden",
        "inventory:read",
    ):
        assert needle in inventory_blob, f"query_inventory discovery missing {needle!r}"
    assert "quantity" in inventory["inputSchema"]["properties"]
    assert "WRITE FIELD" in (
        inventory["inputSchema"]["properties"]["quantity"].get("description") or ""
    )


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
    """Rubric: inventory queries succeed; every write attempt is explicitly rejected."""
    from mcps.company_tools.clients import inventory as inventory_client
    from mcps.company_tools.tools.inventory import WRITE_ACTIONS

    ok = query_inventory(action="query", product_id="1")
    assert ok["ok"] is True
    product = ok["products"][0]
    assert product["product_id"] == "1"
    assert product["source"] == "inventory_manager"
    assert set(product) >= {"product_id", "name", "quantity", "unit", "source"}

    listed = query_inventory(action="list")
    assert listed["ok"] is True
    assert len(listed["products"]) >= 1

    filtered = query_inventory(action="query", name_contains="Tom")
    assert filtered["ok"] is True
    assert any("Tomato" in (p.get("name") or "") for p in filtered["products"])

    missing = query_inventory(action="get", product_id="99999")
    assert missing["ok"] is False
    assert missing["error_code"] == ErrorCode.NOT_FOUND

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

    # Explicit rejection for every write-oriented action (not a silent omit).
    for action in sorted(WRITE_ACTIONS):
        forbidden = query_inventory(action=action, product_id="1", quantity=99)
        assert forbidden["ok"] is False, action
        assert forbidden["error_code"] == ErrorCode.INVENTORY_WRITE_FORBIDDEN, action
        assert forbidden["tool"] == "query_inventory"

    # Write fields on a read action are also rejected.
    for kwargs in (
        {"action": "query", "product_id": "1", "quantity": 99},
        {"action": "query", "product_id": "1", "delta": -1},
        {"action": "query", "product_id": "1", "unit": "kg"},
        {"action": "query", "product_id": "1", "name": "Hacked"},
    ):
        forbidden_fields = query_inventory(**kwargs)
        assert forbidden_fields["error_code"] == ErrorCode.INVENTORY_WRITE_FORBIDDEN, kwargs

    # Least privilege at the HTTP client: GET-only (no write helpers).
    assert hasattr(inventory_client, "list_products")
    assert hasattr(inventory_client, "get_product")
    assert not hasattr(inventory_client, "create_product")
    assert not hasattr(inventory_client, "update_product")
    assert not hasattr(inventory_client, "delete_product")


def test_inventory_mcp_query_and_write_rejection_over_tools_call(mcp_base: str, api_base: str) -> None:
    """Same rubric over the MCP transport (authenticated tools/call)."""
    token = mint_access_token(
        audience="http://127.0.0.1:13001/mcp",
        scopes="inventory:read",
        client_id="inventory-eval",
    )

    list_resp, list_body = _mcp_rpc(
        mcp_base,
        token,
        "tools/call",
        {"name": "query_inventory", "arguments": {"action": "list"}},
        request_id=1,
    )
    assert list_resp.status_code == 200
    listed = __import__("json").loads(list_body["result"]["content"][0]["text"])
    assert listed["ok"] is True
    assert listed["products"]

    get_resp, get_body = _mcp_rpc(
        mcp_base,
        token,
        "tools/call",
        {"name": "query_inventory", "arguments": {"action": "get", "product_id": "1"}},
        request_id=2,
    )
    assert get_resp.status_code == 200
    got = __import__("json").loads(get_body["result"]["content"][0]["text"])
    assert got["ok"] is True
    assert got["products"][0]["product_id"] == "1"

    for rid, arguments in (
        (3, {"action": "update", "product_id": "1", "quantity": 99}),
        (4, {"action": "create", "name": "X", "quantity": 1}),
        (5, {"action": "delete", "product_id": "1"}),
        (6, {"action": "query", "product_id": "1", "delta": 5}),
    ):
        write_resp, write_body = _mcp_rpc(
            mcp_base,
            token,
            "tools/call",
            {"name": "query_inventory", "arguments": arguments},
            request_id=rid,
        )
        assert write_resp.status_code == 200, arguments
        rejected = __import__("json").loads(write_body["result"]["content"][0]["text"])
        assert rejected["ok"] is False, arguments
        assert rejected["error_code"] == ErrorCode.INVENTORY_WRITE_FORBIDDEN, arguments
        assert rejected["tool"] == "query_inventory"


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
    assert "incidents:read" in (payload.get("scopes_supported") or [])
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
    assert auth_mod.SCOPE_INCIDENTS_READ == "incidents:read"
    assert auth_mod.SCOPE_INCIDENTS_MANAGE == "incidents:manage"
    assert auth_mod.SCOPE_INVENTORY_READ == "inventory:read"
    assert auth_mod.TOOL_REQUIRED_SCOPES["query_inventory"] == ["inventory:read"]
    assert "incidents:read" in auth_mod.TOOL_SCOPE_ANY_OF["manage_incident_ticket:get_status"]
    assert auth_mod.TOOL_SCOPE_ANY_OF["manage_incident_ticket:create"] == ["incidents:manage"]
    assert auth_mod.TOOL_SCOPE_ANY_OF["manage_incident_ticket:update"] == ["incidents:manage"]
    # FastMCP is the tool host only — no FastMCP AuthSettings / built-in auth wiring.
    assert server_mod.mcp.settings.auth is None
    source = Path(server_mod.__file__).read_text(encoding="utf-8")
    auth_source = Path(auth_mod.__file__).read_text(encoding="utf-8")
    assert "from mcpauth" in auth_source
    assert "AuthServerType.OIDC" in auth_source
    assert "protected_resources" in auth_source
    assert "from mcp.server.auth" not in source
    assert "import mcp.server.auth" not in source
    # No FastMCP auth wiring — only documented as intentionally unused.
    assert "settings.auth is None" in source or "settings.auth is not None" in source

    meta = httpx.get(f"{mcp_base}/.well-known/oauth-protected-resource/mcp", timeout=5.0)
    assert meta.status_code == 200
    payload = meta.json()
    assert "incidents:read" in (payload.get("scopes_supported") or [])
    assert "incidents:manage" in (payload.get("scopes_supported") or [])
    assert "inventory:read" in (payload.get("scopes_supported") or [])


def _mcp_rpc(mcp_base: str, token: str | None, method: str, params: dict, request_id: int = 1):
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    response = httpx.post(
        f"{mcp_base}/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        timeout=10.0,
    )
    body = response.text
    if "data: " in body:
        for line in body.splitlines():
            if line.startswith("data: "):
                body = line[6:]
                break
    try:
        payload = __import__("json").loads(body)
    except Exception:  # noqa: BLE001
        payload = {"_raw": body}
    return response, payload


def test_mandatory_oauth_blocks_unauthenticated_list_and_invoke(mcp_base: str) -> None:
    """Rubric: no client without a valid access token can list or invoke any tool."""
    list_resp, list_body = _mcp_rpc(mcp_base, None, "tools/list", {})
    assert list_resp.status_code == 401
    assert "error" in list_body
    assert "www-authenticate" in {k.lower() for k in list_resp.headers.keys()}

    # Both exposed tools must be unreachable without a Bearer access token.
    for rid, tool_name, arguments in (
        (2, "query_inventory", {"action": "list"}),
        (
            3,
            "manage_incident_ticket",
            {"action": "get_status", "ticket_id": "BRS-000001"},
        ),
    ):
        call_resp, call_body = _mcp_rpc(
            mcp_base,
            None,
            "tools/call",
            {"name": tool_name, "arguments": arguments},
            request_id=rid,
        )
        assert call_resp.status_code == 401, (tool_name, call_resp.status_code, call_body)
        assert "error" in call_body

    # Invalid Bearer also cannot list or invoke either tool.
    for rid, method, params in (
        (10, "tools/list", {}),
        (
            11,
            "tools/call",
            {"name": "query_inventory", "arguments": {"action": "list"}},
        ),
        (
            12,
            "tools/call",
            {
                "name": "manage_incident_ticket",
                "arguments": {"action": "get_status", "ticket_id": "BRS-000001"},
            },
        ),
    ):
        bad_resp, bad_body = _mcp_rpc(mcp_base, "not-a-jwt", method, params, request_id=rid)
        assert bad_resp.status_code == 401, (method, params, bad_resp.status_code, bad_body)
        assert "error" in bad_body

    init_resp, _ = _mcp_rpc(
        mcp_base,
        None,
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "unauth", "version": "0"},
        },
        request_id=4,
    )
    assert init_resp.status_code == 401


def test_mandatory_oauth_rejects_invalid_and_wrong_audience_tokens(mcp_base: str) -> None:
    bad_resp, bad_body = _mcp_rpc(mcp_base, "not-a-jwt", "tools/list", {})
    assert bad_resp.status_code == 401
    assert bad_body.get("error") in {"invalid_token", "invalid_request", "unauthorized"}

    wrong_aud = mint_access_token(
        audience="https://evil.example/mcp",
        scopes="incidents:manage inventory:read",
    )
    aud_resp, aud_body = _mcp_rpc(mcp_base, wrong_aud, "tools/list", {})
    assert aud_resp.status_code == 401
    assert "error" in aud_body


def test_mandatory_oauth_scope_enforcement_on_invoke(mcp_base: str) -> None:
    """Valid JWT can list tools; invoke still requires the tool's required_scopes."""
    inv_only = mint_access_token(
        audience="http://127.0.0.1:13001/mcp",
        scopes="inventory:read",
        client_id="inv-only",
    )
    list_resp, list_body = _mcp_rpc(mcp_base, inv_only, "tools/list", {})
    assert list_resp.status_code == 200
    tools = [t["name"] for t in list_body["result"]["tools"]]
    assert "manage_incident_ticket" in tools
    assert "query_inventory" in tools

    denied_resp, denied_body = _mcp_rpc(
        mcp_base,
        inv_only,
        "tools/call",
        {
            "name": "manage_incident_ticket",
            "arguments": {"action": "get_status", "ticket_id": "BRS-000001"},
        },
        request_id=2,
    )
    assert denied_resp.status_code == 200
    denied_tool = __import__("json").loads(denied_body["result"]["content"][0]["text"])
    assert denied_tool["ok"] is False
    assert denied_tool["error_code"] == ErrorCode.AUTH_INSUFFICIENT_SCOPE

    ok_resp, ok_body = _mcp_rpc(
        mcp_base,
        inv_only,
        "tools/call",
        {"name": "query_inventory", "arguments": {"action": "list"}},
        request_id=3,
    )
    assert ok_resp.status_code == 200
    ok_tool = __import__("json").loads(ok_body["result"]["content"][0]["text"])
    assert ok_tool["ok"] is True
    assert ok_tool["products"]


def test_least_privilege_incident_read_scope_cannot_write(mcp_base: str, api_base: str) -> None:
    """incidents:read may get_status but must not create/update (required_scopes)."""
    read_only = mint_access_token(
        audience="http://127.0.0.1:13001/mcp",
        scopes="incidents:read",
        client_id="inc-read",
    )
    created = manage_incident_ticket(
        action="create",
        category="EQUIPAMIENTO",
        description="Seed ticket for read-scope least-privilege check",
        status="ABIERTO",
    )
    assert created["ok"] is True
    ticket_id = created["ticket"]["incident_id"]

    get_resp, get_body = _mcp_rpc(
        mcp_base,
        read_only,
        "tools/call",
        {"name": "manage_incident_ticket", "arguments": {"action": "get_status", "ticket_id": ticket_id}},
        request_id=1,
    )
    assert get_resp.status_code == 200
    get_tool = __import__("json").loads(get_body["result"]["content"][0]["text"])
    assert get_tool["ok"] is True
    assert get_tool["ticket"]["incident_id"] == ticket_id

    create_resp, create_body = _mcp_rpc(
        mcp_base,
        read_only,
        "tools/call",
        {
            "name": "manage_incident_ticket",
            "arguments": {
                "action": "create",
                "category": "EQUIPAMIENTO",
                "description": "Should be denied by required_scopes",
            },
        },
        request_id=2,
    )
    create_tool = __import__("json").loads(create_body["result"]["content"][0]["text"])
    assert create_tool["ok"] is False
    assert create_tool["error_code"] == ErrorCode.AUTH_INSUFFICIENT_SCOPE

    update_resp, update_body = _mcp_rpc(
        mcp_base,
        read_only,
        "tools/call",
        {
            "name": "manage_incident_ticket",
            "arguments": {"action": "update", "ticket_id": ticket_id, "status": "CERRADO"},
        },
        request_id=3,
    )
    update_tool = __import__("json").loads(update_body["result"]["content"][0]["text"])
    assert update_tool["ok"] is False
    assert update_tool["error_code"] == ErrorCode.AUTH_INSUFFICIENT_SCOPE


def test_least_privilege_clients_are_domain_isolated() -> None:
    """Incident tool client must not expose inventory ops and vice versa."""
    from mcps.company_tools.clients import incidents as inc
    from mcps.company_tools.clients import inventory as inv

    assert hasattr(inc, "get_incident")
    assert hasattr(inc, "create_incident")
    assert hasattr(inc, "update_incident_status")
    assert not hasattr(inc, "list_products")
    assert not hasattr(inc, "get_product")
    assert inc.INCIDENT_STATUS_PATH.endswith("/status")

    assert hasattr(inv, "list_products")
    assert hasattr(inv, "get_product")
    assert not hasattr(inv, "create_incident")
    assert not hasattr(inv, "update_incident_status")
    # Inventory client is GET-only — no write helpers.
    src = Path(inv.__file__).read_text(encoding="utf-8")
    assert "client.post" not in src
    assert "client.patch" not in src
    assert "client.put" not in src
    assert "client.delete" not in src


def test_least_privilege_update_rejects_non_status_fields(api_base: str) -> None:
    created = manage_incident_ticket(
        action="create",
        category="PERSONAL",
        description="Update must not accept unrelated fields",
        status="ABIERTO",
    )
    assert created["ok"] is True
    ticket_id = created["ticket"]["incident_id"]
    rejected = manage_incident_ticket(
        action="update",
        ticket_id=ticket_id,
        status="CERRADO",
        category="EQUIPAMIENTO",
        description="smuggled",
    )
    assert rejected["ok"] is False
    assert rejected["error_code"] == ErrorCode.VALIDATION_ERROR


def test_error_catalog_defines_distinct_auth_authz_validation_codes() -> None:
    """Failures must use named codes — never a generic 'error' string."""
    from mcps.company_tools.errors import (
        ALL_ERROR_CODES,
        ERROR_CATALOG,
        ExitCode,
        FORBIDDEN_GENERIC_CODES,
        map_transport_oauth_error,
        error_payload,
    )

    codes = {spec.code for spec in ERROR_CATALOG}
    assert codes == ALL_ERROR_CODES
    assert ErrorCode.AUTH_MISSING_TOKEN in codes
    assert ErrorCode.AUTH_INVALID_TOKEN in codes
    assert ErrorCode.AUTH_INVALID_AUDIENCE in codes
    assert ErrorCode.AUTH_INSUFFICIENT_SCOPE in codes
    assert ErrorCode.VALIDATION_ERROR in codes
    assert ErrorCode.LIFECYCLE_ERROR in codes
    assert "error" not in codes
    assert codes.isdisjoint(FORBIDDEN_GENERIC_CODES)

    by_category = {spec.category for spec in ERROR_CATALOG}
    assert {"authentication", "authorization", "validation"} <= by_category

    # Pairwise-disjoint code sets across the three rubric categories.
    grouped: dict[str, set[str]] = {}
    for spec in ERROR_CATALOG:
        grouped.setdefault(spec.category, set()).add(spec.code)
    assert grouped["authentication"].isdisjoint(grouped["authorization"])
    assert grouped["authentication"].isdisjoint(grouped["validation"])
    assert grouped["authorization"].isdisjoint(grouped["validation"])

    assert map_transport_oauth_error("missing_auth_header") == ErrorCode.AUTH_MISSING_TOKEN
    assert map_transport_oauth_error("invalid_token") == ErrorCode.AUTH_INVALID_TOKEN
    assert map_transport_oauth_error("insufficient_scope") == ErrorCode.AUTH_INSUFFICIENT_SCOPE

    payload = error_payload(ErrorCode.VALIDATION_ERROR, "bad input", tool="t")
    assert payload["ok"] is False
    assert payload["error_code"] == ErrorCode.VALIDATION_ERROR
    assert payload["error_code"] != "error"

    try:
        error_payload("error", "nope")
        raise AssertionError("generic error_code must be rejected")
    except ValueError:
        pass

    assert int(ExitCode.SUCCESS) == 0
    assert int(ExitCode.CONFIG_ERROR) == 2
    assert int(ExitCode.AUTH_SETUP_ERROR) == 3
    assert int(ExitCode.VALIDATION_ERROR) == 4


def test_auth_authz_validation_errors_have_distinct_codes_and_messages(
    mcp_base: str, api_base: str
) -> None:
    """Rubric: authentication, authorization, and validation failures are distinguishable."""
    from mcps.company_tools.errors import FORBIDDEN_GENERIC_CODES, map_transport_oauth_error

    samples: list[tuple[str, str, str]] = []  # category, code, message

    # --- Authentication (transport) ---
    missing = httpx.post(
        f"{mcp_base}/mcp",
        headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        timeout=5.0,
    )
    assert missing.status_code == 401
    missing_body = missing.json()
    auth_code = map_transport_oauth_error(missing_body.get("error"))
    auth_msg = str(
        missing_body.get("error_description") or missing_body.get("error") or ""
    ).strip()
    assert auth_code == ErrorCode.AUTH_MISSING_TOKEN
    assert auth_msg
    samples.append(("authentication", auth_code, auth_msg))

    invalid = httpx.post(
        f"{mcp_base}/mcp",
        headers={
            "Authorization": "Bearer not-a-jwt",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        timeout=5.0,
    )
    assert invalid.status_code == 401
    invalid_body = invalid.json()
    auth_code_2 = map_transport_oauth_error(invalid_body.get("error"))
    auth_msg_2 = str(
        invalid_body.get("error_description") or invalid_body.get("error") or ""
    ).strip()
    assert auth_code_2 == ErrorCode.AUTH_INVALID_TOKEN
    assert auth_msg_2
    samples.append(("authentication", auth_code_2, auth_msg_2))

    # --- Authorization (valid token, wrong privilege) ---
    inv_only = mint_access_token(
        audience="http://127.0.0.1:13001/mcp",
        scopes="inventory:read",
        client_id="err-distinct-inv",
    )
    denied_resp, denied_body = _mcp_rpc(
        mcp_base,
        inv_only,
        "tools/call",
        {
            "name": "manage_incident_ticket",
            "arguments": {"action": "get_status", "ticket_id": "BRS-000001"},
        },
        request_id=2,
    )
    assert denied_resp.status_code == 200
    denied = __import__("json").loads(denied_body["result"]["content"][0]["text"])
    assert denied["ok"] is False
    assert denied["error_code"] == ErrorCode.AUTH_INSUFFICIENT_SCOPE
    assert denied["error_code"] not in FORBIDDEN_GENERIC_CODES
    assert (denied.get("message") or "").strip()
    samples.append(("authorization", denied["error_code"], denied["message"]))

    write = query_inventory(action="update", product_id="1", quantity=99)
    assert write["error_code"] == ErrorCode.INVENTORY_WRITE_FORBIDDEN
    assert (write.get("message") or "").strip()
    samples.append(("authorization", write["error_code"], write["message"]))

    # --- Validation (authenticated, wrong/missing input) ---
    full = mint_access_token(
        audience="http://127.0.0.1:13001/mcp",
        scopes="incidents:manage inventory:read",
        client_id="err-distinct-full",
    )
    val_resp, val_body = _mcp_rpc(
        mcp_base,
        full,
        "tools/call",
        {
            "name": "manage_incident_ticket",
            "arguments": {"action": "update", "ticket_id": "BRS-000001"},
        },
        request_id=3,
    )
    assert val_resp.status_code == 200
    validated = __import__("json").loads(val_body["result"]["content"][0]["text"])
    assert validated["ok"] is False
    assert validated["error_code"] == ErrorCode.VALIDATION_ERROR
    assert validated["error_code"] not in FORBIDDEN_GENERIC_CODES
    assert (validated.get("message") or "").strip()
    samples.append(("validation", validated["error_code"], validated["message"]))

    smuggled = manage_incident_ticket(
        action="update",
        ticket_id="BRS-000001",
        status="CERRADO",
        description="not allowed on update",
    )
    assert smuggled["error_code"] == ErrorCode.VALIDATION_ERROR
    samples.append(("validation", smuggled["error_code"], smuggled["message"]))

    # Pairwise: different categories ⇒ different codes AND different messages.
    by_cat: dict[str, list[tuple[str, str]]] = {}
    for category, code, message in samples:
        by_cat.setdefault(category, []).append((code, message))
    assert set(by_cat) == {"authentication", "authorization", "validation"}

    pairs = [
        ("authentication", "authorization"),
        ("authentication", "validation"),
        ("authorization", "validation"),
    ]
    for left, right in pairs:
        for l_code, l_msg in by_cat[left]:
            for r_code, r_msg in by_cat[right]:
                assert l_code != r_code, (left, l_code, right, r_code)
                assert l_msg != r_msg, (left, l_msg, right, r_msg)


def test_transport_auth_failures_map_to_catalog_codes(mcp_base: str) -> None:
    from mcps.company_tools.errors import map_transport_oauth_error

    missing = httpx.post(
        f"{mcp_base}/mcp",
        headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        timeout=5.0,
    )
    assert missing.status_code == 401
    body = missing.json()
    assert body.get("error") != "error"
    assert map_transport_oauth_error(body.get("error")) == ErrorCode.AUTH_MISSING_TOKEN

    invalid = httpx.post(
        f"{mcp_base}/mcp",
        headers={
            "Authorization": "Bearer not-a-jwt",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        timeout=5.0,
    )
    assert invalid.status_code == 401
    inv_body = invalid.json()
    assert inv_body.get("error") == "invalid_token"
    assert map_transport_oauth_error(inv_body.get("error")) == ErrorCode.AUTH_INVALID_TOKEN


def test_every_tool_invocation_is_logged_with_tool_client_and_result(caplog, mcp_base: str) -> None:
    """Traceability: each tools/call emits tool + client_id + result."""
    import json
    import logging

    from mcps.company_tools.logging_util import INVOCATION_LOGGER_NAME

    token = mint_access_token(
        audience="http://127.0.0.1:13001/mcp",
        scopes="incidents:manage inventory:read",
        client_id="trace-client",
    )
    with caplog.at_level(logging.INFO, logger=INVOCATION_LOGGER_NAME):
        ok_resp, ok_body = _mcp_rpc(
            mcp_base,
            token,
            "tools/call",
            {
                "name": "manage_incident_ticket",
                "arguments": {
                    "action": "create",
                    "category": "EQUIPAMIENTO",
                    "description": "Logged invocation for traceability",
                },
            },
            request_id=1,
        )
        assert ok_resp.status_code == 200
        create_tool = json.loads(ok_body["result"]["content"][0]["text"])
        assert create_tool["ok"] is True

        denied_resp, denied_body = _mcp_rpc(
            mcp_base,
            mint_access_token(
                audience="http://127.0.0.1:13001/mcp",
                scopes="inventory:read",
                client_id="inv-logger",
            ),
            "tools/call",
            {
                "name": "manage_incident_ticket",
                "arguments": {"action": "get_status", "ticket_id": "BRS-000001"},
            },
            request_id=2,
        )
        assert denied_resp.status_code == 200
        denied_tool = json.loads(denied_body["result"]["content"][0]["text"])
        assert denied_tool["error_code"] == ErrorCode.AUTH_INSUFFICIENT_SCOPE

    entries = []
    for record in caplog.records:
        if record.name != INVOCATION_LOGGER_NAME:
            continue
        try:
            entries.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            continue

    assert entries, "expected at least one tool_invocation log line"
    for entry in entries:
        assert entry.get("event") == "tool_invocation"
        assert entry.get("tool") in {"manage_incident_ticket", "query_inventory"}
        assert entry.get("client_id")
        assert entry.get("result") in {"success", "error"}
        if entry["result"] == "error":
            assert entry.get("error_code")
            assert entry["error_code"] != "error"

    success = [e for e in entries if e["tool"] == "manage_incident_ticket" and e["result"] == "success"]
    assert success
    assert success[0]["client_id"] == "trace-client"

    authz = [
        e
        for e in entries
        if e.get("error_code") == ErrorCode.AUTH_INSUFFICIENT_SCOPE and e["client_id"] == "inv-logger"
    ]
    assert authz


def test_timed_call_always_logs_tool_client_result(caplog) -> None:
    import json
    import logging
    from types import SimpleNamespace

    from mcps.company_tools.logging_util import INVOCATION_LOGGER_NAME, timed_call

    class _Auth:
        auth_info = SimpleNamespace(client_id="unit-client", subject="sub-1", scopes=["inventory:read"])

    with caplog.at_level(logging.INFO, logger=INVOCATION_LOGGER_NAME):
        out = timed_call(
            tool="query_inventory",
            mcp_auth=_Auth(),  # type: ignore[arg-type]
            input_summary={"action": "list"},
            fn=lambda: {"ok": True, "products": [{"product_id": "1"}]},
        )
    assert out["ok"] is True
    logged = [json.loads(r.getMessage()) for r in caplog.records if r.name == INVOCATION_LOGGER_NAME]
    assert len(logged) == 1
    entry = logged[0]
    assert entry["tool"] == "query_inventory"
    assert entry["client_id"] == "unit-client"
    assert entry["result"] == "success"
    assert entry["result_summary"]["product_count"] == 1
