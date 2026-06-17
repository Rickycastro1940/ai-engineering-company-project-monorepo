from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tinydb import Query, TinyDB

from .suppliers import SupplierCreate, SupplierResponse, _db_path, _model_dump

INITIAL_SUPPLIERS: list[SupplierCreate] = [
    SupplierCreate(
        name="Carnes Antioquia",
        country="Colombia",
        product_categories=["proteins"],
        rate=4.65,
        last_rate_update_date="2026-05-20",
        status="active",
    ),
    SupplierCreate(
        name="Avicola Las Palmas",
        country="Colombia",
        product_categories=["proteins"],
        rate=3.9,
        last_rate_update_date="2026-05-18",
        status="active",
    ),
    SupplierCreate(
        name="Pescados del Caribe",
        country="Colombia",
        product_categories=["proteins"],
        rate=5.2,
        last_rate_update_date="2026-04-30",
        status="suspended",
    ),
    SupplierCreate(
        name="Verduras Oriente",
        country="Colombia",
        product_categories=["produce"],
        rate=1.45,
        last_rate_update_date="2026-06-01",
        status="active",
    ),
    SupplierCreate(
        name="Frutas Medellin",
        country="Colombia",
        product_categories=["produce"],
        rate=1.3,
        last_rate_update_date="2026-05-29",
        status="active",
    ),
    SupplierCreate(
        name="Granos Andinos",
        country="Colombia",
        product_categories=["pantry"],
        rate=2.1,
        last_rate_update_date="2026-05-10",
        status="active",
    ),
    SupplierCreate(
        name="Salsas La Brasa",
        country="Colombia",
        product_categories=["pantry"],
        rate=1.9,
        last_rate_update_date="2026-05-24",
        status="active",
    ),
    SupplierCreate(
        name="Bebidas Tropicales",
        country="Colombia",
        product_categories=["beverages"],
        rate=1.75,
        last_rate_update_date="2026-05-21",
        status="active",
    ),
    SupplierCreate(
        name="Empaques EcoBogota",
        country="Colombia",
        product_categories=["packaging"],
        rate=0.28,
        last_rate_update_date="2026-06-02",
        status="active",
    ),
    SupplierCreate(
        name="Limpieza Profesional",
        country="Colombia",
        product_categories=["cleaning"],
        rate=0.55,
        last_rate_update_date="2026-05-17",
        status="active",
    ),
    SupplierCreate(
        name="Florida Prime Meats",
        country="United States",
        product_categories=["proteins"],
        rate=5.8,
        last_rate_update_date="2026-05-22",
        status="active",
    ),
    SupplierCreate(
        name="Sunshine Poultry",
        country="United States",
        product_categories=["proteins"],
        rate=4.4,
        last_rate_update_date="2026-05-26",
        status="active",
    ),
    SupplierCreate(
        name="Gulf Seafood Supply",
        country="United States",
        product_categories=["proteins"],
        rate=6.3,
        last_rate_update_date="2026-04-28",
        status="suspended",
    ),
    SupplierCreate(
        name="Miami Fresh Produce",
        country="United States",
        product_categories=["produce"],
        rate=1.85,
        last_rate_update_date="2026-06-03",
        status="active",
    ),
    SupplierCreate(
        name="Orlando Citrus Farms",
        country="United States",
        product_categories=["produce"],
        rate=1.6,
        last_rate_update_date="2026-05-31",
        status="active",
    ),
    SupplierCreate(
        name="Latin Pantry Imports",
        country="United States",
        product_categories=["pantry"],
        rate=2.75,
        last_rate_update_date="2026-05-13",
        status="active",
    ),
    SupplierCreate(
        name="Brasa Sauce Co.",
        country="United States",
        product_categories=["pantry"],
        rate=2.2,
        last_rate_update_date="2026-05-27",
        status="active",
    ),
    SupplierCreate(
        name="Florida Beverage Partners",
        country="United States",
        product_categories=["beverages"],
        rate=1.95,
        last_rate_update_date="2026-05-19",
        status="active",
    ),
    SupplierCreate(
        name="Gulf Coast Packaging",
        country="United States",
        product_categories=["packaging"],
        rate=0.32,
        last_rate_update_date="2026-06-04",
        status="active",
    ),
    SupplierCreate(
        name="Clean Kitchen Supply",
        country="United States",
        product_categories=["cleaning"],
        rate=0.7,
        last_rate_update_date="2026-05-15",
        status="active",
    ),
]


def seed_suppliers(db_path: Path | None = None) -> int:
    target_path = db_path or _db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    supplier_query = Query()
    inserted_count = 0

    with TinyDB(target_path) as db:
        table = db.table("suppliers")

        for supplier in INITIAL_SUPPLIERS:
            if table.contains((supplier_query.name == supplier.name) & (supplier_query.country == supplier.country)):
                continue

            payload = _model_dump(supplier)
            doc_id = table.insert(payload)
            response = SupplierResponse(
                id=doc_id,
                updated_at=datetime.now(timezone.utc),
                **payload,
            )
            table.update(_model_dump(response), doc_ids=[doc_id])
            inserted_count += 1

    return inserted_count


def main() -> None:
    inserted_count = seed_suppliers()
    print(f"Inserted {inserted_count} supplier record(s).")


if __name__ == "__main__":
    main()
