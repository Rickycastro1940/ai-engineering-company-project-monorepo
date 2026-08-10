"""MCP client for Incidents Manager tools — replaces direct HTTP ticket lookup.

The LangGraph ``lookup_ticket`` node must call the company-tools MCP server via
``langchain-mcp-adapters``. Direct ``ticket_lookup.lookup_ticket`` HTTP calls
are deprecated for graph use.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from services.agent.tools.contracts import (
    TicketLookupInput,
    TicketLookupOutput,
    TicketRecord,
)
from services.agent.tools.ticket_lookup import (
    TICKET_FALLBACK_MESSAGE,
    TICKET_LOOKUP_TIMEOUT_SECONDS,
)

DEFAULT_MCP_URL = "http://127.0.0.1:3001/mcp"
MCP_SERVER_NAME = "company_tools"


def _mcp_url() -> str:
    return (os.getenv("MCP_SERVER_URL") or DEFAULT_MCP_URL).rstrip("/")


def _access_token() -> str:
    token = os.getenv("MCP_ACCESS_TOKEN") or ""
    if token:
        return token
    # Dev convenience: mint from local issuer when MCP_ACCESS_TOKEN is unset.
    issuer = (os.getenv("MCP_AUTH_ISSUER") or "http://127.0.0.1:3002").rstrip("/")
    try:
        import httpx

        response = httpx.get(
            f"{issuer}/token",
            params={"client_id": os.getenv("MCP_CLIENT_ID", "agent-support-prod")},
            timeout=5.0,
        )
        response.raise_for_status()
        return str(response.json().get("access_token") or "")
    except Exception:  # noqa: BLE001
        return ""


def _record_from_ticket(payload: dict[str, Any]) -> TicketRecord:
    return TicketRecord(
        incident_id=str(payload.get("incident_id") or ""),
        date=str(payload.get("date") or ""),
        location_id=payload.get("location_id"),
        category=str(payload.get("category") or ""),
        description=str(payload.get("description") or ""),
        status=str(payload.get("status") or ""),
        customer_id=payload.get("customer_id"),
        satisfaction_score=payload.get("satisfaction_score"),
        reporter_id=payload.get("reporter_id"),
        source=str(payload.get("source") or "incident_manager"),
    )


def _failed(started: float, *, error: str, message: str) -> TicketLookupOutput:
    return TicketLookupOutput(
        ok=False,
        tickets=[],
        error=error,  # type: ignore[arg-type]
        message=message,
        duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
    )


def _parse_tool_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"ok": False, "message": raw}
    if isinstance(raw, list):
        # LangChain tool messages sometimes return list of content blocks.
        texts = []
        for block in raw:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text") or "")
            elif isinstance(block, str):
                texts.append(block)
        joined = "\n".join(texts).strip()
        if joined:
            try:
                parsed = json.loads(joined)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {"ok": False, "message": joined}
    return {"ok": False, "message": str(raw)}


async def _ainvoke_manage_incident(arguments: dict[str, Any]) -> dict[str, Any]:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    token = _access_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    client = MultiServerMCPClient(
        {
            MCP_SERVER_NAME: {
                "transport": "streamable_http",
                "url": _mcp_url(),
                "headers": headers,
            }
        }
    )
    tools = await client.get_tools(server_name=MCP_SERVER_NAME)
    tool = next((t for t in tools if t.name == "manage_incident_ticket"), None)
    if tool is None:
        return {
            "ok": False,
            "error_code": "UPSTREAM_ERROR",
            "message": "manage_incident_ticket not listed by MCP discovery",
        }
    result = await tool.ainvoke(arguments)
    return _parse_tool_payload(result)


def lookup_ticket_via_mcp(
    query: TicketLookupInput | dict[str, Any],
    *,
    timeout_seconds: float = TICKET_LOOKUP_TIMEOUT_SECONDS,
) -> TicketLookupOutput:
    """Resolve ticket status through the MCP server (no direct Incidents HTTP)."""
    started = time.perf_counter()
    try:
        if isinstance(query, dict):
            inp = TicketLookupInput.model_validate(query)
        else:
            inp = query
    except Exception as exc:  # noqa: BLE001
        return _failed(
            started,
            error="invalid_input",
            message=f"Invalid ticket lookup input: {exc}",
        )

    if not inp.ticket_id:
        return _failed(
            started,
            error="invalid_input",
            message="ticket_id is required when calling the MCP incidents tool from the agent",
        )

    arguments = {"action": "get_status", "ticket_id": inp.ticket_id.strip()}

    try:
        payload = asyncio.run(
            asyncio.wait_for(_ainvoke_manage_incident(arguments), timeout=timeout_seconds + 2)
        )
    except TimeoutError:
        return _failed(started, error="timeout", message=TICKET_FALLBACK_MESSAGE)
    except Exception:  # noqa: BLE001
        return _failed(started, error="service_error", message=TICKET_FALLBACK_MESSAGE)

    if not payload.get("ok"):
        error_code = str(payload.get("error_code") or "")
        if error_code in {"AUTH_MISSING_TOKEN", "AUTH_INVALID_TOKEN", "AUTH_INSUFFICIENT_SCOPE"}:
            return _failed(started, error="auth_error", message=TICKET_FALLBACK_MESSAGE)
        if error_code == "NOT_FOUND":
            return _failed(
                started,
                error="not_found",
                message=(
                    f"{TICKET_FALLBACK_MESSAGE} "
                    f"Ticket {inp.ticket_id} was not found in the incident manager."
                ),
            )
        return _failed(started, error="service_error", message=TICKET_FALLBACK_MESSAGE)

    ticket_payload = payload.get("ticket") or {}
    ticket = _record_from_ticket(ticket_payload if isinstance(ticket_payload, dict) else {})
    return TicketLookupOutput(
        ok=True,
        tickets=[ticket],
        duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
    )
