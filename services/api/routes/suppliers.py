from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

try:
    from ..database import model_dump, supplier_table
    from ..models import SupplierCategory, SupplierCreate, SupplierRateUpdate, SupplierResponse, SupplierStatusUpdate
except ImportError:  # pragma: no cover - supports direct script-style imports during local debugging.
    from database import model_dump, supplier_table
    from models import SupplierCategory, SupplierCreate, SupplierRateUpdate, SupplierResponse, SupplierStatusUpdate

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def _response_from_record(record: dict[str, Any], doc_id: int) -> SupplierResponse:
    payload = {**record, "id": int(record.get("id", doc_id))}
    return SupplierResponse(**payload)


def _get_supplier_record(table, supplier_id: int):
    record = table.get(doc_id=supplier_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
    return record


@router.post("", response_model=SupplierResponse, status_code=201)
def create_supplier(body: SupplierCreate) -> SupplierResponse:
    now = datetime.now()
    payload = model_dump(body)

    db, table = supplier_table()
    try:
        doc_id = table.insert(payload)
        response = SupplierResponse(id=doc_id, updated_at=now, **payload)
        table.update(model_dump(response), doc_ids=[doc_id])
        return response
    finally:
        db.close()


@router.get("", response_model=list[SupplierResponse])
def list_suppliers(country: str | None = None, product_category: SupplierCategory | None = None) -> list[SupplierResponse]:
    db, table = supplier_table()
    try:
        suppliers = []
        for document in table.all():
            record = _response_from_record(dict(document), document.doc_id)
            if country and record.country.casefold() != country.casefold():
                continue
            if product_category and product_category not in record.product_categories:
                continue
            suppliers.append(record)
        return suppliers
    finally:
        db.close()


@router.get("/{supplier_id}", response_model=SupplierResponse)
def get_supplier(supplier_id: int) -> SupplierResponse:
    db, table = supplier_table()
    try:
        record = _get_supplier_record(table, supplier_id)
        return _response_from_record(dict(record), supplier_id)
    finally:
        db.close()


@router.patch("/{supplier_id}/rate", response_model=SupplierResponse)
def update_supplier_rate(supplier_id: int, body: SupplierRateUpdate) -> SupplierResponse:
    db, table = supplier_table()
    try:
        record = _get_supplier_record(table, supplier_id)
        updates = {
            "rate": body.rate,
            "last_rate_update_date": date.today().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        table.update(updates, doc_ids=[supplier_id])
        updated_record = {**dict(record), **updates}
        return _response_from_record(updated_record, supplier_id)
    finally:
        db.close()


@router.patch("/{supplier_id}/status", response_model=SupplierResponse)
def update_supplier_status(supplier_id: int, body: SupplierStatusUpdate) -> SupplierResponse:
    db, table = supplier_table()
    try:
        record = _get_supplier_record(table, supplier_id)
        updates = {
            "status": body.status.value,
            "updated_at": datetime.now().isoformat(),
        }
        table.update(updates, doc_ids=[supplier_id])
        updated_record = {**dict(record), **updates}
        return _response_from_record(updated_record, supplier_id)
    finally:
        db.close()


@router.delete("/{supplier_id}")
def delete_supplier(supplier_id: int) -> dict[str, int | bool]:
    db, table = supplier_table()
    try:
        _get_supplier_record(table, supplier_id)
        table.remove(doc_ids=[supplier_id])
        return {"deleted": True, "id": supplier_id}
    finally:
        db.close()
