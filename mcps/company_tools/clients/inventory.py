"""Least-privilege HTTP client for inventory reads only.

Exposes only ``GET /inventory/products`` and ``GET /inventory/products/{id}``.
No write methods (POST/PATCH/PUT/DELETE) exist in this module.
"""

from __future__ import annotations

import httpx

from mcps.company_tools.clients.base import api_base, build_timeout, json_headers

PRODUCTS_COLLECTION_PATH = "/inventory/products"
PRODUCT_BY_ID_PATH = "/inventory/products/{product_id}"


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
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=json_headers()) as client:
        return client.get(PRODUCTS_COLLECTION_PATH, params=params or None)


def get_product(product_id: str, *, base_url: str | None = None) -> httpx.Response:
    root = (base_url or api_base()).rstrip("/")
    with httpx.Client(base_url=root, timeout=build_timeout(), headers=json_headers()) as client:
        return client.get(PRODUCT_BY_ID_PATH.format(product_id=product_id))
