"""SQLAlchemy async engine and session factory.

Creates the async engine from DATABASE_URL and provides:
  - ``async_engine``:   the SQLAlchemy async engine instance
  - ``AsyncSessionLocal``: an async sessionmaker for dependency injection
  - ``get_db()``:       a FastAPI dependency that yields a scoped session

Uses ``asyncpg`` as the async Postgres driver.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

async_engine = create_async_engine(
    settings.database_url,
    # SQL values may contain profile data; LOG_LEVEL must never enable their export.
    echo=False,
    hide_parameters=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
