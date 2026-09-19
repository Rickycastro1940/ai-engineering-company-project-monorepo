"""SQLModel tables for Brasaland kitchen ingredients (CONTEXT.md Operations + Procurement).

Canonical names from CONTEXT-company.md — not Product / InboundOrder / OutboundOrder:
``Ingredient``, ``IngredientEntry``, ``IngredientExit``.

``IngredientEntry.ingredient_id`` and ``IngredientExit.ingredient_id`` are SQL FKs to
``Ingredient.id`` only. ``location_id`` and TinyDB ``user_uuid`` are not SQL FKs.
``current_stock`` is computed from orders and is never a column.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Ingredient(SQLModel, table=True):
    """Kitchen ingredient stocked across Brasaland's Colombia (CO) and Florida (US) markets."""

    __tablename__ = "ingredient"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(min_length=1, max_length=120, index=True)
    sku: str = Field(min_length=1, max_length=40, unique=True, index=True)
    unit: str = Field(max_length=16)  # kg | litre | unit
    category: str = Field(max_length=32)  # meat, produce, sauce, beverage, packaging, cleaning
    country: str = Field(max_length=2, index=True)  # CO | US


class IngredientEntry(SQLModel, table=True):
    """Supplier delivery. FK: ``ingredient_id`` → ``ingredient.id`` (Ingredient, not Product)."""

    __tablename__ = "ingrediententry"

    id: Optional[int] = Field(default=None, primary_key=True)
    ingredient_id: int = Field(
        sa_column=Column(Integer, ForeignKey("ingredient.id"), nullable=False, index=True)
    )
    quantity: float
    supplier_name: str = Field(max_length=160)
    location_id: int
    created_at: datetime = Field(default_factory=_utcnow)
    user_uuid: str = Field(sa_column=Column(String(64), nullable=False, index=True))


class IngredientExit(SQLModel, table=True):
    """Consumption or waste. FK: ``ingredient_id`` → ``ingredient.id``. ``reason`` is consumption|waste."""

    __tablename__ = "ingredientexit"

    id: Optional[int] = Field(default=None, primary_key=True)
    ingredient_id: int = Field(
        sa_column=Column(Integer, ForeignKey("ingredient.id"), nullable=False, index=True)
    )
    quantity: float
    reason: str = Field(max_length=16)
    location_id: int
    created_at: datetime = Field(default_factory=_utcnow)
    user_uuid: str = Field(sa_column=Column(String(64), nullable=False, index=True))
