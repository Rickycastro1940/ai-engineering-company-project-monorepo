from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    sku: str
    category: str = "-"
    description: Optional[str] = None
    price: float = 0.0
    quantity: int = 0
    unit: str = "unit"


class InboundOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    quantity: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_uuid: str


class OutboundOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    quantity: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_uuid: str
