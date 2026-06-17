from __future__ import annotations

import csv
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_FILE = REPO_ROOT / "products.csv"
FIELDNAMES = ["product_id", "name", "quantity", "unit"]

router = APIRouter(prefix="/inventory", tags=["inventory"])


class ProductCreate(BaseModel):
    name: str = Field(min_length=1)
    quantity: int = Field(ge=0)
    unit: str = Field(min_length=1)


class ProductRead(BaseModel):
    product_id: int
    name: str
    quantity: int
    unit: str


class StockDelta(BaseModel):
    delta: int


class InventorySummary(BaseModel):
    product_count: int
    total_quantity_by_unit: dict[str, int]
    low_stock_count: int
    low_stock_threshold: int


def _ensure_products_file() -> None:
    if PRODUCTS_FILE.exists():
        return
    with PRODUCTS_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()


def load_products() -> list[dict[str, str | int]]:
    _ensure_products_file()
    try:
        with PRODUCTS_FILE.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as error:
        raise HTTPException(status_code=500, detail="Unable to read inventory file") from error

    products: list[dict[str, str | int]] = []
    for row in rows:
        try:
            products.append(
                {
                    "product_id": int(row["product_id"]),
                    "name": row["name"],
                    "quantity": int(row["quantity"]),
                    "unit": row["unit"],
                }
            )
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=500, detail="Invalid inventory data in products.csv") from error
    return products


def save_products(products: list[dict[str, str | int]]) -> None:
    try:
        with PRODUCTS_FILE.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            for product in products:
                writer.writerow(
                    {
                        "product_id": product["product_id"],
                        "name": product["name"],
                        "quantity": product["quantity"],
                        "unit": product["unit"],
                    }
                )
    except OSError as error:
        raise HTTPException(status_code=500, detail="Unable to write inventory file") from error


def _find_product(products: list[dict[str, str | int]], product_id: int) -> dict[str, str | int] | None:
    for product in products:
        if product["product_id"] == product_id:
            return product
    return None


def _require_product(products: list[dict[str, str | int]], product_id: int) -> dict[str, str | int]:
    product = _find_product(products, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    return product


def create_product(name: str, quantity: int, unit: str) -> dict[str, str | int]:
    products = load_products()
    next_id = max((int(product["product_id"]) for product in products), default=0) + 1
    product = {"product_id": next_id, "name": name.strip(), "quantity": quantity, "unit": unit.strip()}
    products.append(product)
    save_products(products)
    return product


def get_product(product_id: int) -> dict[str, str | int]:
    return _require_product(load_products(), product_id)


def apply_delta(product_id: int, delta: int) -> dict[str, str | int]:
    products = load_products()
    product = _require_product(products, product_id)

    new_quantity = int(product["quantity"]) + delta
    if new_quantity < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock: cannot reduce below 0 (current: {product['quantity']}, delta: {delta})",
        )

    product["quantity"] = new_quantity
    save_products(products)
    return product


def get_alerts(threshold: int = 10) -> list[dict[str, str | int]]:
    if threshold < 0:
        raise HTTPException(status_code=400, detail="Threshold must be greater than or equal to 0")
    return [product for product in load_products() if int(product["quantity"]) < threshold]


def build_inventory_summary(threshold: int = 10) -> dict[str, int | dict[str, int]]:
    if threshold < 0:
        raise HTTPException(status_code=400, detail="Threshold must be greater than or equal to 0")
    products = load_products()
    totals_by_unit: dict[str, int] = {}
    low_stock_count = 0
    for product in products:
        quantity = int(product["quantity"])
        unit = str(product["unit"])
        totals_by_unit[unit] = totals_by_unit.get(unit, 0) + quantity
        if quantity < threshold:
            low_stock_count += 1
    return {
        "product_count": len(products),
        "total_quantity_by_unit": dict(sorted(totals_by_unit.items())),
        "low_stock_count": low_stock_count,
        "low_stock_threshold": threshold,
    }


def delete_product(product_id: int) -> dict[str, str | int]:
    products = load_products()
    product = _require_product(products, product_id)
    products.remove(product)
    save_products(products)
    return product


@router.get("", response_model=list[ProductRead])
def list_inventory() -> list[dict[str, str | int]]:
    return load_products()


@router.post("", response_model=ProductRead, status_code=201)
def add_product(body: ProductCreate) -> dict[str, str | int]:
    return create_product(body.name, body.quantity, body.unit)


@router.get("/alerts", response_model=list[ProductRead])
def low_stock_alerts(threshold: int = 10) -> list[dict[str, str | int]]:
    return get_alerts(threshold)


@router.get("/summary", response_model=InventorySummary)
def inventory_summary(threshold: int = 10) -> dict[str, int | dict[str, int]]:
    return build_inventory_summary(threshold)


@router.get("/{product_id}", response_model=ProductRead)
def read_product(product_id: int) -> dict[str, str | int]:
    return get_product(product_id)


@router.patch("/{product_id}", response_model=ProductRead)
def update_stock(product_id: int, body: StockDelta) -> dict[str, str | int]:
    return apply_delta(product_id, body.delta)


@router.delete("/{product_id}", response_model=ProductRead)
def remove_product(product_id: int) -> dict[str, str | int]:
    return delete_product(product_id)
