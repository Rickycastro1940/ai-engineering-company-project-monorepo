"""HTTP clients for the live Incidents Manager and Inventory APIs.

These helpers are the **only** data path used by MCP tools. They talk to the
existing company FastAPI service over HTTP — they do not import
``incidents_store`` / ``inventory`` modules or read CSVs directly.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_API_BASE = "http://127.0.0.1:8000"
HTTP_TIMEOUT_SECONDS = 5.0

# Paths owned by services/api — keep in sync with the Incidents Manager + inventory routers.
INCIDENTS_COLLECTION_PATH = "/api/incidents"
INCIDENT_BY_ID_PATH = "/api/incidents/{incident_id}"
INCIDENT_STATUS_PATH = "/api/incidents/{incident_id}/status"
PRODUCTS_COLLECTION_PATH = "/inventory/products"
PRODUCT_BY_ID_PATH = "/inventory/products/{product_id}"


def api_base() -> str:
    return (
        os.getenv("COMPANY_API_BASE")
        or os.getenv("INCIDENT_API_BASE")
        or DEFAULT_API_BASE
    ).rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    token = os.getenv("INCIDENT_API_TOKEN") or os.getenv("INCIDENT_API_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def build_timeout(seconds: float = HTTP_TIMEOUT_SECONDS) -> httpx.Timeout:
    limit = float(seconds)
    return httpx.Timeout(limit, connect=limit, read=limit, write=limit, pool=limit)


def get_incident(ticket_id: str, *, base_url: str | None = None) -> httpx.Response:
    root = (base_url or api_base()).rstrip("/")
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=_headers()) as client:
        return client.get(INCIDENT_BY_ID_PATH.format(incident_id=ticket_id))


def create_incident(payload: dict[str, Any], *, base_url: str | None = None) -> httpx.Response:
    root = (base_url or api_base()).rstrip("/")
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=_headers()) as client:
        return client.post(INCIDENTS_COLLECTION_PATH, json=payload)


def update_incident_status(
    ticket_id: str,
    status: str,
    *,
    base_url: str | None = None,
) -> httpx.Response:
    """Status changes MUST use the lifecycle endpoint, not a generic PATCH."""
    root = (base_url or api_base()).rstrip("/")
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=_headers()) as client:
        return client.patch(
            INCIDENT_STATUS_PATH.format(incident_id=ticket_id),
            json={"status": status},
        )


def list_products(
    *,
    product_id: str | None = None,
    name_contains: str | None = None,
    base_url: str | None = None,
) -> httpx.Response:
    root = (base_url or api_base()).rstrip("/")
    params: dict[str, str] = {}
    if product_id:
        params["product_id"] = product_id
    if name_contains:
        params["name"] = name_contains
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=_headers()) as client:
        return client.get(PRODUCTS_COLLECTION_PATH, params=params or None)


def get_product(product_id: str, *, base_url: str | None = None) -> httpx.Response:
    root = (base_url or api_base()).rstrip("/")
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=_headers()) as client:
        return client.get(PRODUCT_BY_ID_PATH.format(product_id=product_id))
