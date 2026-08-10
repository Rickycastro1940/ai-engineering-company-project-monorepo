"""Read-only inventory lookup tool — HTTP only against the live inventory manager.

Data source (non-negotiable)
---------------------------
This tool **only** issues:

- ``GET {base}/inventory/products``
- ``GET {base}/inventory/products/{id}``

against the company's existing inventory manager (``products.csv``-backed).
Never embeds product rows or invents quantities.

Timeout / fallback
------------------
Uses ``INVENTORY_LOOKUP_TIMEOUT_SECONDS`` (5s). On timeout / error / not-found
returns ``ok=False`` and the graph takes ``inventory_fallback`` — never a
made-up stock level.

Auth: inventory GETs require **no auth** today. Optional
``INVENTORY_API_TOKEN`` / ``INVENTORY_API_KEY`` are forwarded if set.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from services.agent.tools.contracts import (
    InventoryLookupInput,
    InventoryLookupOutput,
    InventoryProductRecord,
)

INVENTORY_LOOKUP_TIMEOUT_SECONDS: float = 5.0
DEFAULT_INVENTORY_API_BASE = "http://127.0.0.1:8000"

PRODUCTS_LIST_PATH = "/inventory/products"
PRODUCT_BY_ID_PATH_TEMPLATE = "/inventory/products/{product_id}"

INVENTORY_FALLBACK_MESSAGE = (
    "I couldn't confirm that product's stock right now. "
    "Please try again shortly or check the inventory manager directly."
)


def build_inventory_http_timeout(
    seconds: float = INVENTORY_LOOKUP_TIMEOUT_SECONDS,
) -> httpx.Timeout:
    limit = float(seconds)
    if limit <= 0:
        raise ValueError("inventory lookup timeout must be a positive number of seconds")
    return httpx.Timeout(limit, connect=limit, read=limit, write=limit, pool=limit)


def _inventory_api_base() -> str:
    return (
        os.getenv("INVENTORY_API_BASE")
        or os.getenv("INCIDENT_API_BASE")
        or DEFAULT_INVENTORY_API_BASE
    ).rstrip("/")


def _auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    token = os.getenv("INVENTORY_API_TOKEN") or os.getenv("INVENTORY_API_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _record_from_payload(payload: dict[str, Any]) -> InventoryProductRecord:
    return InventoryProductRecord(
        product_id=str(payload.get("product_id") or ""),
        name=str(payload.get("name") or ""),
        quantity=int(payload.get("quantity") or 0),
        unit=str(payload.get("unit") or "unit"),
        source=str(payload.get("source") or "inventory_manager"),
    )


def honest_inventory_fallback_answer(
    output: InventoryLookupOutput | None = None,
) -> str:
    """Canonical fallback — never invent a stock quantity."""
    base = INVENTORY_FALLBACK_MESSAGE
    if output is not None and output.message:
        text = output.message
        if "couldn't confirm" not in text.casefold():
            return f"{base} {text}"
        return text
    return base


def format_inventory_answer(output: InventoryLookupOutput) -> str:
    if not output.ok or not output.products:
        return honest_inventory_fallback_answer(output)
    lines: list[str] = []
    for product in output.products:
        lines.append(
            f"Product {product.product_id} ({product.name}): "
            f"quantity={product.quantity} {product.unit}, "
            f"source={product.source}."
        )
    return "\n".join(lines)


def _failed(started: float, *, error: str, message: str) -> InventoryLookupOutput:
    return InventoryLookupOutput(
        ok=False,
        products=[],
        error=error,  # type: ignore[arg-type]
        message=message,
        duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
    )


def lookup_inventory(
    query: InventoryLookupInput | dict[str, Any] | None = None,
    *,
    base_url: str | None = None,
    timeout_seconds: float = INVENTORY_LOOKUP_TIMEOUT_SECONDS,
    transport: httpx.BaseTransport | None = None,
) -> InventoryLookupOutput:
    """Call the inventory manager via GET only. Never creates/updates/deletes."""
    started = time.perf_counter()
    try:
        if query is None:
            inp = InventoryLookupInput()
        elif isinstance(query, dict):
            inp = InventoryLookupInput.model_validate(query)
        else:
            inp = query
    except Exception as exc:  # noqa: BLE001
        return _failed(
            started,
            error="invalid_input",
            message=f"Invalid inventory lookup input: {exc}",
        )

    root = (base_url or _inventory_api_base()).rstrip("/")
    headers = _auth_headers()
    http_timeout = build_inventory_http_timeout(timeout_seconds)

    try:
        with httpx.Client(
            base_url=root,
            timeout=http_timeout,
            transport=transport,
            headers=headers,
        ) as client:
            if inp.product_id and not inp.name_contains:
                product_id = inp.product_id.strip()
                path = PRODUCT_BY_ID_PATH_TEMPLATE.format(product_id=product_id)
                response = client.get(path)
                if response.status_code == 404:
                    return _failed(
                        started,
                        error="not_found",
                        message=(
                            f"{INVENTORY_FALLBACK_MESSAGE} "
                            f"Product {product_id} was not found in the inventory manager."
                        ),
                    )
                if response.status_code in (401, 403):
                    return _failed(started, error="auth_error", message=INVENTORY_FALLBACK_MESSAGE)
                if response.status_code >= 400:
                    return _failed(started, error="service_error", message=INVENTORY_FALLBACK_MESSAGE)
                payload = response.json()
                product = _record_from_payload(payload if isinstance(payload, dict) else {})
                return InventoryLookupOutput(
                    ok=True,
                    products=[product],
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                )

            params: dict[str, str] = {}
            if inp.product_id:
                params["product_id"] = inp.product_id.strip()
            if inp.name_contains:
                params["name"] = inp.name_contains.strip()
            response = client.get(PRODUCTS_LIST_PATH, params=params or None)
            if response.status_code in (401, 403):
                return _failed(started, error="auth_error", message=INVENTORY_FALLBACK_MESSAGE)
            if response.status_code >= 400:
                return _failed(started, error="service_error", message=INVENTORY_FALLBACK_MESSAGE)
            payload = response.json()
            items = payload if isinstance(payload, list) else payload.get("products", [])
            products = [_record_from_payload(item) for item in items if isinstance(item, dict)]
            if inp.product_id and not products:
                return _failed(
                    started,
                    error="not_found",
                    message=(
                        f"{INVENTORY_FALLBACK_MESSAGE} "
                        f"Product {inp.product_id} was not found in the inventory manager."
                    ),
                )
            return InventoryLookupOutput(
                ok=True,
                products=products,
                message=None if products else "No products matched those filters.",
                duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
            )
    except httpx.TimeoutException:
        return _failed(started, error="timeout", message=INVENTORY_FALLBACK_MESSAGE)
    except Exception:  # noqa: BLE001
        return _failed(started, error="service_error", message=INVENTORY_FALLBACK_MESSAGE)
