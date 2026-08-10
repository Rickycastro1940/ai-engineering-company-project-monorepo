"""MCP Auth (mcpauth) — OAuth 2.1 / OIDC **resource-server** mode.

Mandatory for this project
--------------------------
Company tools must never be listable or invokable without a valid Bearer access
token. Prefer **MCP Auth** (``mcpauth``) over FastMCP's built-in auth so the
flow matches the MCP Authorization spec (Protected Resource Metadata + bearer
JWT validation).

Least privilege (scopes)
------------------------
Each tool declares ``required_scopes`` for the operations it performs:

* ``incidents:read`` — ``manage_incident_ticket`` action ``get_status``
* ``incidents:manage`` — ``manage_incident_ticket`` actions ``create`` / ``update``
  (also satisfies read)
* ``inventory:read`` — ``query_inventory`` (read-only; no write scope exists)

Design
------
* **Resource server mode** — this MCP process validates tokens; it does not
  host the authorization server.
* **Provider-agnostic OIDC** — set ``MCP_AUTH_ISSUER`` to any OIDC issuer
  (Logto, Auth0, Keycloak, Cognito, or the local ``dev_issuer``).
"""

from __future__ import annotations

import os
from functools import lru_cache

from mcpauth import MCPAuth
from mcpauth.config import AuthServerType
from mcpauth.types import ResourceServerConfig, ResourceServerMetadata
from mcpauth.utils import fetch_server_config

# Least-privilege scopes — advertised in PRM and enforced via required_scopes.
SCOPE_INCIDENTS_READ = "incidents:read"
SCOPE_INCIDENTS_MANAGE = "incidents:manage"
SCOPE_INVENTORY_READ = "inventory:read"
ALL_SCOPES = [SCOPE_INCIDENTS_READ, SCOPE_INCIDENTS_MANAGE, SCOPE_INVENTORY_READ]

# Tool → required_scopes (all must be present). Manage implies read for get_status
# via TOOL_SCOPE_ANY_OF below.
TOOL_REQUIRED_SCOPES: dict[str, list[str]] = {
    "query_inventory": [SCOPE_INVENTORY_READ],
}

# For get_status, either read or manage is enough (manage ⊇ read).
TOOL_SCOPE_ANY_OF: dict[str, list[str]] = {
    "manage_incident_ticket:get_status": [SCOPE_INCIDENTS_READ, SCOPE_INCIDENTS_MANAGE],
    "manage_incident_ticket:create": [SCOPE_INCIDENTS_MANAGE],
    "manage_incident_ticket:update": [SCOPE_INCIDENTS_MANAGE],
}

DEFAULT_RESOURCE = "http://127.0.0.1:3001/mcp"
DEFAULT_ISSUER = "http://127.0.0.1:3002"


def resource_indicator() -> str:
    """Canonical resource identifier (also used as JWT ``aud``)."""
    return os.getenv("MCP_RESOURCE_ID") or DEFAULT_RESOURCE


def issuer_url() -> str:
    """OIDC issuer base URL — provider-agnostic (Logto / Auth0 / local stub)."""
    return (os.getenv("MCP_AUTH_ISSUER") or DEFAULT_ISSUER).rstrip("/")


@lru_cache(maxsize=1)
def build_mcp_auth() -> MCPAuth:
    """Build MCPAuth in **resource-server** mode from OIDC issuer metadata.

    Do **not** use FastMCP ``AuthSettings`` / built-in auth here.
    """
    auth_server_config = fetch_server_config(issuer_url(), type=AuthServerType.OIDC)
    resource = resource_indicator()
    return MCPAuth(
        protected_resources=[
            ResourceServerConfig(
                metadata=ResourceServerMetadata(
                    resource=resource,
                    authorization_servers=[auth_server_config],
                    scopes_supported=ALL_SCOPES,
                    resource_name="Brasaland Company Tools",
                    resource_documentation=(
                        "OAuth-protected MCP resource server (least privilege). "
                        "Scopes: incidents:read (get_status), incidents:manage "
                        "(create/update status), inventory:read (query only)."
                    ),
                )
            )
        ]
    )


def clear_auth_cache() -> None:
    build_mcp_auth.cache_clear()


def has_required_scopes(present: list[str] | set[str], required_scopes: list[str]) -> bool:
    """True when every scope in ``required_scopes`` is present (MCP Auth semantics)."""
    have = set(present or [])
    return all(scope in have for scope in required_scopes)


def has_any_scope(present: list[str] | set[str], any_of: list[str]) -> bool:
    """True when at least one scope in ``any_of`` is present."""
    have = set(present or [])
    return any(scope in have for scope in any_of)
