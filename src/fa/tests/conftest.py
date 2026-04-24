"""Pytest configuration for fa tests."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from fa.app import app
from fa.models import SQLModel
from fa.session import session_manager

# Test database URL (SQLite in-memory)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine):
    """Create a test database session."""
    async_session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session_maker() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession):
    """Create an async test client."""
    # Patch the db engine with test engine
    import fa.db
    import fa.routes.ritm

    original_engine = fa.db.engine
    fa.db.engine = db_session.bind
    fa.routes.ritm.engine = db_session.bind

    # Create a test session
    session_id = session_manager.create(username="testuser", password="testpass")

    # Use ASGI transport for FastAPI testing
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Set session cookie
        client.cookies.set("session_id", session_id)
        yield client

    # Cleanup
    session_manager.delete(session_id)
    fa.db.engine = original_engine
    fa.routes.ritm.engine = original_engine
