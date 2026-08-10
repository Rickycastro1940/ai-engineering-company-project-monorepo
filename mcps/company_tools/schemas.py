"""Discovery schemas for company-tools MCP (--help equivalent).

These Pydantic models are published through MCP ``tools/list`` so an external
agent can understand inputs and outputs without reading source code.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

IncidentAction = Literal["create", "update", "get_status"]
InventoryReadAction = Literal["query", "get", "list", "read"]


class IncidentTicket(BaseModel):
    """One Brasaland incident ticket as returned by the Incidents Manager."""

    model_config = ConfigDict(extra="allow")

    incident_id: str = Field(description="Ticket id, e.g. BRS-000002.")
    date: str | None = Field(default=None, description="Incident date YYYY-MM-DD.")
    location_id: str | None = Field(default=None, description="Location id, e.g. COL-01.")
    category: str | None = Field(
        default=None,
        description=(
            "Category from Incidents Manager: EQUIPAMIENTO | ABASTECIMIENTO | "
            "QUEJA_CLIENTE | CALIDAD_ALIMENTO | PERSONAL."
        ),
    )
    description: str | None = Field(default=None, description="Incident description.")
    status: str | None = Field(
        default=None,
        description="Lifecycle status: ABIERTO | CERRADO | DESCARTADO.",
    )
    customer_id: str | None = Field(default=None, description="Optional customer id.")
    satisfaction_score: float | None = Field(default=None, description="Optional score.")
    reporter_id: str | None = Field(default=None, description="Optional reporter id.")
    source: str | None = Field(
        default="incident_manager",
        description="Always incident_manager for live backend data.",
    )


class ManageIncidentTicketOutput(BaseModel):
    """Structured result of ``manage_incident_ticket``."""

    model_config = ConfigDict(extra="allow")

    ok: bool = Field(description="True when the Incidents Manager call succeeded.")
    action: str | None = Field(
        default=None,
        description="Echo of the requested action: create | update | get_status.",
    )
    ticket: IncidentTicket | None = Field(
        default=None,
        description="Ticket payload from the live Incidents Manager on success.",
    )
    error_code: str | None = Field(
        default=None,
        description=(
            "Machine-readable failure code when ok is false — never the generic "
            "string 'error'. Auth: AUTH_MISSING_TOKEN | AUTH_INVALID_TOKEN | "
            "AUTH_INVALID_AUDIENCE | AUTH_INSUFFICIENT_SCOPE. "
            "Validation: VALIDATION_ERROR | LIFECYCLE_ERROR | NOT_FOUND. "
            "Other: INVENTORY_WRITE_FORBIDDEN | UPSTREAM_ERROR | UNHANDLED_ERROR. "
            "See mcps/company_tools/ERRORS.md."
        ),
    )
    message: str | None = Field(default=None, description="Human-readable error detail.")
    tool: str | None = Field(default=None, description="Tool name on error payloads.")
    details: dict[str, Any] | None = Field(default=None, description="Optional error details.")
    duration_ms: int | None = Field(default=None, description="Tool latency in milliseconds.")


class InventoryProduct(BaseModel):
    """One product row from the inventory manager (products.csv-backed)."""

    model_config = ConfigDict(extra="allow")

    product_id: str = Field(description="Product id, e.g. '1'.")
    name: str | None = Field(default=None, description="Product display name.")
    quantity: int | None = Field(default=None, description="On-hand quantity.")
    unit: str | None = Field(default=None, description="Unit of measure, e.g. kg.")
    source: str | None = Field(
        default="inventory_manager",
        description="Always inventory_manager for live backend data.",
    )


class QueryInventoryOutput(BaseModel):
    """Structured result of ``query_inventory`` (read-only)."""

    model_config = ConfigDict(extra="allow")

    ok: bool = Field(description="True when the inventory query succeeded.")
    products: list[InventoryProduct] | None = Field(
        default=None,
        description="Matching products from GET /inventory/products.",
    )
    message: str | None = Field(
        default=None,
        description="Optional note (e.g. no matches) or error text.",
    )
    error_code: str | None = Field(
        default=None,
        description=(
            "Machine-readable failure code when ok is false — never the generic "
            "string 'error'. Write attempts → INVENTORY_WRITE_FORBIDDEN. "
            "Auth: AUTH_MISSING_TOKEN | AUTH_INVALID_TOKEN | AUTH_INSUFFICIENT_SCOPE. "
            "Validation: VALIDATION_ERROR | NOT_FOUND. "
            "Other: UPSTREAM_ERROR | UNHANDLED_ERROR. See ERRORS.md."
        ),
    )
    tool: str | None = Field(default=None, description="Tool name on error payloads.")
    details: dict[str, Any] | None = Field(
        default=None,
        description="Optional details (e.g. rejected write fields).",
    )
    duration_ms: int | None = Field(default=None, description="Tool latency in milliseconds.")
