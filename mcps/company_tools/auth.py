"""MCP Auth (mcpauth) — OAuth 2.1 / OIDC **resource-server** mode.

Mandatory for this project
--------------------------
Company tools must never be listable or invokable without a valid Bearer access
token. Prefer **MCP Auth** (``mcpauth``) over FastMCP's built-in auth so the
flow matches the MCP Authorization spec (Protected Resource Metadata + bearer
JWT validation).

Design
------
* **Resource server mode** — this MCP process validates tokens; it does not
  host the authorization server.
* **Provider-agnostic OIDC** — set ``MCP_AUTH_ISSUER`` to any OIDC issuer
  (Logto, Auth0, Keycloak, Cognito, or the local ``dev_issuer``). Metadata /
  JWKS are fetched via ``fetch_server_config(..., type=AuthServerType.OIDC)``.
* **Scopes** — ``incidents:manage`` and ``inventory:read`` are advertised in
  Protected Resource Metadata and enforced per tool after JWT validation.
"""

from __future__ import annotations

import os
from functools import lru_cache

from mcpauth import MCPAuth
from mcpauth.config import AuthServerType
from mcpauth.types import ResourceServerConfig, ResourceServerMetadata
from mcpauth.utils import fetch_server_config

# Scopes — least privilege per tool family (advertised + enforced).
SCOPE_INCIDENTS_MANAGE = "incidents:manage"
SCOPE_INVENTORY_READ = "inventory:read"
ALL_SCOPES = [SCOPE_INCIDENTS_MANAGE, SCOPE_INVENTORY_READ]

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
                        "OAuth-protected MCP resource server. Clients must present "
                        "a Bearer access token (OIDC JWT) with audience equal to "
                        "this resource and scopes incidents:manage / inventory:read "
                        "to list or invoke company tools."
                    ),
                )
            )
        ]
    )


def clear_auth_cache() -> None:
    build_mcp_auth.cache_clear()


def current_scopes() -> list[str]:
    """Scopes from the Bearer token validated by MCP Auth middleware (if any)."""
    info = build_mcp_auth().auth_info
    if info is None:
        return []
    return list(info.scopes or [])
