"""
PostgreSQL async connection pool using SQLAlchemy 2.x + asyncpg.
"""
from __future__ import annotations

import os
import logging
from typing import AsyncGenerator

from sqlalchemy import (
    Column, String, Text, Float, Integer,
    DateTime, ForeignKey, func, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/spiderdb",
    )


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

class MissionORM(Base):
    __tablename__ = "missions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    config = Column(JSONB, nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    job_total = Column(Integer, default=0)
    job_done = Column(Integer, default=0)
    job_failed = Column(Integer, default=0)


class RawEventORM(Base):
    __tablename__ = "raw_events"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id"), nullable=True)
    target_url = Column(Text, nullable=True)
    source_type = Column(Text, nullable=True)
    raw_content = Column(Text, nullable=True)
    captured_at = Column(DateTime(timezone=True), server_default=func.now())


class ScrapedDataORM(Base):
    __tablename__ = "scraped_data"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id"), nullable=True)
    target_url = Column(Text, nullable=True)
    extracted_fields = Column(JSONB, nullable=True)
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Engine / session management
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Initialise the async engine and session factory."""
    global _engine, _session_factory
    url = get_database_url()
    _engine = create_async_engine(
        url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False,
    )
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("Database engine initialised: %s", url.split("@")[-1])


async def close_db() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency-injection helper for FastAPI routes."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised; call init_db() first.")
    async with _session_factory() as session:
        yield session


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialised; call init_db() first.")
    return _session_factory
