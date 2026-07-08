from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from auth import get_current_user
from database import get_db
from models import InboundOrder, OutboundOrder, Product
from schemas import (
    InboundOrderCreate,
    OrderItemResponse,
    OrderResponse,
    OutboundOrderCreate,
    ProductCreate,
    ProductResponse,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _slugify_name(value: str) -> str:
    cleaned = "-".join(value.strip().lower().split())
    return cleaned or "product"


def _product_response(product: Product) -> ProductResponse:
    return ProductResponse(
        id=product.id or 0,
        product_id=str(product.id or 0),
        sku=product.sku,
        name=product.name,
        category=product.category,
        description=product.description,
        price=product.price,
        quantity=product.quantity,
        unit=product.unit,
        current_stock=product.quantity,
    )


def _order_response(order: InboundOrder | OutboundOrder, order_type: str, product: Product) -> OrderResponse:
    return OrderResponse(
        id=str(order.id or ""),
        type=order_type,
        created_by=order.user_uuid,
        created_at=order.created_at,
        items=[
            OrderItemResponse(
                product_id=product.id or 0,
                sku=product.sku,
                name=product.name,
                unit=product.unit,
                quantity=order.quantity,
                price=product.price,
            )
        ],
    )


@router.get("")
def list_inventory(db: Session = Depends(get_db)):
    products = db.exec(select(Product)).all()
    return [
        {
            "product_id": product.id,
            "name": product.name,
            "quantity": product.quantity,
            "unit": product.unit,
            "sku": product.sku,
        }
        for product in products
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def add_product(product_in: dict, db: Session = Depends(get_db)):
    name = str(product_in.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Product name is required")

    quantity = int(product_in.get("quantity", 0))
    if quantity < 0:
        raise HTTPException(status_code=400, detail="Quantity must be zero or greater")

    unit = str(product_in.get("unit", "unit")).strip() or "unit"
    sku = str(product_in.get("sku", f"SKU-{_slugify_name(name).upper()}"))
    category = str(product_in.get("category", "-"))
    description = product_in.get("description")
    price = float(product_in.get("price", 0))

    db_product = Product(
        name=name,
        sku=sku,
        category=category,
        description=description,
        price=price,
        quantity=quantity,
        unit=unit,
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return {
        "product_id": db_product.id,
        "name": db_product.name,
        "quantity": db_product.quantity,
        "unit": db_product.unit,
        "sku": db_product.sku,
    }


@router.patch("/{product_id}")
def update_stock(product_id: int, payload: dict, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    delta = int(payload.get("delta", 0))
    next_quantity = product.quantity + delta
    if next_quantity < 0:
        raise HTTPException(status_code=400, detail="Insufficient stock available")

    product.quantity = next_quantity
    db.add(product)
    db.commit()
    db.refresh(product)
    return {
        "product_id": product.id,
        "name": product.name,
        "quantity": product.quantity,
        "unit": product.unit,
        "sku": product.sku,
    }


@router.get("/alerts")
def get_low_stock_alerts(threshold: int = Query(default=10, ge=0), db: Session = Depends(get_db)):
    products = db.exec(select(Product)).all()
    return [
        {
            "product_id": product.id,
            "name": product.name,
            "quantity": product.quantity,
            "unit": product.unit,
            "sku": product.sku,
        }
        for product in products
        if product.quantity < threshold
    ]


@router.get("/products", response_model=List[ProductResponse])
def get_products(db: Session = Depends(get_db)):
    products = db.exec(select(Product)).all()
    return [_product_response(product) for product in products]


@router.get("/products/{id}", response_model=ProductResponse)
def get_product(id: int, db: Session = Depends(get_db)):
    product = db.get(Product, id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_response(product)


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product_in: ProductCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    del current_user
    db_product = Product(**product_in.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return _product_response(db_product)


@router.post("/orders/inbound", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_inbound_order(
    order_in: InboundOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    product = db.get(Product, order_in.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    product.quantity += order_in.quantity
    order = InboundOrder(
        product_id=order_in.product_id,
        quantity=order_in.quantity,
        user_uuid=current_user["uuid"],
    )
    db.add(product)
    db.add(order)
    db.commit()
    db.refresh(order)
    db.refresh(product)
    return _order_response(order, "INBOUND", product)


@router.post("/orders/outbound", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_outbound_order(
    order_in: OutboundOrderCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    product = db.get(Product, order_in.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    if order_in.quantity > product.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock available")

    product.quantity -= order_in.quantity
    order = OutboundOrder(
        product_id=order_in.product_id,
        quantity=order_in.quantity,
        user_uuid=current_user["uuid"],
    )
    db.add(product)
    db.add(order)
    db.commit()
    db.refresh(order)
    db.refresh(product)
    return _order_response(order, "OUTBOUND", product)


@router.get("/orders", response_model=List[OrderResponse])
def get_orders(db: Session = Depends(get_db)):
    products = {product.id: product for product in db.exec(select(Product)).all()}
    inbound_orders = db.exec(select(InboundOrder)).all()
    outbound_orders = db.exec(select(OutboundOrder)).all()

    all_orders: List[OrderResponse] = []
    for order in inbound_orders:
        product = products.get(order.product_id)
        if product is not None:
            all_orders.append(_order_response(order, "INBOUND", product))
    for order in outbound_orders:
        product = products.get(order.product_id)
        if product is not None:
            all_orders.append(_order_response(order, "OUTBOUND", product))

    all_orders.sort(key=lambda order: order.created_at, reverse=True)
    return all_orders
