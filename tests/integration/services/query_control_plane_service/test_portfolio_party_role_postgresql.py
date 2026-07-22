"""PostgreSQL proof for effective party roles and the legacy PM-book fence."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime

import pytest
from portfolio_common.database_models import Portfolio, PortfolioPartyRoleAssignment
from portfolio_common.domain.portfolio_party_roles import (
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
)
from src.services.query_control_plane_service.app.infrastructure import (
    SqlAlchemyPortfolioManagerBookReader,
    SqlAlchemyPortfolioPartyRoleReader,
)

pytestmark = pytest.mark.asyncio

MIGRATED_PORTFOLIO = "ISSUE513_ROLE_PORTFOLIO"
LEGACY_PORTFOLIO = "ISSUE513_LEGACY_PORTFOLIO"
PORTFOLIO_MANAGER = "ISSUE513_PARTY_PM"
SOURCE_RECORD = "ISSUE513_COVERAGE_RECORD"


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
    portfolio_id: str, *, portfolio_type: str = "discretionary", status: str = "active"
) -> Portfolio:
    return Portfolio(
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


def _assignment(*, version: int, quality_status: str) -> dict[str, object]:
    return {
        "portfolio_id": MIGRATED_PORTFOLIO,
        "party_id": PORTFOLIO_MANAGER,
        "role_type": PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER,
        "role_scope": PortfolioPartyRoleScope.PORTFOLIO_MANAGEMENT,
        "effective_from": date(2026, 4, 1),
        "effective_to": None,
        "assignment_version": version,
        "source_system": "relationship_master",
        "source_record_id": SOURCE_RECORD,
        "observed_at": datetime(2026, 7, 17 + version, 9, tzinfo=UTC),
        "quality_status": quality_status,
    }


async def test_latest_role_version_fences_stale_acceptance_and_legacy_projection() -> None:
    engine = create_async_engine(_async_database_url())
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    portfolio_ids = (MIGRATED_PORTFOLIO, LEGACY_PORTFOLIO)

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
                        status="ACTIVE",
                    ),
                ]
            )
            await session.commit()

            ingestion = ReferenceDataIngestionService(session)
            await ingestion.upsert_portfolio_party_role_assignments(
                [
                    _assignment(version=1, quality_status="accepted"),
                    _assignment(version=2, quality_status="quarantined"),
                ]
            )

            role_reader = SqlAlchemyPortfolioPartyRoleReader(session)
            accepted = await role_reader.list_effective_assignments(
                portfolio_id=MIGRATED_PORTFOLIO,
                as_of_date=date(2026, 7, 18),
                party_id=PORTFOLIO_MANAGER,
                role_types=(),
                role_scopes=(),
                include_non_accepted=False,
            )
            latest = await role_reader.list_effective_assignments(
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

            book_reader = SqlAlchemyPortfolioManagerBookReader(session)
            quarantined_book = await book_reader.list_members(
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
