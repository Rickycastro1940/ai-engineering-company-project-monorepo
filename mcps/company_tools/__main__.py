"""ASGI app factory — start the local OIDC issuer before importing if needed.

Usage::

    # Terminal A — local OIDC issuer (dev/tests)
    uv run uvicorn mcps.company_tools.dev_issuer:app --port 3002

    # Terminal B — MCP server (Streamable HTTP + MCP Auth)
    uv run uvicorn mcps.company_tools.server:create_app --factory --port 3001
"""

from mcps.company_tools.server import create_app, main

__all__ = ["create_app", "main"]
