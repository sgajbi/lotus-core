"""PostgreSQL tenant-isolation proof for DPM population and party-role reads."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime

import pytest
from portfolio_common.database_models import (
    Portfolio,
    PortfolioBenchmarkAssignment,
    PortfolioMandateBinding,
    PortfolioPartyRoleAssignment,
)
from portfolio_common.database_runtime_profile import DatabasePoolMode
from portfolio_common.db import create_async_database_engine
from portfolio_common.domain.portfolio_party_roles import (
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
)
from src.services.query_control_plane_service.app.infrastructure import (
    SqlAlchemyPortfolioManagerBookReader,
    SqlAlchemyPortfolioPartyRoleReader,
    benchmark_assignment_sources,
    dpm_portfolio_population_sources,
)
from tests.test_support.tenant import TEST_TENANT_ID

pytestmark = pytest.mark.asyncio

MIGRATED_PORTFOLIO = "ISSUE513_ROLE_PORTFOLIO"
LEGACY_PORTFOLIO = "ISSUE513_LEGACY_PORTFOLIO"
FOREIGN_PORTFOLIO = "ISSUE798_FOREIGN_ROLE_PORTFOLIO"
FOREIGN_TENANT_ID = "ISSUE798_FOREIGN_TENANT"
PORTFOLIO_MANAGER = "ISSUE513_PARTY_PM"
SOURCE_RECORD = "ISSUE513_COVERAGE_RECORD"
DPM_OWNED_PORTFOLIO = "ISSUE798_DPM_OWNED_PORTFOLIO"
DPM_FOREIGN_PORTFOLIO = "ISSUE798_DPM_FOREIGN_PORTFOLIO"
DPM_MODEL = "ISSUE798_DPM_MODEL"
BENCHMARK_AS_OF = date(2026, 7, 18)


def _async_database_url() -> str:
    database_url = (
        os.getenv("LOTUS_PARTY_ROLE_POSTGRESQL_URL")
        or os.getenv("HOST_DATABASE_URL")
        or os.getenv("DATABASE_URL")
    )
    if not database_url:
        pytest.skip("PostgreSQL URL is required for the party-role integration proof")
    assert database_url is not None
    return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _portfolio(
    portfolio_id: str,
    *,
    tenant_id: str = TEST_TENANT_ID,
    portfolio_type: str = "discretionary",
    status: str = "active",
) -> Portfolio:
    return Portfolio(
        tenant_id=tenant_id,
        legal_book_id="ISSUE513_BOOK",
        portfolio_id=portfolio_id,
        base_currency="SGD",
        open_date=date(2026, 1, 1),
        close_date=None,
        risk_exposure="BALANCED",
        investment_time_horizon="LONG_TERM",
        portfolio_type=portfolio_type,
        objective="CAPITAL_GROWTH",
        booking_center_code="Singapore",
        client_id=f"CLIENT_{portfolio_id}",
        is_leverage_allowed=False,
        advisor_id=PORTFOLIO_MANAGER,
        status=status,
    )


def _assignment(
    *,
    version: int,
    quality_status: str,
    portfolio_id: str = MIGRATED_PORTFOLIO,
    source_record_id: str = SOURCE_RECORD,
) -> dict[str, object]:
    return {
        "portfolio_id": portfolio_id,
        "party_id": PORTFOLIO_MANAGER,
        "role_type": PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER,
        "role_scope": PortfolioPartyRoleScope.PORTFOLIO_MANAGEMENT,
        "effective_from": date(2026, 4, 1),
        "effective_to": None,
        "assignment_version": version,
        "source_system": "relationship_master",
        "source_record_id": source_record_id,
        "observed_at": datetime(2026, 7, 17 + version, 9, tzinfo=UTC),
        "quality_status": quality_status,
    }


def _mandate_binding(portfolio_id: str, *, suffix: str) -> PortfolioMandateBinding:
    return PortfolioMandateBinding(
        portfolio_id=portfolio_id,
        mandate_id=f"ISSUE798_MANDATE_{suffix}",
        client_id=f"ISSUE798_CLIENT_{suffix}",
        mandate_type="discretionary",
        discretionary_authority_status="active",
        booking_center_code="Singapore",
        jurisdiction_code="SG",
        model_portfolio_id=DPM_MODEL,
        policy_pack_id="ISSUE798_POLICY",
        mandate_objective="balanced_growth",
        risk_profile="balanced",
        investment_horizon="long_term",
        rebalance_frequency="monthly",
        rebalance_bands={"default_band": "0.025"},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        binding_version=1,
        source_system="issue798_test",
        source_record_id=f"ISSUE798_BINDING_{suffix}",
        observed_at=datetime(2026, 7, 18, 8, tzinfo=UTC),
        quality_status="accepted",
    )


def _benchmark_assignment(portfolio_id: str, *, suffix: str) -> PortfolioBenchmarkAssignment:
    return PortfolioBenchmarkAssignment(
        portfolio_id=portfolio_id,
        benchmark_id=f"ISSUE798_BENCHMARK_{suffix}",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        assignment_source="issue798_test",
        assignment_status="active",
        policy_pack_id="ISSUE798_POLICY",
        source_system="issue798_test",
        assignment_recorded_at=datetime(2026, 7, 18, 8, tzinfo=UTC),
        assignment_version=1,
    )


async def test_qcp_reference_readers_exclude_foreign_tenant_portfolios() -> None:
    engine = create_async_database_engine(
        runtime_identity="lotus-core-test",
        database_url=_async_database_url(),
        pool_mode=DatabasePoolMode.NULL,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    portfolio_ids = (DPM_OWNED_PORTFOLIO, DPM_FOREIGN_PORTFOLIO)

    try:
        async with sessions() as session:
            await session.execute(
                delete(PortfolioBenchmarkAssignment).where(
                    PortfolioBenchmarkAssignment.portfolio_id.in_(portfolio_ids)
                )
            )
            await session.execute(
                delete(PortfolioMandateBinding).where(
                    PortfolioMandateBinding.portfolio_id.in_(portfolio_ids)
                )
            )
            await session.execute(
                delete(Portfolio).where(Portfolio.portfolio_id.in_(portfolio_ids))
            )
            session.add_all(
                [
                    _portfolio(DPM_OWNED_PORTFOLIO),
                    _portfolio(DPM_FOREIGN_PORTFOLIO, tenant_id=FOREIGN_TENANT_ID),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    _mandate_binding(DPM_OWNED_PORTFOLIO, suffix="OWNED"),
                    _mandate_binding(DPM_FOREIGN_PORTFOLIO, suffix="FOREIGN"),
                    _benchmark_assignment(DPM_OWNED_PORTFOLIO, suffix="OWNED"),
                    _benchmark_assignment(DPM_FOREIGN_PORTFOLIO, suffix="FOREIGN"),
                ]
            )
            await session.commit()

            reader = dpm_portfolio_population_sources.SqlAlchemyDpmPortfolioPopulationReader(
                session
            )
            cohort = await reader.list_affected_mandates(
                tenant_id=TEST_TENANT_ID,
                model_portfolio_id=DPM_MODEL,
                as_of_date=date(2026, 7, 18),
                booking_center_code=None,
                include_inactive_mandates=False,
            )
            universe = await reader.list_universe_candidates(
                tenant_id=TEST_TENANT_ID,
                as_of_date=date(2026, 7, 18),
                booking_center_code=None,
                model_portfolio_ids=(DPM_MODEL,),
                include_inactive_mandates=False,
                after_sort_key=None,
                limit=10,
            )

            assert [row.portfolio_id for row in cohort] == [DPM_OWNED_PORTFOLIO]
            assert [row.portfolio_id for row in universe] == [DPM_OWNED_PORTFOLIO]

            benchmark_reader = benchmark_assignment_sources.SqlAlchemyBenchmarkAssignmentReader(
                session
            )
            owned_assignment = await benchmark_reader.resolve(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=DPM_OWNED_PORTFOLIO,
                as_of_date=BENCHMARK_AS_OF,
            )
            foreign_assignment = await benchmark_reader.resolve(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=DPM_FOREIGN_PORTFOLIO,
                as_of_date=BENCHMARK_AS_OF,
            )
            assert owned_assignment is not None
            assert owned_assignment.benchmark_id == "ISSUE798_BENCHMARK_OWNED"
            assert foreign_assignment is None
    finally:
        async with sessions() as session:
            await session.execute(
                delete(PortfolioBenchmarkAssignment).where(
                    PortfolioBenchmarkAssignment.portfolio_id.in_(portfolio_ids)
                )
            )
            await session.execute(
                delete(PortfolioMandateBinding).where(
                    PortfolioMandateBinding.portfolio_id.in_(portfolio_ids)
                )
            )
            await session.execute(
                delete(Portfolio).where(Portfolio.portfolio_id.in_(portfolio_ids))
            )
            await session.commit()
        await engine.dispose()


async def test_latest_role_version_fences_stale_acceptance_and_legacy_projection() -> None:
    engine = create_async_database_engine(
        runtime_identity="lotus-core-test",
        database_url=_async_database_url(),
        pool_mode=DatabasePoolMode.NULL,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    portfolio_ids = (MIGRATED_PORTFOLIO, LEGACY_PORTFOLIO, FOREIGN_PORTFOLIO)

    try:
        async with sessions() as session:
            await session.execute(
                delete(PortfolioPartyRoleAssignment).where(
                    PortfolioPartyRoleAssignment.portfolio_id.in_(portfolio_ids)
                )
            )
            await session.execute(
                delete(Portfolio).where(Portfolio.portfolio_id.in_(portfolio_ids))
            )
            session.add_all(
                [
                    _portfolio(MIGRATED_PORTFOLIO),
                    _portfolio(
                        LEGACY_PORTFOLIO,
                        portfolio_type="Discretionary",
                        status="Active",
                    ),
                    _portfolio(FOREIGN_PORTFOLIO, tenant_id=FOREIGN_TENANT_ID),
                ]
            )
            await session.commit()

            ingestion = ReferenceDataIngestionService(session)
            await ingestion.upsert_portfolio_party_role_assignments(
                [
                    _assignment(version=1, quality_status="accepted"),
                    _assignment(version=2, quality_status="quarantined"),
                    _assignment(
                        version=1,
                        quality_status="accepted",
                        portfolio_id=FOREIGN_PORTFOLIO,
                        source_record_id="ISSUE798_FOREIGN_COVERAGE_RECORD",
                    ),
                ]
            )

            role_reader = SqlAlchemyPortfolioPartyRoleReader(session)
            accepted = await role_reader.list_effective_assignments(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=MIGRATED_PORTFOLIO,
                as_of_date=date(2026, 7, 18),
                party_id=PORTFOLIO_MANAGER,
                role_types=(),
                role_scopes=(),
                include_non_accepted=False,
            )
            latest = await role_reader.list_effective_assignments(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=MIGRATED_PORTFOLIO,
                as_of_date=date(2026, 7, 18),
                party_id=PORTFOLIO_MANAGER,
                role_types=(),
                role_scopes=(),
                include_non_accepted=True,
            )
            assert accepted == []
            assert len(latest) == 1
            assert latest[0].assignment_version == 2
            assert latest[0].quality_status is PortfolioPartyRoleQualityStatus.QUARANTINED
            foreign = await role_reader.list_effective_assignments(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=FOREIGN_PORTFOLIO,
                as_of_date=date(2026, 7, 18),
                party_id=PORTFOLIO_MANAGER,
                role_types=(),
                role_scopes=(),
                include_non_accepted=True,
            )
            assert foreign == []

            book_reader = SqlAlchemyPortfolioManagerBookReader(session)
            quarantined_book = await book_reader.list_members(
                tenant_id=TEST_TENANT_ID,
                portfolio_manager_id=PORTFOLIO_MANAGER,
                as_of_date=date(2026, 7, 18),
                booking_center_code=None,
                portfolio_types=("DISCRETIONARY",),
                include_inactive=False,
            )
            assert [member.portfolio_id for member in quarantined_book] == [LEGACY_PORTFOLIO]
            assert quarantined_book[0].membership_source == "legacy_advisor_projection"

            await ingestion.upsert_portfolio_party_role_assignments(
                [_assignment(version=2, quality_status="accepted")]
            )
            accepted_book = await book_reader.list_members(
                tenant_id=TEST_TENANT_ID,
                portfolio_manager_id=PORTFOLIO_MANAGER,
                as_of_date=date(2026, 7, 18),
                booking_center_code=None,
                portfolio_types=("DISCRETIONARY",),
                include_inactive=False,
            )
            assert {member.portfolio_id: member.membership_source for member in accepted_book} == {
                LEGACY_PORTFOLIO: "legacy_advisor_projection",
                MIGRATED_PORTFOLIO: "party_role_assignment",
            }
            row_count = await session.scalar(
                select(func.count(PortfolioPartyRoleAssignment.id)).where(
                    PortfolioPartyRoleAssignment.portfolio_id == MIGRATED_PORTFOLIO
                )
            )
            assert row_count == 2
    finally:
        async with sessions() as session:
            await session.execute(
                delete(PortfolioPartyRoleAssignment).where(
                    PortfolioPartyRoleAssignment.portfolio_id.in_(portfolio_ids)
                )
            )
            await session.execute(
                delete(Portfolio).where(Portfolio.portfolio_id.in_(portfolio_ids))
            )
            await session.commit()
        await engine.dispose()
