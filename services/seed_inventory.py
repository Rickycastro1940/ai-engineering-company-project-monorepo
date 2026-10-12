"""Seed Brasaland inventory from CONTEXT-company.md before demo.

Minimums: 6 Ingredients, 4 IngredientEntries, 3 IngredientExits.
Seeded ``current_stock`` is always SUM(inbound) − SUM(outbound), never a stored column.
BRS-BEEF-001 net: 50 + 30 − 15 − 5 = 60 kg.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from services.models import Ingredient, IngredientEntry, IngredientExit

SEED_INGREDIENTS = (
    {"name": "Beef brisket", "sku": "BRS-BEEF-001", "unit": "kg", "category": "meat", "country": "CO"},
    {"name": "Pork ribs", "sku": "BRS-PORK-001", "unit": "kg", "category": "meat", "country": "US"},
    {"name": "Chimichurri sauce", "sku": "BRS-SAUCE-001", "unit": "litre", "category": "sauce", "country": "CO"},
    {"name": "House BBQ sauce", "sku": "BRS-SAUCE-002", "unit": "litre", "category": "sauce", "country": "US"},
    {"name": "Yuca (cassava)", "sku": "BRS-PROD-001", "unit": "kg", "category": "produce", "country": "CO"},
    {"name": "Takeaway box (M)", "sku": "BRS-PKG-001", "unit": "unit", "category": "packaging", "country": "CO"},
)

SEED_ENTRIES = (
    {"sku": "BRS-BEEF-001", "quantity": 50, "supplier_name": "Carnes del Valle S.A.", "location_id": 1},
    {"sku": "BRS-BEEF-001", "quantity": 30, "supplier_name": "Carnes del Valle S.A.", "location_id": 1},
    {"sku": "BRS-PORK-001", "quantity": 40, "supplier_name": "MiamiMeat Co.", "location_id": 10},
    {"sku": "BRS-SAUCE-001", "quantity": 20, "supplier_name": "Salsas Artesanales Ltda.", "location_id": 1},
)

SEED_EXITS = (
    {"sku": "BRS-BEEF-001", "quantity": 15, "reason": "consumption", "location_id": 1},
    {"sku": "BRS-BEEF-001", "quantity": 5, "reason": "waste", "location_id": 1},
    {"sku": "BRS-PORK-001", "quantity": 8, "reason": "consumption", "location_id": 10},
)

SEED_NET_STOCK = {
    "BRS-BEEF-001": 60.0,
    "BRS-PORK-001": 32.0,
    "BRS-SAUCE-001": 20.0,
    "BRS-SAUCE-002": 0.0,
    "BRS-PROD-001": 0.0,
    "BRS-PKG-001": 0.0,
}


def seed_inventory(session: Session, user_uuid: str) -> None:
    existing = {item.sku: item for item in session.exec(select(Ingredient)).all() if item.sku}
    by_sku: dict[str, Ingredient] = {}
    for row in SEED_INGREDIENTS:
        ingredient = existing.get(row["sku"])
        if ingredient is None:
            ingredient = Ingredient(**row)
            session.add(ingredient)
            session.flush()
        by_sku[row["sku"]] = ingredient

    if session.exec(select(IngredientEntry)).first() is not None:
        session.commit()
        return

    now = datetime.now(timezone.utc)
    for row in SEED_ENTRIES:
        session.add(
            IngredientEntry(
                ingredient_id=by_sku[row["sku"]].id or 0,
                quantity=row["quantity"],
                supplier_name=row["supplier_name"],
                location_id=row["location_id"],
                created_at=now,
                user_uuid=user_uuid,
            )
        )
    for row in SEED_EXITS:
        session.add(
            IngredientExit(
                ingredient_id=by_sku[row["sku"]].id or 0,
                quantity=row["quantity"],
                reason=row["reason"],
                location_id=row["location_id"],
                created_at=now,
                user_uuid=user_uuid,
            )
        )
    session.commit()
