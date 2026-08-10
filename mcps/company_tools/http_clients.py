"""HTTP clients for the live Incidents Manager and Inventory APIs."""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_API_BASE = "http://127.0.0.1:8000"
HTTP_TIMEOUT_SECONDS = 5.0


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
        return client.get(f"/api/incidents/{ticket_id}")


def create_incident(payload: dict[str, Any], *, base_url: str | None = None) -> httpx.Response:
    root = (base_url or api_base()).rstrip("/")
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=_headers()) as client:
        return client.post("/api/incidents", json=payload)


def update_incident_status(
    ticket_id: str,
    status: str,
    *,
    base_url: str | None = None,
) -> httpx.Response:
    """Status changes MUST use the lifecycle endpoint, not a generic PATCH."""
    root = (base_url or api_base()).rstrip("/")
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=_headers()) as client:
        return client.patch(f"/api/incidents/{ticket_id}/status", json={"status": status})


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
        return client.get("/inventory/products", params=params or None)


def get_product(product_id: str, *, base_url: str | None = None) -> httpx.Response:
    root = (base_url or api_base()).rstrip("/")
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=_headers()) as client:
        return client.get(f"/inventory/products/{product_id}")
