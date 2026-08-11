"""Prove governed runtime identity reaches PostgreSQL through both Core drivers."""

from __future__ import annotations

import pytest
from portfolio_common.database_runtime_identity import (
    async_database_connect_args,
    sync_database_connect_args,
)
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine


def test_sync_database_connection_publishes_governed_application_name(
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SERVICE_NAME", "query-service")
    engine = create_engine(
        db_engine.url,
        connect_args=sync_database_connect_args(),
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
    async_url = db_engine.url.set(drivername="postgresql+asyncpg")
    engine = create_async_engine(
        async_url,
        connect_args=async_database_connect_args(),
    )
    try:
        async with engine.connect() as connection:
            application_name = await connection.scalar(
                text("SELECT current_setting('application_name')")
            )
    finally:
        await engine.dispose()

    assert application_name == "portfolio-derived-state"
