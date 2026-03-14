# libs/portfolio-common/portfolio_common/db.py
import os

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from .config import POSTGRES_DB, POSTGRES_HOST, POSTGRES_PASSWORD, POSTGRES_PORT, POSTGRES_USER


def _normalize_database_url_scheme(url: str, *, async_mode: bool) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]

    if async_mode:
        if url.startswith("postgresql+asyncpg://"):
            return url
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url[len("postgresql://") :]
        return url

    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url[len("postgresql+asyncpg://") :]
    return url


def get_sync_database_url():
    """
    Determines the synchronous database URL.
    Prioritizes HOST_DATABASE_URL for local development/testing environments
    running on the host machine, then falls back to DATABASE_URL for
    container-to-container communication.
    """
    url = os.getenv("HOST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        # Fallback for cases where neither is set
        url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

    return _normalize_database_url_scheme(url, async_mode=False)


_engine = None
_session_factory = None
_async_engine = None
_async_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_sync_database_url(), pool_pre_ping=True)
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _session_factory


def SessionLocal():
    return get_session_factory()()


def get_db_session():
    """
    A synchronous dependency to get a SQLAlchemy database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_async_database_url():
    """
    Determines the correct async database URL, with an asyncpg driver scheme.
    Prioritizes HOST_DATABASE_URL for local development/testing, falling back
    to DATABASE_URL for containerized environments.
    """
    url = os.getenv("HOST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        # Fallback for cases where neither is set
        url = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

    return _normalize_database_url_scheme(url, async_mode=True)


def get_async_engine():
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            get_async_database_url(),
            pool_pre_ping=True,
        )
    return _async_engine


def get_async_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_async_engine(),
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _async_session_factory


def AsyncSessionLocal():
    return get_async_session_factory()()


async def get_async_db_session() -> AsyncSession:
    """
    An async dependency that provides an SQLAlchemy AsyncSession.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
