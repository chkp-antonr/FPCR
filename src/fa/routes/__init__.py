"""API route modules."""

from .auth import router as auth_router
from .domains import router as domains_router
from .health import router as health_router
from .packages import router as packages_router
from .ritm import router as ritm_router

__all__ = [
    "auth_router",
    "domains_router",
    "health_router",
    "packages_router",
    "ritm_router",
]
