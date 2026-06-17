from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

API_NAME = "company-backend-api"
API_VERSION = "1.1.0"

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class StatusResponse(BaseModel):
    service: str
    version: str
    status: Literal["ok"]
    capabilities: list[str]


def build_status() -> dict[str, str | list[str]]:
    return {
        "service": API_NAME,
        "version": API_VERSION,
        "status": "ok",
        "capabilities": [
            "inventory",
            "inventory-summary",
            "incident-analysis",
            "user-auth",
            "user-crud",
            "static-web-ui",
        ],
    }


@router.get("/health", response_model=HealthResponse)
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/status", response_model=StatusResponse)
def status() -> dict[str, str | list[str]]:
    return build_status()
