"""External tools for the Brasaland support agent (Part 2).

Each tool has a single responsibility and a typed input/output contract.
"""

from services.agent.tools.contracts import (
    TicketLookupInput,
    TicketLookupOutput,
    TicketRecord,
)
from services.agent.tools.ticket_lookup import (
    TICKET_LOOKUP_TIMEOUT_SECONDS,
    build_ticket_http_timeout,
    lookup_ticket,
)

__all__ = [
    "TICKET_LOOKUP_TIMEOUT_SECONDS",
    "TicketLookupInput",
    "TicketLookupOutput",
    "TicketRecord",
    "build_ticket_http_timeout",
    "lookup_ticket",
]
