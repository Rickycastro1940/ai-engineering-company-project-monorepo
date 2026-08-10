"""Brasaland inventory manager — CSV-backed, read-first HTTP API.

Data lives in the company ``products.csv`` at the repo root (same file the
earlier inventory project used). This is **not** a parallel fake dataset.

Stretch routes used by the LangGraph inventory tool:

- ``GET /inventory/products`` — list / filter products (read-only)
- ``GET /inventory/products/{id}`` — get one product by id (read-only)

Compatibility aliases for the plain-Python inventory agent:

- ``GET /inventory`` — same list as ``/inventory/products``
"""

from __future__ import annotations

import csv
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_CSV = REPO_ROOT / "products.csv"

router = APIRouter(prefix="/inventory", tags=["inventory"])


class InventoryProduct(BaseModel):
    """One product row as exposed by the inventory manager."""

    model_config = ConfigDict(extra="forbid")

    product_id: str
    name: str
    quantity: int
    unit: str
    source: str = Field(default="inventory_manager")


def _load_products(*, csv_path: Path | None = None) -> list[InventoryProduct]:
    path = csv_path or PRODUCTS_CSV
    if not path.exists():
        return []
    products: list[InventoryProduct] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            pid = (row.get("product_id") or "").strip()
            if not pid:
                continue
            try:
                qty = int(float((row.get("quantity") or "0").strip() or "0"))
            except ValueError:
                qty = 0
            products.append(
                InventoryProduct(
                    product_id=pid,
                    name=(row.get("name") or "").strip(),
                    quantity=qty,
                    unit=(row.get("unit") or "").strip() or "unit",
                    source="inventory_manager",
                )
            )
    return products


def get_product(product_id: str, *, csv_path: Path | None = None) -> InventoryProduct | None:
    needle = product_id.strip().casefold()
    for product in _load_products(csv_path=csv_path):
        if product.product_id.casefold() == needle:
            return product
    return None


def search_products(
    *,
    product_id: str | None = None,
    name_contains: str | None = None,
    csv_path: Path | None = None,
) -> list[InventoryProduct]:
    products = _load_products(csv_path=csv_path)
    if product_id:
        found = get_product(product_id, csv_path=csv_path)
        return [found] if found else []
    if name_contains:
        needle = name_contains.casefold()
        return [p for p in products if needle in p.name.casefold()]
    return products


@router.get("/products", response_model=list[InventoryProduct])
def list_products(
    product_id: str | None = Query(default=None),
    name: str | None = Query(default=None, description="Case-insensitive name substring"),
) -> list[InventoryProduct]:
    """Read-only list/search — used by the LangGraph inventory tool."""
    return search_products(product_id=product_id, name_contains=name)


@router.get("/products/{product_id}", response_model=InventoryProduct)
def get_product_by_id(product_id: str) -> InventoryProduct:
    """Read-only get-by-id for a single inventory product."""
    record = get_product(product_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Product not found: {product_id}")
    return record


@router.get("", response_model=list[InventoryProduct])
@router.get("/", response_model=list[InventoryProduct], include_in_schema=False)
def list_inventory_compat() -> list[InventoryProduct]:
    """Alias of ``GET /inventory/products`` for the legacy inventory agent."""
    return search_products()
