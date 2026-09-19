"""Dedicated Brasaland inventory API router (prefix ``/inventory``).

ORM entities: Ingredient, IngredientEntry, IngredientExit (CONTEXT-company.md).
URL paths keep the milestone ``/products`` and ``/orders`` routes.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from users import get_current_user

from services.database import get_db
from services.inventory_stock import (
    computed_stock_by_ingredient,
    insufficient_stock_message,
    outbound_exceeds_stock,
)
from services.models import Ingredient, IngredientEntry, IngredientExit
from services.schemas import (
    IngredientCreate,
    IngredientCountry,
    IngredientEntryCreate,
    IngredientEntryResponse,
    IngredientExitCreate,
    IngredientExitResponse,
    IngredientResponse,
    InventoryOrderResponse,
    OrderType,
)

router = APIRouter(
    prefix="/inventory",
    tags=["inventory"],
    dependencies=[Depends(get_current_user)],
)


def _user_uuid(current_user: dict[str, Any]) -> str:
    """TinyDB document id of the authenticated staff user (no SQL User table)."""
    return str(current_user["id"])


def _to_ingredient_response(ingredient: Ingredient, current_stock: float) -> IngredientResponse:
    return IngredientResponse(
        id=ingredient.id or 0,
        name=ingredient.name,
        sku=ingredient.sku,
        unit=ingredient.unit,
        category=ingredient.category,
        country=ingredient.country,
        current_stock=current_stock,
    )


def _get_ingredient(session: Session, ingredient_id: int) -> Ingredient:
    ingredient = session.get(Ingredient, ingredient_id)
    if ingredient is None:
        raise HTTPException(status_code=404, detail=f"Ingredient {ingredient_id} not found")
    return ingredient


@router.get("/products", response_model=list[IngredientResponse])
def list_ingredients(
    country: Optional[IngredientCountry] = Query(default=None),
    session: Session = Depends(get_db),
) -> list[IngredientResponse]:
    stmt = select(Ingredient).order_by(Ingredient.id)
    if country is not None:
        stmt = stmt.where(Ingredient.country == country)
    ingredients = session.exec(stmt).all()
    stock = computed_stock_by_ingredient(session)
    return [_to_ingredient_response(item, stock.get(item.id or 0, 0.0)) for item in ingredients]


@router.post("/products", response_model=IngredientResponse, status_code=201)
def create_ingredient(
    body: IngredientCreate,
    session: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> IngredientResponse:
    del current_user
    existing = session.exec(select(Ingredient).where(Ingredient.sku == body.sku)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Ingredient SKU {body.sku} already exists")
    ingredient = Ingredient(
        name=body.name,
        sku=body.sku,
        unit=body.unit,
        category=body.category,
        country=body.country,
    )
    session.add(ingredient)
    session.commit()
    session.refresh(ingredient)
    ingredient_id = ingredient.id or 0
    stock = computed_stock_by_ingredient(session, [ingredient_id]).get(ingredient_id, 0.0)
    return _to_ingredient_response(ingredient, stock)


@router.get("/products/{id}", response_model=IngredientResponse)
def get_ingredient(id: int, session: Session = Depends(get_db)) -> IngredientResponse:
    ingredient = _get_ingredient(session, id)
    stock = computed_stock_by_ingredient(session, [id])
    return _to_ingredient_response(ingredient, stock.get(id, 0.0))


@router.post("/orders/inbound", response_model=IngredientEntryResponse, status_code=201)
def create_ingredient_entry(
    body: IngredientEntryCreate,
    session: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> IngredientEntryResponse:
    ingredient = _get_ingredient(session, body.ingredient_id)
    entry = IngredientEntry(
        ingredient_id=body.ingredient_id,
        quantity=body.quantity,
        supplier_name=body.supplier_name,
        location_id=body.location_id,
        user_uuid=_user_uuid(current_user),
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return IngredientEntryResponse(
        id=entry.id or 0,
        ingredient_id=entry.ingredient_id,
        quantity=entry.quantity,
        supplier_name=entry.supplier_name,
        location_id=entry.location_id,
        created_at=entry.created_at,
        user_uuid=entry.user_uuid,
        name=ingredient.name,
        sku=ingredient.sku,
    )


@router.post("/orders/outbound", response_model=IngredientExitResponse, status_code=201)
def create_ingredient_exit(
    body: IngredientExitCreate,
    session: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> IngredientExitResponse:
    ingredient = _get_ingredient(session, body.ingredient_id)
    # CONTEXT-company.md: stock is global per Ingredient, not per kitchen/warehouse.
    available = computed_stock_by_ingredient(session, [body.ingredient_id]).get(body.ingredient_id, 0.0)
    if outbound_exceeds_stock(available, body.quantity):
        raise HTTPException(
            status_code=400,
            detail=insufficient_stock_message(ingredient.name, available, body.quantity),
        )
    exit_row = IngredientExit(
        ingredient_id=body.ingredient_id,
        quantity=body.quantity,
        reason=body.reason,
        location_id=body.location_id,
        user_uuid=_user_uuid(current_user),
    )
    session.add(exit_row)
    session.commit()
    session.refresh(exit_row)
    return IngredientExitResponse(
        id=exit_row.id or 0,
        ingredient_id=exit_row.ingredient_id,
        quantity=exit_row.quantity,
        reason=exit_row.reason,
        location_id=exit_row.location_id,
        created_at=exit_row.created_at,
        user_uuid=exit_row.user_uuid,
        name=ingredient.name,
        sku=ingredient.sku,
    )


@router.get("/orders", response_model=list[InventoryOrderResponse])
def list_orders(session: Session = Depends(get_db)) -> list[InventoryOrderResponse]:
    ingredients = {item.id: item for item in session.exec(select(Ingredient)).all() if item.id is not None}
    entries = session.exec(select(IngredientEntry).order_by(IngredientEntry.created_at)).all()
    exits = session.exec(select(IngredientExit).order_by(IngredientExit.created_at)).all()

    orders: list[InventoryOrderResponse] = []
    for entry in entries:
        ingredient = ingredients.get(entry.ingredient_id)
        orders.append(
            InventoryOrderResponse(
                id=entry.id or 0,
                type=OrderType.INBOUND,
                ingredient_id=entry.ingredient_id,
                name=ingredient.name if ingredient else "",
                sku=ingredient.sku if ingredient else "",
                quantity=entry.quantity,
                location_id=entry.location_id,
                created_at=entry.created_at,
                user_uuid=entry.user_uuid,
                supplier_name=entry.supplier_name,
            )
        )
    for exit_row in exits:
        ingredient = ingredients.get(exit_row.ingredient_id)
        orders.append(
            InventoryOrderResponse(
                id=exit_row.id or 0,
                type=OrderType.OUTBOUND,
                ingredient_id=exit_row.ingredient_id,
                name=ingredient.name if ingredient else "",
                sku=ingredient.sku if ingredient else "",
                quantity=exit_row.quantity,
                location_id=exit_row.location_id,
                created_at=exit_row.created_at,
                user_uuid=exit_row.user_uuid,
                reason=exit_row.reason,
            )
        )
    orders.sort(key=lambda item: item.created_at)
    return orders
