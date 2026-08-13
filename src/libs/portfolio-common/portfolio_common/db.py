# libs/portfolio-common/portfolio_common/db.py
import os
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from .config import POSTGRES_DB, POSTGRES_HOST, POSTGRES_PASSWORD, POSTGRES_PORT, POSTGRES_USER
from .connection_security import validate_database_url_security
from .database_runtime_identity import async_database_connect_args, sync_database_connect_args

_LEGACY_POSTGRES_SCHEME = "postgres://"
_SYNC_POSTGRES_SCHEME = "postgresql://"
_ASYNC_POSTGRES_SCHEME = "postgresql+asyncpg://"


def _normalize_database_url_scheme(url: str, *, async_mode: bool) -> str:
    normalized_url = _normalize_legacy_postgres_scheme(url)
    if async_mode:
        return _normalize_async_database_url_scheme(normalized_url)
    return _normalize_sync_database_url_scheme(normalized_url)


def _normalize_legacy_postgres_scheme(url: str) -> str:
    if url.startswith(_LEGACY_POSTGRES_SCHEME):
        return _replace_database_url_scheme(url, _LEGACY_POSTGRES_SCHEME, _SYNC_POSTGRES_SCHEME)
    return url


def _normalize_async_database_url_scheme(url: str) -> str:
    if url.startswith(_SYNC_POSTGRES_SCHEME):
        return _replace_database_url_scheme(url, _SYNC_POSTGRES_SCHEME, _ASYNC_POSTGRES_SCHEME)
    return url


def _normalize_sync_database_url_scheme(url: str) -> str:
    if url.startswith(_ASYNC_POSTGRES_SCHEME):
        return _replace_database_url_scheme(url, _ASYNC_POSTGRES_SCHEME, _SYNC_POSTGRES_SCHEME)
    return url


def _replace_database_url_scheme(url: str, source_scheme: str, target_scheme: str) -> str:
    return target_scheme + url[len(source_scheme) :]


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

    normalized_url = _normalize_database_url_scheme(url, async_mode=False)
    validate_database_url_security(normalized_url, service_name="lotus-core")
    return normalized_url


_engine = None
_session_factory = None
_async_engine = None
_async_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_sync_database_url(),
            pool_pre_ping=True,
            connect_args=sync_database_connect_args(),
        )
    return _engine


def create_sync_database_engine(
    *,
    runtime_identity: str,
    database_url: str | None = None,
    **engine_options: Any,
) -> Engine:
    """Create a standalone synchronous engine with governed connection attribution."""

    normalized_url = _normalize_database_url_scheme(
        database_url or get_sync_database_url(),
        async_mode=False,
    )
    validate_database_url_security(normalized_url, service_name=runtime_identity)
    return create_engine(
        normalized_url,
        pool_pre_ping=True,
        connect_args=sync_database_connect_args(explicit_identity=runtime_identity),
        **engine_options,
    )


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

    normalized_url = _normalize_database_url_scheme(url, async_mode=True)
    validate_database_url_security(normalized_url, service_name="lotus-core")
    return normalized_url


def get_async_engine():
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            get_async_database_url(),
            pool_pre_ping=True,
            connect_args=async_database_connect_args(),
        )
    return _async_engine


def create_async_database_engine(
    *,
    runtime_identity: str,
    database_url: str | None = None,
    **engine_options: Any,
) -> AsyncEngine:
    """Create a standalone asynchronous engine with governed connection attribution."""

    normalized_url = _normalize_database_url_scheme(
        database_url or get_async_database_url(),
        async_mode=True,
    )
    validate_database_url_security(normalized_url, service_name=runtime_identity)
    return create_async_engine(
        normalized_url,
        pool_pre_ping=True,
        connect_args=async_database_connect_args(explicit_identity=runtime_identity),
        **engine_options,
    )


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
