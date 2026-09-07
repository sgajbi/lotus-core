"""PostgreSQL proof for tenant-scoped benchmark assignment resolution."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime

import pytest
from portfolio_common.database_models import Portfolio, PortfolioBenchmarkAssignment
from portfolio_common.database_runtime_profile import DatabasePoolMode
from portfolio_common.db import create_async_database_engine
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.services.query_control_plane_service.app.infrastructure import (
    benchmark_assignment_sources,
)

pytestmark = pytest.mark.asyncio

PORTFOLIO_ID = "ISSUE1095_BENCHMARK_TENANT"
TENANT_ID = "TENANT_1095"


def _async_database_url() -> str:
    database_url = os.getenv("HOST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL URL is required for benchmark tenant integration proof")
    return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


async def test_benchmark_assignment_is_visible_only_to_owning_tenant() -> None:
    engine = create_async_database_engine(
        runtime_identity="lotus-core-test",
        database_url=_async_database_url(),
        pool_mode=DatabasePoolMode.NULL,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with sessions() as session:
            await session.execute(
                delete(PortfolioBenchmarkAssignment).where(
                    PortfolioBenchmarkAssignment.portfolio_id == PORTFOLIO_ID
                )
            )
            await session.execute(delete(Portfolio).where(Portfolio.portfolio_id == PORTFOLIO_ID))
            session.add(
                Portfolio(
                    tenant_id=TENANT_ID,
                    portfolio_id=PORTFOLIO_ID,
                    base_currency="SGD",
                    open_date=date(2026, 1, 1),
                    risk_exposure="BALANCED",
                    investment_time_horizon="LONG_TERM",
                    portfolio_type="discretionary",
                    booking_center_code="Singapore",
                    client_id="ISSUE1095_CLIENT",
                    is_leverage_allowed=False,
                    status="active",
                )
            )
            session.add(
                PortfolioBenchmarkAssignment(
                    portfolio_id=PORTFOLIO_ID,
                    benchmark_id="BMK_ISSUE1095",
                    effective_from=date(2026, 1, 1),
                    assignment_source="integration_test",
                    assignment_status="active",
                    assignment_recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
                    assignment_version=1,
                )
            )
            await session.commit()

            reader = benchmark_assignment_sources.SqlAlchemyBenchmarkAssignmentReader(session)
            owned = await reader.resolve(
                portfolio_id=PORTFOLIO_ID,
                tenant_id=TENANT_ID,
                as_of_date=date(2026, 6, 30),
            )
            foreign = await reader.resolve(
                portfolio_id=PORTFOLIO_ID,
                tenant_id="TENANT_OTHER",
                as_of_date=date(2026, 6, 30),
            )

            assert owned is not None
            assert owned.benchmark_id == "BMK_ISSUE1095"
            assert foreign is None
    finally:
        async with sessions() as session:
            await session.execute(
                delete(PortfolioBenchmarkAssignment).where(
                    PortfolioBenchmarkAssignment.portfolio_id == PORTFOLIO_ID
                )
            )
            await session.execute(delete(Portfolio).where(Portfolio.portfolio_id == PORTFOLIO_ID))
            await session.commit()
        await engine.dispose()
