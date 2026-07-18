from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

# Tests may use SQLite only as an explicit, test-only fast feedback database.
# PostgreSQL remains the runtime/integration contract and is exercised in CI.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_SQLITE_TESTS", "true")
TEST_DB_PATH = Path(tempfile.gettempdir()) / "crowdcue-pytest.sqlite3"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}")
os.environ.setdefault("ENABLE_DEMO_FAULT_INJECTION", "true")
os.environ.setdefault("GEMINI_API_KEY", "")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.config import settings
from backend.app.database import Base
from backend.app.database import engine as app_engine
from backend.app.database import get_db
from backend.app.persistence import models as _models  # noqa: F401

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

test_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)


@event.listens_for(test_engine.sync_engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def reset_test_schema() -> None:
    # SQLite cannot order DROP statements across the intentional circular
    # preflight/candidate foreign keys. Disable enforcement only for schema
    # replacement; every test transaction runs with enforcement enabled.
    async with test_engine.connect() as connection:
        await connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
        await connection.commit()
        await connection.exec_driver_sql("PRAGMA foreign_keys=ON")


@pytest.fixture(scope="session", autouse=True)
def setup_test_db() -> Generator[None, None, None]:
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    loop = asyncio.new_event_loop()

    async def run_setup() -> None:
        await reset_test_schema()

    loop.run_until_complete(run_setup())
    yield

    async def run_teardown() -> None:
        async with test_engine.connect() as connection:
            await connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            await connection.run_sync(Base.metadata.drop_all)
            await connection.commit()
        await test_engine.dispose()
        await app_engine.dispose()

    loop.run_until_complete(run_teardown())
    loop.close()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    # Each test receives a fresh schema so service-level commits are real and an
    # expected command failure cannot roll back previously completed API calls.
    await reset_test_schema()
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from backend.app.main import app

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()
