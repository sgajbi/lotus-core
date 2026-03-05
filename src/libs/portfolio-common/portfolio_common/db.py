# libs/portfolio-common/portfolio_common/db.py
import os

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from .config import POSTGRES_DB, POSTGRES_HOST, POSTGRES_PASSWORD, POSTGRES_PORT, POSTGRES_USER


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

    # Ensure the URL does not use an async driver
    if "asyncpg" in url:
        url = url.replace("postgresql+asyncpg://", "postgresql://")

    return url

engine = create_engine(get_sync_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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

    # Ensure the URL uses the asyncpg driver scheme
    if "postgresql+asyncpg://" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")

    return url

async_engine = create_async_engine(
    get_async_database_url(),
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

async def get_async_db_session() -> AsyncSession:
    """
    An async dependency that provides an SQLAlchemy AsyncSession.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()