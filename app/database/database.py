from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base


class Database:
    """Async SQLAlchemy unit-of-work factory for SQLite now and PostgreSQL later."""

    def __init__(self, database_url: str) -> None:
        self._ensure_sqlite_parent_directory(database_url)
        self.engine = create_async_engine(database_url, pool_pre_ping=True)
        if database_url.startswith("sqlite"):
            event.listen(self.engine.sync_engine, "connect", self._enable_sqlite_foreign_keys)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        session = self.session_factory()
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def dispose(self) -> None:
        await self.engine.dispose()

    @staticmethod
    def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @staticmethod
    def _ensure_sqlite_parent_directory(database_url: str) -> None:
        prefix = "sqlite+aiosqlite:///"
        if not database_url.startswith(prefix) or database_url.endswith(":memory:"):
            return
        raw_path = database_url.removeprefix(prefix)
        if raw_path and not raw_path.startswith("/"):
            Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
