"""Compatibility shim — Pydantic inventory schemas live in ``services/schemas.py``."""

from services.schemas import (
    IngredientCreate,
    IngredientEntryCreate,
    IngredientEntryResponse,
    IngredientExitCreate,
    IngredientExitResponse,
    IngredientResponse,
    InventoryOrderResponse,
    OrderType,
)

__all__ = [
    "IngredientCreate",
    "IngredientEntryCreate",
    "IngredientEntryResponse",
    "IngredientExitCreate",
    "IngredientExitResponse",
    "IngredientResponse",
    "InventoryOrderResponse",
    "OrderType",
]
