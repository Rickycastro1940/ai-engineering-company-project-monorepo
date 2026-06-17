from __future__ import annotations

import json
import os
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from tinydb import Query, TinyDB


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


class SupplierRateUpdate(BaseModel):
    rate: float = Field(gt=0)


class SupplierStatusUpdate(BaseModel):
    status: SupplierStatus


DEFAULT_DB_PATH = Path(__file__).with_name("suppliers_db.json")
router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def _db_path() -> Path:
    configured_path = os.environ.get("SUPPLIERS_DB_PATH")
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return DEFAULT_DB_PATH


def _model_dump(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return json.loads(model.json())


def _table():
    target_path = _db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    db = TinyDB(target_path)
    return db, db.table("suppliers")


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
    payload = _model_dump(body)

    db, table = _table()
    try:
        doc_id = table.insert(payload)
        response = SupplierResponse(id=doc_id, updated_at=now, **payload)
        table.update(_model_dump(response), doc_ids=[doc_id])
        return response
    finally:
        db.close()


@router.get("", response_model=list[SupplierResponse])
def list_suppliers(country: str | None = None, product_category: SupplierCategory | None = None) -> list[SupplierResponse]:
    db, table = _table()
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
    db, table = _table()
    try:
        record = _get_supplier_record(table, supplier_id)
        return _response_from_record(dict(record), supplier_id)
    finally:
        db.close()


@router.patch("/{supplier_id}/rate", response_model=SupplierResponse)
def update_supplier_rate(supplier_id: int, body: SupplierRateUpdate) -> SupplierResponse:
    db, table = _table()
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
    db, table = _table()
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
    db, table = _table()
    try:
        _get_supplier_record(table, supplier_id)
        table.remove(doc_ids=[supplier_id])
        return {"deleted": True, "id": supplier_id}
    finally:
        db.close()
