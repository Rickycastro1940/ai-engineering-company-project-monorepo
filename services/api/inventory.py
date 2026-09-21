from __future__ import annotations

import csv
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from users import get_current_user

logger = logging.getLogger("brasaland.inventory")

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_FILE = REPO_ROOT / "products.csv"
ORDERS_FILE = REPO_ROOT / "inventory_orders.csv"
FIELDNAMES = ["product_id", "name", "quantity", "unit"]
ORDER_FIELDNAMES = [
    "order_id",
    "product_id",
    "product_name",
    "quantity",
    "unit",
    "order_type",
    "created_at",
    "user_uuid",
]

ProductRow = Dict[str, Union[str, int]]

router = APIRouter(prefix="/inventory", tags=["inventory"])


class ProductCreate(BaseModel):
    name: str = Field(min_length=1)
    quantity: int = Field(ge=0)
    unit: str = Field(min_length=1)


class StockDelta(BaseModel):
    delta: int


class InboundOrderCreate(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(gt=0)


class OutboundOrderCreate(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(gt=0)


def _ensure_products_file() -> None:
    if PRODUCTS_FILE.exists():
        return
    try:
        with PRODUCTS_FILE.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
    except OSError as error:
        raise HTTPException(status_code=500, detail="Unable to create inventory file") from error


def load_products() -> List[ProductRow]:
    _ensure_products_file()
    try:
        with PRODUCTS_FILE.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as error:
        raise HTTPException(status_code=500, detail="Unable to read inventory file") from error

    products: List[ProductRow] = []
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
        except (KeyError, TypeError, ValueError):
            logger.warning("Skipping invalid inventory row")
            continue
    return products


def save_products(products: List[ProductRow]) -> None:
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


def _find_product(products: List[ProductRow], product_id: int) -> Optional[ProductRow]:
    for product in products:
        if product["product_id"] == product_id:
            return product
    return None


def create_product(name: str, quantity: int, unit: str) -> ProductRow:
    products = load_products()
    next_id = max((int(product["product_id"]) for product in products), default=0) + 1
    product: ProductRow = {
        "product_id": next_id,
        "name": name.strip(),
        "quantity": quantity,
        "unit": unit.strip(),
    }
    products.append(product)
    save_products(products)
    return product


def apply_delta(product_id: int, delta: int) -> ProductRow:
    products = load_products()
    product = _find_product(products, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")

    new_quantity = int(product["quantity"]) + delta
    if new_quantity < 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Insufficient stock: cannot reduce below 0 "
                f"(current: {product['quantity']}, delta: {delta})"
            ),
        )

    product["quantity"] = new_quantity
    save_products(products)
    return product


def _product_with_current_stock(product: ProductRow) -> dict:
    return {
        "product_id": product["product_id"],
        "name": product["name"],
        "quantity": product["quantity"],
        "unit": product["unit"],
        "current_stock": int(product["quantity"]),
    }


def get_alerts(threshold: int = 10) -> List[ProductRow]:
    if threshold < 0:
        raise HTTPException(status_code=400, detail="Threshold must be greater than or equal to 0")
    return [product for product in load_products() if int(product["quantity"]) < threshold]


def user_uuid_for(user: dict) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"brasaland:staff:{user.get('id')}"))


def _ensure_orders_file() -> None:
    if ORDERS_FILE.exists():
        return
    try:
        with ORDERS_FILE.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=ORDER_FIELDNAMES)
            writer.writeheader()
    except OSError as error:
        raise HTTPException(status_code=500, detail="Unable to create inventory orders file") from error


def load_orders() -> List[dict]:
    _ensure_orders_file()
    try:
        with ORDERS_FILE.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as error:
        raise HTTPException(status_code=500, detail="Unable to read inventory orders file") from error

    orders: List[dict] = []
    for row in rows:
        try:
            orders.append(
                {
                    "order_id": int(row["order_id"]),
                    "product_id": int(row["product_id"]),
                    "product_name": row["product_name"],
                    "quantity": int(row["quantity"]),
                    "unit": row.get("unit", ""),
                    "order_type": row["order_type"],
                    "created_at": row["created_at"],
                    "user_uuid": row["user_uuid"],
                }
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("Skipping invalid inventory order row")
            continue
    orders.sort(key=lambda item: item["order_id"], reverse=True)
    return orders


def record_order(
    *,
    order_type: str,
    product: ProductRow,
    quantity: int,
    user: dict,
) -> dict:
    orders = load_orders()
    next_id = max((int(order["order_id"]) for order in orders), default=0) + 1
    order = {
        "order_id": next_id,
        "product_id": int(product["product_id"]),
        "product_name": str(product["name"]),
        "quantity": quantity,
        "unit": str(product["unit"]),
        "order_type": order_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user_uuid": user_uuid_for(user),
    }
    try:
        with ORDERS_FILE.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=ORDER_FIELDNAMES)
            writer.writerow(order)
    except OSError as error:
        raise HTTPException(status_code=500, detail="Unable to write inventory orders file") from error
    return order


@router.get("")
def list_inventory() -> List[ProductRow]:
    return load_products()


@router.post("", status_code=201)
def add_product(body: ProductCreate) -> ProductRow:
    return create_product(body.name, body.quantity, body.unit)


@router.get("/alerts")
def low_stock_alerts(threshold: int = 10) -> List[ProductRow]:
    return get_alerts(threshold)


@router.get("/orders")
def list_inventory_orders(_current_user: dict = Depends(get_current_user)) -> List[dict]:
    return load_orders()


@router.post("/orders/inbound", status_code=201)
def create_inbound_order(
    body: InboundOrderCreate,
    current_user: dict = Depends(get_current_user),
) -> dict:
    updated = apply_delta(body.product_id, body.quantity)
    order = record_order(
        order_type="inbound",
        product=updated,
        quantity=body.quantity,
        user=current_user,
    )
    return {
        "order_type": "inbound",
        "quantity": body.quantity,
        "product": _product_with_current_stock(updated),
        "order": order,
    }


@router.post("/orders/outbound", status_code=201)
def create_outbound_order(
    body: OutboundOrderCreate,
    current_user: dict = Depends(get_current_user),
) -> dict:
    updated = apply_delta(body.product_id, -body.quantity)
    order = record_order(
        order_type="outbound",
        product=updated,
        quantity=body.quantity,
        user=current_user,
    )
    return {
        "order_type": "outbound",
        "quantity": body.quantity,
        "product": _product_with_current_stock(updated),
        "order": order,
    }


@router.get("/{product_id}")
def read_product(product_id: int) -> dict:
    product = _find_product(load_products(), product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    return _product_with_current_stock(product)


@router.patch("/{product_id}")
def update_stock(product_id: int, body: StockDelta) -> ProductRow:
    return apply_delta(product_id, body.delta)
