"""FastAPI application factory."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from arlogi import setup_logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.exc import InvalidRequestError
from sqlmodel import SQLModel

from .cache_service import cache_service
from .config import settings
from .db import create_ritm_flow_tables, dispose_engine, engine
from .routes import auth_router, domains_router, health_router, packages_router, ritm_router
from .routes.ritm_flow import router as ritm_flow_router

# Initialize arlogi logging before importing anything else
log_level = os.getenv("LOG_LEVEL", "INFO")
cpaiops_log_level = os.getenv("CPAIOPS_LOG_LEVEL", "INFO")

setup_logging(
    level=log_level,
    module_levels={
        "cpaiops": cpaiops_log_level,
        "sqlalchemy": "WARNING",
        "sqlalchemy.engine": "WARNING",
        "sqlalchemy.pool": "WARNING",
        "aiosqlite": "WARNING",
        "httpcore": "WARNING",
        "httpx": "WARNING",
        "aiohttp": "WARNING",
        "asyncio": "WARNING",
    },
)

logger = logging.getLogger(__name__)

webui_dist = Path(__file__).resolve().parent.parent.parent / "webui" / "dist"


async def init_database() -> None:
    """Initialize database with auto-recreate on schema errors."""
    try:
        async with engine.begin() as conn:
            needs_recreate = await conn.run_sync(_cache_schema_needs_recreate)
            if needs_recreate:
                logger.warning("Legacy cache schema detected, recreating SQLModel tables")
                await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("Database initialized successfully")
    except InvalidRequestError as exc:
        # Hot reload: tables already defined in MetaData, drop and recreate
        logger.warning(
            f"InvalidRequestError (hot reload): {exc}, dropping and recreating schema..."
        )
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("Database recreated successfully after hot reload")
    except Exception as exc:
        logger.warning(f"DB init error: {exc}, recreating schema...")
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("Database recreated successfully")


def _cache_schema_needs_recreate(sync_conn: Connection) -> bool:
    """Return True when the on-disk cache schema still uses the legacy section layout."""
    inspector = inspect(sync_conn)
    table_names = set(inspector.get_table_names())
    if "cached_sections" not in table_names:
        return False

    section_columns = {column["name"] for column in inspector.get_columns("cached_sections")}
    if "package_uid" in section_columns or "domain_uid" in section_columns:
        return True

    return "cached_section_assignments" not in table_names


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    # Startup
    print(f"FPCR WebUI starting on {settings.host}:{settings.port}")

    await init_database()
    await create_ritm_flow_tables()
    logger.info("RITM flow tables created")
    yield
    # Shutdown
    await cache_service.shutdown()
    await dispose_engine()
    print("FPCR WebUI shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="FPCR WebUI",
        version="0.1.0",
        description="Firewall Policy Change Request - Web UI",
        lifespan=lifespan,
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers (must be before static mount)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(domains_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(packages_router, prefix="/api/v1")
    app.include_router(ritm_router, prefix="/api/v1")
    app.include_router(ritm_flow_router, prefix="/api/v1")

    # Root health check for load balancers
    @app.get("/health")
    async def health_root() -> dict[str, str]:
        return {"status": "ok", "service": "fpcr-webui"}

    # Mount static assets if built
    if webui_dist.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(webui_dist / "assets")),
            name="assets",
        )

        @app.get("/favicon.ico", include_in_schema=False)
        async def favicon() -> FileResponse:
            favicon_path = webui_dist / "favicon.svg"
            if favicon_path.exists():
                return FileResponse(favicon_path)
            return FileResponse(webui_dist / "index.html")

        @app.get("/favicon.svg", include_in_schema=False)
        async def favicon_svg() -> FileResponse:
            favicon_path = webui_dist / "favicon.svg"
            if favicon_path.exists():
                return FileResponse(favicon_path, media_type="image/svg+xml")
            return FileResponse(webui_dist / "index.html")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str) -> FileResponse:
            """Serve React app for all non-API routes."""
            if full_path.startswith("api/"):
                from fastapi import HTTPException

                raise HTTPException(status_code=404, detail="Not Found")
            return FileResponse(webui_dist / "index.html")

    return app


# Create app instance for uvicorn
app = create_app()
