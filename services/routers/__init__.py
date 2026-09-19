"""API routers mounted by the Brasaland FastAPI app."""

from services.routers.inventory import router as inventory_router

__all__ = ["inventory_router"]
