"""Computed ``current_stock`` for Brasaland ingredients.

``current_stock`` is never a database column and cannot be set on create/update.

Formula (per Ingredient, already scoped by ``country`` CO/US):

    current_stock = SUM(IngredientEntry.quantity) − SUM(IngredientExit.quantity)

Partition from CONTEXT.md: each Ingredient is already scoped to one market via
``country`` (``CO`` or ``US``). There is no warehouse entity. ``location_id``
(1–14 kitchens) is recorded on orders for traceability only and does not split
stock.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlmodel import Session, col, func, select

from services.models import IngredientEntry, IngredientExit


def computed_stock_by_ingredient(
    session: Session,
    ingredient_ids: Optional[list[int]] = None,
) -> dict[int, float]:
    inbound_stmt = select(
        IngredientEntry.ingredient_id,
        func.coalesce(func.sum(IngredientEntry.quantity), 0),
    ).group_by(IngredientEntry.ingredient_id)
    outbound_stmt = select(
        IngredientExit.ingredient_id,
        func.coalesce(func.sum(IngredientExit.quantity), 0),
    ).group_by(IngredientExit.ingredient_id)
    if ingredient_ids is not None:
        inbound_stmt = inbound_stmt.where(col(IngredientEntry.ingredient_id).in_(ingredient_ids))
        outbound_stmt = outbound_stmt.where(col(IngredientExit.ingredient_id).in_(ingredient_ids))

    inbound = {ingredient_id: float(total) for ingredient_id, total in session.exec(inbound_stmt).all()}
    outbound = {ingredient_id: float(total) for ingredient_id, total in session.exec(outbound_stmt).all()}
    stock: dict[int, float] = defaultdict(float)
    for ingredient_id, total in inbound.items():
        stock[ingredient_id] += total
    for ingredient_id, total in outbound.items():
        stock[ingredient_id] -= total
    return stock


def _format_qty(value: float) -> float | int:
    return int(value) if value == int(value) else value


def insufficient_stock_message(name: str, available: float, requested: float) -> str:
    return (
        f"Insufficient stock for ingredient '{name}'. "
        f"Available: {_format_qty(available)}, requested: {_format_qty(requested)}."
    )


def outbound_exceeds_stock(available: float, requested: float) -> bool:
    return requested > available
