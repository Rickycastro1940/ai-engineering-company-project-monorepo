"""Read-only inventory query tool — writes are explicitly rejected."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mcps.company_tools import http_clients
from mcps.company_tools.errors import ErrorCode, error_payload

TOOL_NAME = "query_inventory"
READ_ACTIONS = frozenset({"query", "get", "list", "read"})
WRITE_ACTIONS = frozenset({"update", "create", "delete", "write", "patch", "put"})


def _blank_to_none(value: str | None) -> str | None:
    """MCP clients often send '' for unused optional string fields."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class QueryInventoryInput(BaseModel):
    """Input schema published via MCP discovery (self-explanatory)."""

    model_config = ConfigDict(extra="forbid")

    action: str | None = Field(
        default="query",
        description=(
            "Read-only action. Allowed: query | get | list | read. "
            "Any write-oriented action (update, create, delete, write, patch, put) "
            "is rejected with INVENTORY_WRITE_FORBIDDEN."
        ),
    )
    product_id: str | None = Field(
        default=None,
        description="Optional product id from products.csv (e.g. '1').",
    )
    name_contains: str | None = Field(
        default=None,
        description="Optional case-insensitive name substring filter.",
    )
    # Explicit write-oriented fields — a non-empty value triggers rejection.
    quantity: int | None = Field(
        default=None,
        description="WRITE FIELD — not permitted. Setting this triggers INVENTORY_WRITE_FORBIDDEN.",
    )
    delta: int | None = Field(
        default=None,
        description="WRITE FIELD — not permitted. Setting this triggers INVENTORY_WRITE_FORBIDDEN.",
    )
    unit: str | None = Field(
        default=None,
        description="WRITE FIELD — not permitted. Setting this triggers INVENTORY_WRITE_FORBIDDEN.",
    )
    name: str | None = Field(
        default=None,
        description="WRITE FIELD for create/rename — not permitted on this read-only tool.",
    )

    @field_validator("action", "product_id", "name_contains", "unit", "name", mode="before")
    @classmethod
    def _normalize_blank_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _blank_to_none(value)
        return value


def _is_write_attempt(inp: QueryInventoryInput) -> bool:
    action = (inp.action or "query").strip().casefold()
    if action in WRITE_ACTIONS or action not in READ_ACTIONS:
        return True
    # Only non-None write fields count — blank strings are normalized away above.
    if inp.quantity is not None or inp.delta is not None:
        return True
    if inp.unit is not None or inp.name is not None:
        return True
    return False


def _product_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": payload.get("product_id"),
        "name": payload.get("name"),
        "quantity": payload.get("quantity"),
        "unit": payload.get("unit"),
        "source": payload.get("source", "inventory_manager"),
    }


def query_inventory(
    *,
    action: str | None = "query",
    product_id: str | None = None,
    name_contains: str | None = None,
    quantity: int | None = None,
    delta: int | None = None,
    unit: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Query live inventory. Explicitly rejects any write attempt."""
    try:
        inp = QueryInventoryInput(
            action=action,
            product_id=product_id,
            name_contains=name_contains,
            quantity=quantity,
            delta=delta,
            unit=unit,
            name=name,
        )
    except Exception as exc:  # noqa: BLE001
        return error_payload(
            ErrorCode.VALIDATION_ERROR,
            f"Invalid query_inventory input: {exc}",
            tool=TOOL_NAME,
        )

    if _is_write_attempt(inp):
        return error_payload(
            ErrorCode.INVENTORY_WRITE_FORBIDDEN,
            "Inventory tool is read-only. Write operations are not permitted on this MCP server.",
            tool=TOOL_NAME,
            details={
                "action": inp.action or "query",
                "rejected_fields": {
                    k: v
                    for k, v in {
                        "quantity": inp.quantity,
                        "delta": inp.delta,
                        "unit": inp.unit,
                        "name": inp.name,
                    }.items()
                    if v is not None
                },
            },
        )

    if inp.product_id and not inp.name_contains:
        response = http_clients.get_product(inp.product_id)
        if response.status_code == 404:
            return error_payload(
                ErrorCode.NOT_FOUND,
                f"Product {inp.product_id} was not found in the inventory manager.",
                tool=TOOL_NAME,
            )
        if response.status_code >= 400:
            return error_payload(
                ErrorCode.UPSTREAM_ERROR,
                f"Inventory manager returned HTTP {response.status_code}.",
                tool=TOOL_NAME,
            )
        return {
            "ok": True,
            "products": [_product_from_payload(response.json())],
        }

    response = http_clients.list_products(
        product_id=inp.product_id,
        name_contains=inp.name_contains,
    )
    if response.status_code >= 400:
        return error_payload(
            ErrorCode.UPSTREAM_ERROR,
            f"Inventory manager returned HTTP {response.status_code}.",
            tool=TOOL_NAME,
        )
    payload = response.json()
    items = payload if isinstance(payload, list) else payload.get("products", [])
    products = [_product_from_payload(item) for item in items if isinstance(item, dict)]
    return {
        "ok": True,
        "products": products,
        "message": None if products else "No products matched those filters.",
    }
