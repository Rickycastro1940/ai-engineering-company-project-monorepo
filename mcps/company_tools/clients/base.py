"""Shared HTTP helpers for live Company API calls (no domain operations)."""

from __future__ import annotations

import os

import httpx

DEFAULT_API_BASE = "http://127.0.0.1:8000"
HTTP_TIMEOUT_SECONDS = 5.0


def api_base() -> str:
    return (
        os.getenv("COMPANY_API_BASE")
        or os.getenv("INCIDENT_API_BASE")
        or DEFAULT_API_BASE
    ).rstrip("/")


def json_headers() -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    token = os.getenv("INCIDENT_API_TOKEN") or os.getenv("INCIDENT_API_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def build_timeout(seconds: float = HTTP_TIMEOUT_SECONDS) -> httpx.Timeout:
    limit = float(seconds)
    return httpx.Timeout(limit, connect=limit, read=limit, write=limit, pool=limit)
