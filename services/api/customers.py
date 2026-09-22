"""Brasaland customers API — Marketing CRM slice from CONTEXT.md.

Camila Ospina needs customer identity, order history, and preferences.
Brasa Points still runs on physical stamp cards (not a digital wallet).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from users import get_current_user

router = APIRouter(
    prefix="/customers",
    tags=["customers"],
    dependencies=[Depends(get_current_user)],
)

Market = Literal["Colombia", "Florida"]


class OrderHistoryItem(BaseModel):
    menu_item_id: str
    location_id: str
    ordered_on: str


class Customer(BaseModel):
    id: str
    name: str
    market: Market
    preferred_location_id: str
    preferences: list[str]
    last_order: OrderHistoryItem | None = None
    order_history: list[OrderHistoryItem] = Field(default_factory=list)
    loyalty_program: str = "Brasa Points"
    loyalty_medium: Literal["physical_stamp_card"] = "physical_stamp_card"
    uses_stamp_card: bool
    digital_loyalty: bool = False


class CustomersOverview(BaseModel):
    company: str = "Brasaland"
    total_customers: int
    colombia_count: int
    florida_count: int
    stamp_card_users: int
    unused_stamp_cards: int
    digital_loyalty: bool = False
    source: str = (
        "CONTEXT.md Marketing — CRM with order history; "
        "Brasa Points remains physical stamp cards"
    )
    customers: list[Customer]


_CUSTOMERS: list[Customer] = [
    Customer(
        id="cus-001",
        name="Ana Morales",
        market="Colombia",
        preferred_location_id="co-med-centro",
        preferences=["grilled-sirloin", "house-sauce"],
        uses_stamp_card=True,
        last_order=OrderHistoryItem(
            menu_item_id="grilled-sirloin",
            location_id="co-med-centro",
            ordered_on="2026-09-18",
        ),
        order_history=[
            OrderHistoryItem(
                menu_item_id="grilled-sirloin",
                location_id="co-med-centro",
                ordered_on="2026-09-18",
            ),
            OrderHistoryItem(
                menu_item_id="corn-arepa",
                location_id="co-med-elpoblado",
                ordered_on="2026-09-11",
            ),
        ],
    ),
    Customer(
        id="cus-002",
        name="Carlos Restrepo",
        market="Colombia",
        preferred_location_id="co-bog-chapinero",
        preferences=["bbq-ribs"],
        uses_stamp_card=False,
        last_order=OrderHistoryItem(
            menu_item_id="bbq-ribs",
            location_id="co-bog-chapinero",
            ordered_on="2026-09-16",
        ),
        order_history=[
            OrderHistoryItem(
                menu_item_id="bbq-ribs",
                location_id="co-bog-chapinero",
                ordered_on="2026-09-16",
            )
        ],
    ),
    Customer(
        id="cus-003",
        name="Valentina Gómez",
        market="Colombia",
        preferred_location_id="co-cali-norte",
        preferences=["tropical-salad"],
        uses_stamp_card=True,
        last_order=None,
        order_history=[],
    ),
    Customer(
        id="cus-004",
        name="Julián Pérez",
        market="Colombia",
        preferred_location_id="co-cartagena",
        preferences=["grilled-chicken"],
        uses_stamp_card=True,
        last_order=OrderHistoryItem(
            menu_item_id="grilled-chicken",
            location_id="co-cartagena",
            ordered_on="2026-09-12",
        ),
        order_history=[
            OrderHistoryItem(
                menu_item_id="grilled-chicken",
                location_id="co-cartagena",
                ordered_on="2026-09-12",
            )
        ],
    ),
    Customer(
        id="cus-005",
        name="Sofia Alvarez",
        market="Florida",
        preferred_location_id="us-mia-brickell",
        preferences=["grilled-sirloin", "tropical-salad"],
        uses_stamp_card=False,
        last_order=OrderHistoryItem(
            menu_item_id="tropical-salad",
            location_id="us-mia-brickell",
            ordered_on="2026-09-19",
        ),
        order_history=[
            OrderHistoryItem(
                menu_item_id="tropical-salad",
                location_id="us-mia-brickell",
                ordered_on="2026-09-19",
            ),
            OrderHistoryItem(
                menu_item_id="grilled-sirloin",
                location_id="us-mia-downtown",
                ordered_on="2026-09-05",
            ),
        ],
    ),
    Customer(
        id="cus-006",
        name="James Walker",
        market="Florida",
        preferred_location_id="us-orlando",
        preferences=["bbq-ribs"],
        uses_stamp_card=True,
        last_order=OrderHistoryItem(
            menu_item_id="bbq-ribs",
            location_id="us-orlando",
            ordered_on="2026-09-14",
        ),
        order_history=[
            OrderHistoryItem(
                menu_item_id="bbq-ribs",
                location_id="us-orlando",
                ordered_on="2026-09-14",
            )
        ],
    ),
    Customer(
        id="cus-007",
        name="Maya Patel",
        market="Florida",
        preferred_location_id="us-tampa",
        preferences=["grilled-chicken", "corn-arepa"],
        uses_stamp_card=False,
        last_order=None,
        order_history=[],
    ),
    Customer(
        id="cus-008",
        name="Luis Herrera",
        market="Colombia",
        preferred_location_id="co-pereira",
        preferences=["house-sauce", "corn-arepa"],
        uses_stamp_card=True,
        last_order=OrderHistoryItem(
            menu_item_id="corn-arepa",
            location_id="co-pereira",
            ordered_on="2026-09-10",
        ),
        order_history=[
            OrderHistoryItem(
                menu_item_id="corn-arepa",
                location_id="co-pereira",
                ordered_on="2026-09-10",
            )
        ],
    ),
]


def _overview() -> CustomersOverview:
    colombia = [row for row in _CUSTOMERS if row.market == "Colombia"]
    florida = [row for row in _CUSTOMERS if row.market == "Florida"]
    stamp_users = [row for row in _CUSTOMERS if row.uses_stamp_card]
    return CustomersOverview(
        total_customers=len(_CUSTOMERS),
        colombia_count=len(colombia),
        florida_count=len(florida),
        stamp_card_users=len(stamp_users),
        unused_stamp_cards=len(_CUSTOMERS) - len(stamp_users),
        customers=list(_CUSTOMERS),
    )


@router.get("", response_model=list[Customer])
def list_customers() -> list[Customer]:
    return list(_CUSTOMERS)


@router.get("/overview", response_model=CustomersOverview)
def customers_overview() -> CustomersOverview:
    return _overview()


@router.get("/{customer_id}", response_model=Customer)
def get_customer(customer_id: str) -> Customer:
    for row in _CUSTOMERS:
        if row.id == customer_id:
            return row
    raise HTTPException(status_code=404, detail="Customer was not found.")
