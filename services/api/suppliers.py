from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class SupplierCategory(str, Enum):
    PROTEINS = "proteins"
    PRODUCE = "produce"
    PANTRY = "pantry"
    BEVERAGES = "beverages"
    PACKAGING = "packaging"
    CLEANING = "cleaning"


class SupplierStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class SupplierBase(BaseModel):
    name: str = Field(min_length=1)
    country: str = Field(min_length=1)
    product_categories: list[SupplierCategory] = Field(min_length=1)
    rate: float = Field(gt=0)
    last_rate_update_date: date
    status: SupplierStatus


class SupplierCreate(SupplierBase):
    pass


class SupplierResponse(SupplierBase):
    id: int
    updated_at: datetime
