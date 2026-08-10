"""Local OIDC / OAuth 2.1 issuer for development and automated tests.

Production deployments should point ``MCP_AUTH_ISSUER`` at a real provider
(Logto, Auth0, etc.). This stub exists so the monorepo can validate MCP Auth
JWT + JWKS flows without an external SaaS dependency.
"""

from __future__ import annotations

import os
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

ISSUER_DEFAULT = "http://127.0.0.1:3002"
DEFAULT_AUDIENCE = "http://127.0.0.1:3001/mcp"
DEFAULT_SCOPES = "incidents:manage inventory:read"


def _issuer() -> str:
    return (os.getenv("MCP_AUTH_ISSUER") or ISSUER_DEFAULT).rstrip("/")


def _audience() -> str:
    return os.getenv("MCP_RESOURCE_ID") or DEFAULT_AUDIENCE

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_KID = "brasaland-dev-key-1"


def _public_jwk() -> dict[str, Any]:
    public_numbers = _PUBLIC_KEY.public_numbers()

    def _b64int(value: int) -> str:
        length = (value.bit_length() + 7) // 8
        return jwt.utils.base64url_encode(value.to_bytes(length, "big")).decode("ascii")

    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": _KID,
        "n": _b64int(public_numbers.n),
        "e": _b64int(public_numbers.e),
    }


def mint_access_token(
    *,
    subject: str = "agent-support",
    client_id: str = "agent-support-prod",
    scopes: str = DEFAULT_SCOPES,
    audience: str | None = None,
    expires_in: int = 3600,
) -> str:
    """Issue a signed JWT access token accepted by the MCP Auth middleware."""
    now = int(time.time())
    payload = {
        "iss": _issuer(),
        "sub": subject,
        "aud": audience or _audience(),
        "client_id": client_id,
        "scope": scopes,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(
        payload,
        _PRIVATE_KEY,
        algorithm="RS256",
        headers={"kid": _KID},
    )


async def openid_configuration(_: Request) -> JSONResponse:
    issuer = _issuer()
    return JSONResponse(
        {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/authorize",
            "token_endpoint": f"{issuer}/token",
            "jwks_uri": f"{issuer}/jwks",
            "response_types_supported": ["code", "token"],
            "grant_types_supported": ["client_credentials", "authorization_code"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
            "scopes_supported": [
                "incidents:manage",
                "inventory:read",
                "openid",
            ],
            "id_token_signing_alg_values_supported": ["RS256"],
            "subject_types_supported": ["public"],
        }
    )


async def jwks(_: Request) -> JSONResponse:
    return JSONResponse({"keys": [_public_jwk()]})


async def token(request: Request) -> JSONResponse:
    """Minimal token endpoint — issues a JWT for local MCP clients / tests."""
    if request.method == "POST":
        form = await request.form()
        # Respect an explicitly provided scope (including "") for auth tests.
        if "scope" in form:
            scopes = str(form.get("scope") or "")
        else:
            scopes = DEFAULT_SCOPES
        client_id = str(form.get("client_id") or "mcp-playground")
    else:
        if "scope" in request.query_params:
            scopes = request.query_params.get("scope") or ""
        else:
            scopes = DEFAULT_SCOPES
        client_id = request.query_params.get("client_id") or "mcp-playground"

    access_token = mint_access_token(
        client_id=client_id,
        scopes=scopes,
        audience=_audience(),
    )
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": scopes,
        }
    )


def create_issuer_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/.well-known/openid-configuration", openid_configuration, methods=["GET"]),
            Route("/jwks", jwks, methods=["GET"]),
            Route("/token", token, methods=["GET", "POST"]),
        ]
    )


app = create_issuer_app()


def main() -> None:
    import uvicorn

    host = os.getenv("MCP_ISSUER_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_ISSUER_PORT", "3002"))
    uvicorn.run("mcps.company-tools.dev_issuer:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
