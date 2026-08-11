"""Backward-compatible re-exports of least-privilege domain HTTP clients.

Prefer importing from ``mcps.company_tools.clients.incidents`` or
``.inventory`` in new code so each tool only sees its own operations.
"""

from __future__ import annotations

from mcps.company_tools.clients.base import (  # noqa: F401
    DEFAULT_API_BASE,
    HTTP_TIMEOUT_SECONDS,
    api_base,
    build_timeout,
)
from mcps.company_tools.clients.incidents import (  # noqa: F401
    INCIDENT_BY_ID_PATH,
    INCIDENT_STATUS_PATH,
    INCIDENTS_COLLECTION_PATH,
    create_incident,
    get_incident,
    update_incident_status,
)
from mcps.company_tools.clients.inventory import (  # noqa: F401
    PRODUCT_BY_ID_PATH,
    PRODUCTS_COLLECTION_PATH,
    get_product,
    list_products,
)
