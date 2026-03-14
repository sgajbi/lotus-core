import importlib

import pytest
import sqlalchemy
import sqlalchemy.ext.asyncio as sa_async
from portfolio_common.db import get_async_database_url, get_sync_database_url


class _FakeSyncSession:
    pass


class _FakeAsyncSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeFactory:
    def __init__(self, session_cls):
        self._session_cls = session_cls

    def __call__(self):
        return self._session_cls()


def test_db_module_import_does_not_create_engines(monkeypatch):
    sync_calls = []
    async_calls = []

    def _fake_create_engine(*args, **kwargs):
        sync_calls.append((args, kwargs))
        return object()

    def _fake_create_async_engine(*args, **kwargs):
        async_calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(sqlalchemy, "create_engine", _fake_create_engine)
    monkeypatch.setattr(sa_async, "create_async_engine", _fake_create_async_engine)

    import portfolio_common.db as db_module

    reloaded = importlib.reload(db_module)

    assert reloaded._engine is None
    assert reloaded._async_engine is None
    assert sync_calls == []
    assert async_calls == []


def test_sessionlocal_creates_sync_engine_lazily(monkeypatch):
    sync_calls = []

    def _fake_create_engine(*args, **kwargs):
        sync_calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(sqlalchemy, "create_engine", _fake_create_engine)
    monkeypatch.setattr(
        sqlalchemy.orm,
        "sessionmaker",
        lambda **kwargs: _FakeFactory(_FakeSyncSession),
    )

    import portfolio_common.db as db_module

    reloaded = importlib.reload(db_module)
    session = reloaded.SessionLocal()

    assert isinstance(session, _FakeSyncSession)
    assert len(sync_calls) == 1


def test_sync_database_url_normalizes_postgres_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/dbname")
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)

    assert get_sync_database_url() == "postgresql://user:pass@host:5432/dbname"


def test_async_database_url_normalizes_postgres_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/dbname")
    monkeypatch.delenv("HOST_DATABASE_URL", raising=False)

    assert get_async_database_url() == "postgresql+asyncpg://user:pass@host:5432/dbname"


@pytest.mark.asyncio
async def test_asyncsessionlocal_creates_async_engine_lazily(monkeypatch):
    async_calls = []

    def _fake_create_async_engine(*args, **kwargs):
        async_calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(sa_async, "create_async_engine", _fake_create_async_engine)
    monkeypatch.setattr(
        sa_async,
        "async_sessionmaker",
        lambda **kwargs: _FakeFactory(_FakeAsyncSession),
    )

    import portfolio_common.db as db_module

    reloaded = importlib.reload(db_module)

    async with reloaded.AsyncSessionLocal() as session:
        assert isinstance(session, _FakeAsyncSession)

    assert len(async_calls) == 1
