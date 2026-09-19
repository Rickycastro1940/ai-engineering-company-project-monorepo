"""Standalone Pydantic schemas for Brasaland ``Ingredient`` / ``IngredientEntry`` / ``IngredientExit``.

Field names and domain values come from CONTEXT-company.md (CONTEXT.md company briefing).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

IngredientCategory = Literal["meat", "produce", "sauce", "beverage", "packaging", "cleaning"]
IngredientCountry = Literal["CO", "US"]
IngredientUnit = Literal["kg", "litre", "unit"]
ExitReason = Literal["consumption", "waste"]


class OrderType(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


# --- Ingredient ---


class IngredientCreate(BaseModel):
    """Request body for POST /inventory/products. ``current_stock`` cannot be set."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    unit: IngredientUnit
    category: IngredientCategory
    country: IngredientCountry

    @field_validator("name", "sku", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class IngredientResponse(BaseModel):
    """Response for GET/POST /inventory/products. ``current_stock`` is computed, not stored."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sku: str
    unit: str
    category: str
    country: str
    current_stock: float


# --- IngredientEntry ---


class IngredientEntryCreate(BaseModel):
    """Request body for POST /inventory/orders/inbound. ``user_uuid`` comes from the JWT, not the body."""

    model_config = ConfigDict(extra="forbid")

    ingredient_id: int
    quantity: float = Field(gt=0)
    supplier_name: str = Field(min_length=1)
    location_id: int = Field(ge=1, le=14)

    @field_validator("supplier_name", mode="before")
    @classmethod
    def strip_supplier(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class IngredientEntryResponse(BaseModel):
    """Response for a logged supplier delivery."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ingredient_id: int
    quantity: float
    supplier_name: str
    location_id: int
    created_at: datetime
    user_uuid: str
    name: Optional[str] = None
    sku: Optional[str] = None


# --- IngredientExit ---


class IngredientExitCreate(BaseModel):
    """Request body for POST /inventory/orders/outbound. ``user_uuid`` comes from the JWT, not the body."""

    model_config = ConfigDict(extra="forbid")

    ingredient_id: int
    quantity: float = Field(gt=0)
    reason: ExitReason
    location_id: int = Field(ge=1, le=14)


class IngredientExitResponse(BaseModel):
    """Response for a logged consumption or waste exit."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ingredient_id: int
    quantity: float
    reason: str
    location_id: int
    created_at: datetime
    user_uuid: str
    name: Optional[str] = None
    sku: Optional[str] = None


class InventoryOrderResponse(BaseModel):
    """Combined entry/exit row for GET /inventory/orders."""

    id: int
    type: OrderType
    ingredient_id: int
    name: str
    sku: str
    quantity: float
    location_id: int
    created_at: datetime
    user_uuid: str
    supplier_name: Optional[str] = None
    reason: Optional[str] = None
