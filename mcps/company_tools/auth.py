"""MCP Auth (mcpauth) wiring — OAuth 2.1 resource-server mode.

Uses MCP Auth for Protected Resource Metadata + bearer JWT validation.
Do **not** use FastMCP's built-in auth helpers for this project.
"""

from __future__ import annotations

import os
from functools import lru_cache

from mcpauth import MCPAuth
from mcpauth.config import AuthServerType
from mcpauth.types import ResourceServerConfig, ResourceServerMetadata
from mcpauth.utils import fetch_server_config

# Scopes — least privilege per tool family.
SCOPE_INCIDENTS_MANAGE = "incidents:manage"
SCOPE_INVENTORY_READ = "inventory:read"
ALL_SCOPES = [SCOPE_INCIDENTS_MANAGE, SCOPE_INVENTORY_READ]

DEFAULT_RESOURCE = "http://127.0.0.1:3001/mcp"
DEFAULT_ISSUER = "http://127.0.0.1:3002"


def resource_indicator() -> str:
    return os.getenv("MCP_RESOURCE_ID") or DEFAULT_RESOURCE


def issuer_url() -> str:
    return (os.getenv("MCP_AUTH_ISSUER") or DEFAULT_ISSUER).rstrip("/")


@lru_cache(maxsize=1)
def build_mcp_auth() -> MCPAuth:
    """Fetch OIDC metadata and build MCPAuth in resource-server mode."""
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
                        "MCP server exposing Incidents Manager ticket management "
                        "and read-only inventory queries for authorized clients."
                    ),
                )
            )
        ]
    )


def clear_auth_cache() -> None:
    build_mcp_auth.cache_clear()
