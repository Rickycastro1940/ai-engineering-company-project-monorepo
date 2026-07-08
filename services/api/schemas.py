from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

class OrderType(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"

class ProductBase(BaseModel):
    sku: str
    name: str
    category: str = "-"
    description: Optional[str] = None
    price: float = Field(default=0, ge=0)
    quantity: int = Field(default=0, ge=0)
    unit: str = "unit"

class ProductCreate(ProductBase):
    pass

class ProductResponse(ProductBase):
    id: int
    product_id: str
    current_stock: int = 0

    class Config:
        from_attributes = True

class OrderItemBase(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)

class OrderItemCreate(OrderItemBase):
    pass

class OrderItemResponse(OrderItemBase):
    sku: Optional[str] = None
    name: Optional[str] = None
    unit: Optional[str] = None
    price: Optional[float] = None

class OrderBase(BaseModel):
    product_id: int
    quantity: int = Field(..., gt=0)

class OrderCreate(OrderBase):
    pass

class InboundOrderCreate(OrderBase):
    type: OrderType = OrderType.INBOUND

class OutboundOrderCreate(OrderBase):
    type: OrderType = OrderType.OUTBOUND

class OrderResponse(BaseModel):
    id: str
    type: OrderType
    created_by: str
    created_at: datetime
    items: List[OrderItemResponse]

    class Config:
        from_attributes = True

class ProductStockResponse(BaseModel):
    product_id: str
    sku: str
    name: str
    current_stock: int
