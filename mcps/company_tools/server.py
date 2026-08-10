"""Brasaland company-tools MCP server (Streamable HTTP + MCP Auth).

Transport choice
----------------
**Streamable HTTP** — the RFP requires remote MCP clients (Playground, other
teams, partners). stdio would only work when a single local process spawns the
server; HTTP lets multiple authenticated clients share one OAuth-protected
resource server. MCP Auth bearer middleware + Protected Resource Metadata run
on the HTTP app.
"""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcpauth.exceptions import BearerAuthExceptionCode, MCPAuthBearerAuthException
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Mount

from mcps.company_tools.auth import (
    SCOPE_INCIDENTS_MANAGE,
    SCOPE_INVENTORY_READ,
    build_mcp_auth,
    resource_indicator,
)
from mcps.company_tools.errors import ErrorCode, error_payload
from mcps.company_tools.logging_util import timed_call
from mcps.company_tools.tools.incidents import manage_incident_ticket
from mcps.company_tools.tools.inventory import query_inventory

logging.basicConfig(level=logging.INFO, format="%(message)s")


def _build_transport_security() -> TransportSecuritySettings:
    """Allow localhost + optional public Host values (Codespaces / Cloudflare).

    The MCP SDK only supports exact Host matches or ``host:*`` port wildcards —
    not ``*.domain`` patterns — so public tunnel hosts must be listed explicitly
    via ``MCP_RESOURCE_ID`` / ``MCP_ALLOWED_HOSTS``.
    """
    if os.getenv("MCP_DISABLE_DNS_REBINDING", "").strip().lower() in {"1", "true", "yes"}:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)

    hosts = [
        "127.0.0.1",
        "127.0.0.1:*",
        "localhost",
        "localhost:*",
        "[::1]",
        "[::1]:*",
    ]
    origins = [
        "http://127.0.0.1",
        "http://127.0.0.1:*",
        "http://localhost",
        "http://localhost:*",
        "https://www.mcpplayground.tech",
        "https://mcpplayground.tech",
    ]

    resource = os.getenv("MCP_RESOURCE_ID") or ""
    if "://" in resource:
        # https://host[:port]/path → host[:port]
        hostport = resource.split("://", 1)[1].split("/", 1)[0]
        if hostport and hostport not in hosts:
            hosts.append(hostport)
        if resource.startswith("https://"):
            origins.append(f"https://{hostport}")
        elif resource.startswith("http://"):
            origins.append(f"http://{hostport}")

    for raw in (os.getenv("MCP_ALLOWED_HOSTS") or "").split(","):
        host = raw.strip()
        if host and host not in hosts:
            hosts.append(host)

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


mcp = FastMCP(
    name="Brasaland Company Tools",
    stateless_http=True,
    transport_security=_build_transport_security(),
)
mcp_auth = None  # set in create_app() so issuer can start first


def _require_scopes(required: list[str]) -> None:
    auth = build_mcp_auth().auth_info
    if auth is None:
        raise MCPAuthBearerAuthException(BearerAuthExceptionCode.MISSING_AUTH_HEADER)
    missing = [scope for scope in required if scope not in (auth.scopes or [])]
    if missing:
        raise MCPAuthBearerAuthException(BearerAuthExceptionCode.MISSING_REQUIRED_SCOPES)


@mcp.tool(
    name="manage_incident_ticket",
    description=(
        "Create, update status, or query an incident ticket in the Brasaland "
        "Incidents Manager. "
        "Actions: create | update | get_status. "
        "Status updates always call PATCH /api/incidents/{id}/status (lifecycle). "
        "Requires OAuth scope incidents:manage. "
        "Fields match the live API (incident_id, category, description, status, …)."
    ),
)
def tool_manage_incident_ticket(
    action: str,
    ticket_id: str | None = None,
    category: str | None = None,
    description: str | None = None,
    status: str | None = None,
    date: str | None = None,
    location_id: str | None = None,
    customer_id: str | None = None,
    reporter_id: str | None = None,
) -> dict[str, Any]:
    """MCP tool: manage Incidents Manager tickets."""
    auth = build_mcp_auth()

    def _run() -> dict[str, Any]:
        try:
            _require_scopes([SCOPE_INCIDENTS_MANAGE])
        except MCPAuthBearerAuthException:
            return error_payload(
                ErrorCode.AUTH_INSUFFICIENT_SCOPE,
                f"Missing required scope: {SCOPE_INCIDENTS_MANAGE}",
                tool="manage_incident_ticket",
            )
        if action not in {"create", "update", "get_status"}:
            return error_payload(
                ErrorCode.VALIDATION_ERROR,
                "action must be one of: create, update, get_status",
                tool="manage_incident_ticket",
            )
        return manage_incident_ticket(
            action=action,  # type: ignore[arg-type]
            ticket_id=ticket_id,
            category=category,
            description=description,
            status=status,
            date=date,
            location_id=location_id,
            customer_id=customer_id,
            reporter_id=reporter_id,
        )

    return timed_call(
        tool="manage_incident_ticket",
        mcp_auth=auth,
        input_summary={"action": action, "ticket_id": ticket_id},
        fn=_run,
    )


@mcp.tool(
    name="query_inventory",
    description=(
        "Read-only lookup of Brasaland inventory products/stock from the live "
        "inventory manager (products.csv-backed GET /inventory/products). "
        "Write operations are not supported and are rejected with "
        "INVENTORY_WRITE_FORBIDDEN. Requires OAuth scope inventory:read. "
        "Filter with product_id or name_contains."
    ),
)
def tool_query_inventory(
    action: str | None = "query",
    product_id: str | None = None,
    name_contains: str | None = None,
    quantity: int | None = None,
    delta: int | None = None,
    unit: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """MCP tool: read-only inventory queries."""
    auth = build_mcp_auth()

    def _run() -> dict[str, Any]:
        try:
            _require_scopes([SCOPE_INVENTORY_READ])
        except MCPAuthBearerAuthException:
            return error_payload(
                ErrorCode.AUTH_INSUFFICIENT_SCOPE,
                f"Missing required scope: {SCOPE_INVENTORY_READ}",
                tool="query_inventory",
            )
        return query_inventory(
            action=action,
            product_id=product_id,
            name_contains=name_contains,
            quantity=quantity,
            delta=delta,
            unit=unit,
            name=name,
        )

    return timed_call(
        tool="query_inventory",
        mcp_auth=auth,
        input_summary={
            "action": action,
            "product_id": product_id,
            "name_contains": name_contains,
        },
        fn=_run,
    )


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session_manager.run())
        yield


def create_app() -> Starlette:
    """Build the Streamable HTTP Starlette app with MCP Auth middleware."""
    auth = build_mcp_auth()
    resource = resource_indicator()
    bearer_auth = Middleware(
        auth.bearer_auth_middleware(
            "jwt",
            resource=resource,
            audience=resource,
            required_scopes=None,  # per-tool scopes enforced inside tools
            show_error_details=True,
        )
    )
    return Starlette(
        routes=[
            *auth.resource_metadata_router().routes,
            Mount("/", app=mcp.streamable_http_app(), middleware=[bearer_auth]),
        ],
        lifespan=lifespan,
    )


# ASGI entrypoint for uvicorn: mcps.company_tools.server:app
app = None


def get_app() -> Starlette:
    global app
    if app is None:
        app = create_app()
    return app


def main() -> None:
    import uvicorn

    # Build app after issuer is expected to be reachable.
    asgi = create_app()
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "3001"))
    uvicorn.run(asgi, host=host, port=port)


if __name__ == "__main__":
    main()
