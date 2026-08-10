"""External tools for the Brasaland support agent.

Ticket status for the LangGraph graph goes through the MCP client
(``mcp_incidents``). Direct ``lookup_ticket`` HTTP is deprecated for graph use.
"""

from services.agent.tools.contracts import (
    InventoryLookupInput,
    InventoryLookupOutput,
    InventoryProductRecord,
    TicketLookupInput,
    TicketLookupOutput,
    TicketRecord,
)
from services.agent.tools.inventory_lookup import (
    INVENTORY_LOOKUP_TIMEOUT_SECONDS,
    lookup_inventory,
)
from services.agent.tools.mcp_incidents import lookup_ticket_via_mcp
from services.agent.tools.ticket_lookup import (
    TICKET_LOOKUP_TIMEOUT_SECONDS,
    build_ticket_http_timeout,
    honest_ticket_fallback_answer,
    lookup_ticket,
)

__all__ = [
    "INVENTORY_LOOKUP_TIMEOUT_SECONDS",
    "InventoryLookupInput",
    "InventoryLookupOutput",
    "InventoryProductRecord",
    "TICKET_LOOKUP_TIMEOUT_SECONDS",
    "TicketLookupInput",
    "TicketLookupOutput",
    "TicketRecord",
    "build_ticket_http_timeout",
    "honest_ticket_fallback_answer",
    "lookup_inventory",
    "lookup_ticket",
    "lookup_ticket_via_mcp",
]
