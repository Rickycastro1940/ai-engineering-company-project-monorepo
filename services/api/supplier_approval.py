"""Staff review of a new supplier application.

Procurement receives the public form. This route runs the Supplier, Compliance,
and Operations handoff and returns the management summary. It does not insert
a row into the seeded supplier directory.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agents.supplier_approval.orchestrator import review_supplier_application
from users import get_current_user

router = APIRouter(
    prefix="/suppliers",
    tags=["suppliers"],
    dependencies=[Depends(get_current_user)],
)


class SupplierApplicationRequest(BaseModel):
    raw_text: str = Field(default="", max_length=8000)
    name: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=40)
    product_categories: list[str] | None = None
    emergency_surcharge_pct: float | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, max_length=32)
    health_notes: str | None = Field(default=None, max_length=4000)


class CitedStandard(BaseModel):
    source_document: str | None
    section: str | None
    text: str
    score: float | None
    chunk_index: int | None
    language: str | None = "en"


class ComplianceCheck(BaseModel):
    id: str
    status: Literal["pass", "fail", "condition"]
    detail: str


class ParsedApplication(BaseModel):
    name: str | None
    country: str | None
    market: str | None
    currency: str | None
    categories: list[str]
    emergency_surcharge_pct: float | None
    status: str | None
    complete: bool
    gaps: list[str]


class SupplierApprovalResponse(BaseModel):
    decision: Literal["approve", "approve_with_conditions", "reject"]
    summary: str
    conditions: list[str]
    currency: Literal["COP", "USD"] | None
    market: Literal["Colombia", "Florida"] | None
    roles: list[str]
    orchestration: str
    llm: str
    parsed: ParsedApplication
    compliance: dict


@router.post("/applications/review", response_model=SupplierApprovalResponse)
def review_application(payload: SupplierApplicationRequest) -> dict:
    if not payload.raw_text.strip() and not (payload.name or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Send the supplier application text or the legal name.",
        )
    return review_supplier_application(payload.model_dump())
