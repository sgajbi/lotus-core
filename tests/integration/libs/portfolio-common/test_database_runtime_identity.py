"""Prove governed runtime identity reaches PostgreSQL through both Core drivers."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from contextlib import contextmanager

import pytest
from portfolio_common.database_runtime_profile import (
    DATABASE_CONNECT_TIMEOUT_SECONDS_ENV,
    DATABASE_IDLE_TRANSACTION_TIMEOUT_MS_ENV,
    DATABASE_MAX_OVERFLOW_ENV,
    DATABASE_POOL_SIZE_ENV,
    DATABASE_POOL_TIMEOUT_SECONDS_ENV,
    DATABASE_STATEMENT_TIMEOUT_MS_ENV,
)
from portfolio_common.db import create_async_database_engine, create_sync_database_engine
from sqlalchemy import exc as sa_exc
from sqlalchemy import text


def _database_url(db_engine) -> str:
    return db_engine.url.render_as_string(hide_password=False)


@contextmanager
def _non_speaking_tcp_endpoint():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    release = threading.Event()

    def _accept_without_postgres_handshake() -> None:
        try:
            connection, _ = server.accept()
            with connection:
                release.wait(timeout=5)
        except OSError:
            return

    worker = threading.Thread(target=_accept_without_postgres_handshake, daemon=True)
    worker.start()
    try:
        yield server.getsockname()[1]
    finally:
        release.set()
        server.close()
        worker.join(timeout=1)


def test_sync_database_connection_publishes_governed_application_name(
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERVICE_NAME", "query-service")
    engine = create_sync_database_engine(
        runtime_identity="query-service",
        database_url=_database_url(db_engine),
    )
    try:
        with engine.connect() as connection:
            application_name = connection.scalar(text("SELECT current_setting('application_name')"))
    finally:
        engine.dispose()

    assert application_name == "query-service"


@pytest.mark.asyncio
async def test_async_database_connection_publishes_governed_application_name(
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERVICE_NAME", "portfolio-derived-state")
    engine = create_async_database_engine(
        runtime_identity="portfolio-derived-state",
        database_url=_database_url(db_engine),
    )
    try:
        async with engine.connect() as connection:
            application_name = await connection.scalar(
                text("SELECT current_setting('application_name')")
            )
    finally:
        await engine.dispose()

    assert application_name == "portfolio-derived-state"


def test_sync_connection_establishment_timeout_is_bounded_and_database_recovers(
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_CONNECT_TIMEOUT_SECONDS_ENV, "2")
    with _non_speaking_tcp_endpoint() as port:
        engine = create_sync_database_engine(
            runtime_identity="query-service",
            database_url=(f"postgresql://timeout-user:timeout-secret@127.0.0.1:{port}/timeout-db"),
        )
        started = time.monotonic()
        try:
            with pytest.raises(sa_exc.OperationalError):
                engine.connect()
        finally:
            engine.dispose()
        elapsed = time.monotonic() - started

    assert 1.8 <= elapsed <= 4.5
    with db_engine.connect() as recovered:
        assert recovered.scalar(text("SELECT 1")) == 1


@pytest.mark.asyncio
async def test_async_connection_establishment_timeout_is_bounded_and_database_recovers(
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_CONNECT_TIMEOUT_SECONDS_ENV, "2")
    with _non_speaking_tcp_endpoint() as port:
        engine = create_async_database_engine(
            runtime_identity="portfolio-derived-state",
            database_url=(f"postgresql://timeout-user:timeout-secret@127.0.0.1:{port}/timeout-db"),
        )
        started = time.monotonic()
        try:
            with pytest.raises((sa_exc.DBAPIError, TimeoutError)):
                async with engine.connect():
                    pass
        finally:
            await engine.dispose()
        elapsed = time.monotonic() - started

    assert 1.8 <= elapsed <= 4.5
    healthy_engine = create_async_database_engine(
        runtime_identity="portfolio-derived-state",
        database_url=_database_url(db_engine),
    )
    try:
        async with healthy_engine.connect() as recovered:
            assert await recovered.scalar(text("SELECT 1")) == 1
    finally:
        await healthy_engine.dispose()


def test_sync_statement_timeout_cancels_and_connection_recovers(
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_STATEMENT_TIMEOUT_MS_ENV, "100")
    engine = create_sync_database_engine(
        runtime_identity="query-service",
        database_url=_database_url(db_engine),
    )
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SHOW statement_timeout")) == "100ms"
            with pytest.raises(sa_exc.DBAPIError):
                connection.execute(text("SELECT pg_sleep(0.25)"))
            connection.rollback()
            assert connection.scalar(text("SELECT 1")) == 1
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_async_statement_timeout_cancels_and_connection_recovers(
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_STATEMENT_TIMEOUT_MS_ENV, "100")
    engine = create_async_database_engine(
        runtime_identity="portfolio-derived-state",
        database_url=_database_url(db_engine),
    )
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SHOW statement_timeout")) == "100ms"
            with pytest.raises(sa_exc.DBAPIError):
                await connection.execute(text("SELECT pg_sleep(0.25)"))
            await connection.rollback()
            assert await connection.scalar(text("SELECT 1")) == 1
    finally:
        await engine.dispose()


def test_idle_transaction_timeout_discards_dead_connection_and_recovers(
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_IDLE_TRANSACTION_TIMEOUT_MS_ENV, "1000")
    engine = create_sync_database_engine(
        runtime_identity="query-service",
        database_url=_database_url(db_engine),
    )
    try:
        with pytest.raises(sa_exc.DBAPIError):
            with engine.connect() as connection:
                assert connection.scalar(text("SHOW idle_in_transaction_session_timeout")) == "1s"
                connection.execute(text("SELECT 1"))
                time.sleep(1.25)
                connection.execute(text("SELECT 1"))

        with engine.connect() as recovered:
            assert recovered.scalar(text("SELECT 1")) == 1
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_async_idle_transaction_timeout_discards_dead_connection_and_recovers(
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_IDLE_TRANSACTION_TIMEOUT_MS_ENV, "1000")
    engine = create_async_database_engine(
        runtime_identity="portfolio-derived-state",
        database_url=_database_url(db_engine),
    )
    try:
        with pytest.raises(sa_exc.DBAPIError):
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(text("SHOW idle_in_transaction_session_timeout"))
                    == "1s"
                )
                await connection.execute(text("SELECT 1"))
                await asyncio.sleep(1.25)
                await connection.execute(text("SELECT 1"))

        async with engine.connect() as recovered:
            assert await recovered.scalar(text("SELECT 1")) == 1
    finally:
        await engine.dispose()


def test_pool_acquisition_timeout_is_bounded(
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATABASE_POOL_SIZE_ENV, "1")
    monkeypatch.setenv(DATABASE_MAX_OVERFLOW_ENV, "0")
    monkeypatch.setenv(DATABASE_POOL_TIMEOUT_SECONDS_ENV, "1")
    engine = create_sync_database_engine(
        runtime_identity="query-service",
        database_url=_database_url(db_engine),
    )
    try:
        with engine.connect() as held_connection:
            assert held_connection.scalar(text("SELECT 1")) == 1
            started = time.monotonic()
            with pytest.raises(sa_exc.TimeoutError):
                unexpected_connection = engine.connect()
                unexpected_connection.close()
            elapsed = time.monotonic() - started
    finally:
        engine.dispose()

    assert 0.8 <= elapsed <= 3.0
