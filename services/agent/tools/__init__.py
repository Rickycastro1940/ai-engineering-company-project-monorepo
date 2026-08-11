"""External tools for the Brasaland support agent.

Ticket status for the LangGraph graph goes **only** through the MCP client
(``lookup_ticket_via_mcp`` / ``langchain-mcp-adapters``). The direct HTTP
``lookup_ticket`` helper is deprecated and is **not** re-exported here, so the
agent package has a single path to the Incidents Manager.
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
    TICKET_FALLBACK_MESSAGE,
    TICKET_LOOKUP_TIMEOUT_SECONDS,
    build_ticket_http_timeout,
    format_ticket_answer,
    honest_ticket_fallback_answer,
)

__all__ = [
    "INVENTORY_LOOKUP_TIMEOUT_SECONDS",
    "InventoryLookupInput",
    "InventoryLookupOutput",
    "InventoryProductRecord",
    "TICKET_FALLBACK_MESSAGE",
    "TICKET_LOOKUP_TIMEOUT_SECONDS",
    "TicketLookupInput",
    "TicketLookupOutput",
    "TicketRecord",
    "build_ticket_http_timeout",
    "format_ticket_answer",
    "honest_ticket_fallback_answer",
    "lookup_inventory",
    "lookup_ticket_via_mcp",
]
