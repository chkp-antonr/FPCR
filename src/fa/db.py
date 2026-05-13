"""Database infrastructure for the FastAPI application."""

import logging
import sqlite3

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel

from .config import settings

logger = logging.getLogger(__name__)

# Shared engine for CPAIOPS
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"timeout": 30},
)


@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_connection: sqlite3.Connection, _connection_record: object) -> None:
    """Configure SQLite for concurrent reads during cache refreshes."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")  # 10 seconds for lock contention (with retries)
    cursor.close()


async def dispose_engine() -> None:
    """Dispose the database engine."""
    await engine.dispose()


async def create_ritm_flow_tables() -> None:
    """Create new tables for RITM flow tracking."""
    flow_tables = SQLModel.metadata.tables
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: SQLModel.metadata.create_all(
                    sync_conn,
                    tables=[
                        flow_tables["ritm_created_objects"],
                        flow_tables["ritm_created_rules"],
                        flow_tables["ritm_verification"],
                        flow_tables["ritm_editors"],
                        flow_tables["ritm_reviewers"],
                        flow_tables["ritm_evidence_sessions"],
                    ],
                )
            )
        logger.info("RITM flow tables created successfully")
    except InvalidRequestError as exc:
        # Hot reload: tables already defined, drop specific tables and recreate
        logger.warning(f"InvalidRequestError in create_ritm_flow_tables (hot reload): {exc}")
        logger.info("Dropping RITM flow tables and recreating...")
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: SQLModel.metadata.drop_all(
                    sync_conn,
                    tables=[
                        flow_tables["ritm_created_objects"],
                        flow_tables["ritm_created_rules"],
                        flow_tables["ritm_verification"],
                        flow_tables["ritm_editors"],
                        flow_tables["ritm_reviewers"],
                        flow_tables["ritm_evidence_sessions"],
                    ],
                )
            )
            await conn.run_sync(
                lambda sync_conn: SQLModel.metadata.create_all(
                    sync_conn,
                    tables=[
                        flow_tables["ritm_created_objects"],
                        flow_tables["ritm_created_rules"],
                        flow_tables["ritm_verification"],
                        flow_tables["ritm_editors"],
                        flow_tables["ritm_reviewers"],
                        flow_tables["ritm_evidence_sessions"],
                    ],
                )
            )
        logger.info("RITM flow tables recreated successfully after hot reload")
