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
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Mount

from mcps.company_tools.auth import (
    SCOPE_INCIDENTS_MANAGE,
    SCOPE_INCIDENTS_READ,
    SCOPE_INVENTORY_READ,
    TOOL_REQUIRED_SCOPES,
    TOOL_SCOPE_ANY_OF,
    build_mcp_auth,
    has_any_scope,
    has_required_scopes,
    resource_indicator,
)
from mcps.company_tools.errors import ErrorCode, ExitCode, error_payload
from mcps.company_tools.logging_util import timed_call
from mcps.company_tools.schemas import ManageIncidentTicketOutput, QueryInventoryOutput
from mcps.company_tools.tools.incidents import manage_incident_ticket
from mcps.company_tools.tools.inventory import query_inventory

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("mcps.company_tools.server")


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
    # Intentionally NO FastMCP AuthSettings — OAuth is MCP Auth (mcpauth) only.
)
assert getattr(mcp, "settings", None) is None or mcp.settings.auth is None, (
    "FastMCP built-in auth must stay disabled; use mcpauth resource-server mode."
)


def _auth_gate(
    *,
    tool: str,
    required_scopes: list[str] | None = None,
    any_of_scopes: list[str] | None = None,
) -> dict[str, Any] | None:
    """Enforce least-privilege ``required_scopes`` (MCP Auth semantics).

    Transport-level MCP Auth middleware already rejects missing/invalid JWTs
    with HTTP 401. This gate applies per-tool ``required_scopes`` so each tool
    only runs when the token carries the scopes it needs.
    """
    auth = build_mcp_auth().auth_info
    if auth is None:
        return error_payload(
            ErrorCode.AUTH_MISSING_TOKEN,
            "Missing authenticated Bearer context. Present a valid OAuth access token.",
            tool=tool,
        )
    present = list(auth.scopes or [])
    if required_scopes:
        if not has_required_scopes(present, required_scopes):
            missing = [s for s in required_scopes if s not in set(present)]
            return error_payload(
                ErrorCode.AUTH_INSUFFICIENT_SCOPE,
                f"Missing required_scopes: {', '.join(missing)}",
                tool=tool,
                details={
                    "required_scopes": required_scopes,
                    "present": sorted(set(present)),
                    "missing": missing,
                },
            )
    if any_of_scopes:
        if not has_any_scope(present, any_of_scopes):
            return error_payload(
                ErrorCode.AUTH_INSUFFICIENT_SCOPE,
                f"Token needs one of required_scopes: {', '.join(any_of_scopes)}",
                tool=tool,
                details={
                    "required_scopes_any_of": any_of_scopes,
                    "present": sorted(set(present)),
                },
            )
    return None


@mcp.tool(
    name="manage_incident_ticket",
    title="Manage Brasaland incident tickets",
    description=(
        "Create, update status, or query an incident ticket in the Brasaland "
        "Incidents Manager (live HTTP API — not a mock). "
        "Actions: create | update | get_status. "
        "create requires category+description; update requires ticket_id+status and "
        "always calls PATCH /api/incidents/{id}/status (lifecycle only); "
        "get_status requires ticket_id. "
        "Statuses: ABIERTO | CERRADO | DESCARTADO. "
        "On success returns {ok:true, action, ticket:{incident_id,status,…}}. "
        "On failure returns {ok:false, error_code, message} with distinct codes "
        "(never a generic 'error'): AUTH_INSUFFICIENT_SCOPE, VALIDATION_ERROR, "
        "NOT_FOUND, LIFECYCLE_ERROR, UPSTREAM_ERROR — see ERRORS.md. "
        "Requires OAuth Bearer token with required_scopes incidents:manage "
        "(create/update) or incidents:read (get_status; manage also allowed)."
    ),
    structured_output=True,
)
def tool_manage_incident_ticket(
    action: Annotated[
        Literal["create", "update", "get_status"],
        Field(
            description=(
                "create: open a new ticket (needs category+description). "
                "update: change status via PATCH /api/incidents/{id}/status (needs ticket_id+status). "
                "get_status: look up one ticket (needs ticket_id)."
            )
        ),
    ],
    ticket_id: Annotated[
        str | None,
        Field(description="Required for update and get_status. Example: BRS-000002."),
    ] = None,
    category: Annotated[
        str | None,
        Field(
            description=(
                "Required for create. Categories from Incidents Manager: "
                "EQUIPAMIENTO | ABASTECIMIENTO | QUEJA_CLIENTE | CALIDAD_ALIMENTO | PERSONAL."
            )
        ),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="Required for create. Short description of the incident."),
    ] = None,
    status: Annotated[
        str | None,
        Field(
            description=(
                "For create: initial status (default ABIERTO). "
                "For update: target status only — ABIERTO | CERRADO | DESCARTADO. "
                "update always calls PATCH /api/incidents/{id}/status."
            )
        ),
    ] = None,
    date: Annotated[
        str | None,
        Field(description="Optional ISO date for create (YYYY-MM-DD)."),
    ] = None,
    location_id: Annotated[
        str | None,
        Field(description="Optional location id for create (e.g. COL-01, FLA-02)."),
    ] = None,
    customer_id: Annotated[
        str | None,
        Field(description="Optional customer id for create."),
    ] = None,
    satisfaction_score: Annotated[
        float | None,
        Field(description="Optional satisfaction score for create (IncidentCreateInput field)."),
    ] = None,
    reporter_id: Annotated[
        str | None,
        Field(description="Optional reporter id for create."),
    ] = None,
) -> ManageIncidentTicketOutput:
    """MCP discovery entry for Incidents Manager ticket management."""
    auth = build_mcp_auth()

    def _run() -> dict[str, Any]:
        # Least privilege: get_status needs read (or manage); writes need manage.
        key = f"manage_incident_ticket:{action}"
        any_of = TOOL_SCOPE_ANY_OF.get(key)
        denied = _auth_gate(
            tool="manage_incident_ticket",
            required_scopes=None if any_of else [SCOPE_INCIDENTS_MANAGE],
            any_of_scopes=any_of,
        )
        if denied is not None:
            return denied
        return manage_incident_ticket(
            action=action,
            ticket_id=ticket_id,
            category=category,
            description=description,
            status=status,
            date=date,
            location_id=location_id,
            customer_id=customer_id,
            satisfaction_score=satisfaction_score,
            reporter_id=reporter_id,
        )

    payload = timed_call(
        tool="manage_incident_ticket",
        mcp_auth=auth,
        input_summary={
            "action": action,
            "ticket_id": ticket_id,
            "category": category,
            "status": status,
        },
        fn=_run,
    )
    return ManageIncidentTicketOutput.model_validate(payload)


@mcp.tool(
    name="query_inventory",
    title="Query Brasaland inventory (read-only)",
    description=(
        "Read-only lookup of Brasaland inventory products/stock from the live "
        "inventory manager (GET /inventory/products — products.csv-backed). "
        "Use product_id for one product or name_contains to filter by name. "
        "Allowed actions: query | get | list | read. "
        "Write operations are NOT supported: any action of update/create/delete/"
        "write/patch/put OR any non-empty quantity/delta/unit/name field is "
        "explicitly rejected with error_code INVENTORY_WRITE_FORBIDDEN "
        "(the write tool is not omitted — it fails with a clear code). "
        "On success returns {ok:true, products:[{product_id,name,quantity,unit,source}]}. "
        "Requires OAuth Bearer token with required_scopes=[inventory:read]."
    ),
    structured_output=True,
)
def tool_query_inventory(
    action: Annotated[
        str | None,
        Field(
            description=(
                "Read-only action. Allowed: query | get | list | read (default query). "
                "Write-oriented values (update, create, delete, write, patch, put) "
                "are rejected with INVENTORY_WRITE_FORBIDDEN."
            )
        ),
    ] = "query",
    product_id: Annotated[
        str | None,
        Field(description="Optional product id from products.csv (e.g. '1')."),
    ] = None,
    name_contains: Annotated[
        str | None,
        Field(description="Optional case-insensitive name substring filter."),
    ] = None,
    quantity: Annotated[
        int | None,
        Field(
            description="WRITE FIELD — not permitted. Any value triggers INVENTORY_WRITE_FORBIDDEN."
        ),
    ] = None,
    delta: Annotated[
        int | None,
        Field(
            description="WRITE FIELD — not permitted. Any value triggers INVENTORY_WRITE_FORBIDDEN."
        ),
    ] = None,
    unit: Annotated[
        str | None,
        Field(
            description="WRITE FIELD — not permitted. Non-empty value triggers INVENTORY_WRITE_FORBIDDEN."
        ),
    ] = None,
    name: Annotated[
        str | None,
        Field(
            description=(
                "WRITE FIELD for create/rename — not permitted. "
                "Use name_contains to filter reads instead."
            )
        ),
    ] = None,
) -> QueryInventoryOutput:
    """MCP discovery entry for read-only inventory queries."""
    auth = build_mcp_auth()

    def _run() -> dict[str, Any]:
        denied = _auth_gate(
            tool="query_inventory",
            required_scopes=TOOL_REQUIRED_SCOPES["query_inventory"],
        )
        if denied is not None:
            return denied
        return query_inventory(
            action=action,
            product_id=product_id,
            name_contains=name_contains,
            quantity=quantity,
            delta=delta,
            unit=unit,
            name=name,
        )

    payload = timed_call(
        tool="query_inventory",
        mcp_auth=auth,
        input_summary={
            "action": action,
            "product_id": product_id,
            "name_contains": name_contains,
        },
        fn=_run,
    )
    return QueryInventoryOutput.model_validate(payload)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session_manager.run())
        yield


def create_app() -> Starlette:
    """Build Streamable HTTP app with mandatory MCP Auth (resource-server mode).

    Protection model
    ----------------
    1. ``resource_metadata_router`` — public OAuth Protected Resource Metadata
       (RFC 9728) so clients discover the OIDC issuer + scopes.
    2. ``bearer_auth_middleware("jwt", ...)`` wraps **all** ``/mcp`` traffic.
       Missing / invalid / wrong-audience tokens → HTTP 401
       (``AUTH_MISSING_TOKEN`` / ``AUTH_INVALID_TOKEN``). No anonymous
       ``tools/list`` or ``tools/call``.
    3. Per-tool ``required_scopes`` (least privilege):
       ``incidents:read`` / ``incidents:manage`` / ``inventory:read``
       → ``AUTH_INSUFFICIENT_SCOPE`` when missing.

    FastMCP built-in auth is intentionally unused (``settings.auth is None``).
    Middleware ``required_scopes`` stays unset at the transport layer so a
    read-only inventory token can still open an MCP session; tool gates apply
    the precise ``required_scopes`` for each operation.

    See ``ERRORS.md`` for the full error / exit code catalog.
    """
    try:
        auth = build_mcp_auth()
    except Exception as exc:  # noqa: BLE001 — surface as auth setup failure
        logger.error("AUTH_SETUP_ERROR: failed to init MCP Auth from OIDC issuer: %s", exc)
        raise SystemExit(int(ExitCode.AUTH_SETUP_ERROR)) from exc

    resource = resource_indicator()
    if "://" not in resource:
        logger.error("CONFIG_ERROR: MCP_RESOURCE_ID must be an absolute URL, got %r", resource)
        raise SystemExit(int(ExitCode.CONFIG_ERROR))

    if mcp.settings.auth is not None:
        logger.error(
            "CONFIG_ERROR: FastMCP built-in auth is set; use mcpauth resource-server mode only."
        )
        raise SystemExit(int(ExitCode.CONFIG_ERROR))

    bearer_auth = Middleware(
        auth.bearer_auth_middleware(
            "jwt",
            resource=resource,
            audience=resource,  # aud must equal resource indicator
            # Transport gate = valid JWT. Per-tool required_scopes in _auth_gate.
            required_scopes=None,
            show_error_details=True,
        )
    )
    logger.info(
        "MCP Auth resource-server enabled resource=%s scopes=%s",
        resource,
        [SCOPE_INCIDENTS_READ, SCOPE_INCIDENTS_MANAGE, SCOPE_INVENTORY_READ],
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

    try:
        asgi = create_app()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("UNEXPECTED startup failure: %s", exc)
        raise SystemExit(int(ExitCode.UNEXPECTED)) from exc

    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "3001"))
    uvicorn.run(asgi, host=host, port=port)


if __name__ == "__main__":
    main()
