"""PostgreSQL proof for tenant-fenced reporting portfolio resolution."""

from datetime import UTC, date, datetime

import pytest
from portfolio_common.database_models import Portfolio, PortfolioPartyRoleAssignment
from portfolio_common.domain.portfolio_party_roles import (
    PortfolioPartyRoleQualityStatus,
    PortfolioPartyRoleScope,
    PortfolioPartyRoleType,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_manager_book_sources,
    transaction_economics_sources,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_timeseries_repository import (  # noqa: E501
    AnalyticsTimeseriesRepository,
)
from src.services.query_service.app.repositories.buy_state_repository import BuyStateRepository
from src.services.query_service.app.repositories.cash_account_repository import (
    CashAccountRepository,
)
from src.services.query_service.app.repositories.cashflow_repository import CashflowRepository
from src.services.query_service.app.repositories.lot_basis_transfer_repository import (
    LotBasisTransferRepository,
)
from src.services.query_service.app.repositories.lot_disposal_repository import (
    LotDisposalRepository,
)
from src.services.query_service.app.repositories.reporting_repository import ReportingRepository
from src.services.query_service.app.repositories.sell_state_repository import SellStateRepository

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct]


def _portfolio(*, tenant_id: str, portfolio_id: str) -> Portfolio:
    return Portfolio(
        tenant_id=tenant_id,
        legal_book_id=f"BOOK-{tenant_id}",
        portfolio_id=portfolio_id,
        base_currency="USD",
        open_date=date(2024, 1, 1),
        risk_exposure="Moderate",
        investment_time_horizon="Long",
        portfolio_type="Discretionary",
        booking_center_code="SG",
        client_id=f"CLIENT-{tenant_id}",
        status="ACTIVE",
    )


async def test_reporting_portfolio_resolution_excludes_foreign_tenant(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio(tenant_id="tenant-a", portfolio_id="PORT-A"),
            _portfolio(tenant_id="tenant-b", portfolio_id="PORT-B"),
        ]
    )
    await async_db_session.flush()
    repository = ReportingRepository(async_db_session)

    foreign_portfolio = await repository.get_portfolio_by_id(
        tenant_id="tenant-a",
        portfolio_id="PORT-B",
    )
    visible_portfolios = await repository.list_portfolios(
        tenant_id="tenant-a",
        portfolio_ids=["PORT-A", "PORT-B"],
    )

    assert foreign_portfolio is None
    assert [portfolio.portfolio_id for portfolio in visible_portfolios] == ["PORT-A"]


async def test_portfolio_manager_book_excludes_foreign_tenant_memberships(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    owner = _portfolio(tenant_id="tenant-a", portfolio_id="PORT-A")
    foreign = _portfolio(tenant_id="tenant-b", portfolio_id="PORT-B")
    owner.advisor_id = "MANAGER-SHARED"
    foreign.advisor_id = "MANAGER-SHARED"
    async_db_session.add_all([owner, foreign])
    await async_db_session.flush()

    members = await portfolio_manager_book_sources.SqlAlchemyPortfolioManagerBookReader(
        async_db_session
    ).list_members(
        tenant_id="tenant-a",
        portfolio_manager_id="MANAGER-SHARED",
        as_of_date=date(2026, 1, 1),
        booking_center_code=None,
        portfolio_types=(),
        include_inactive=False,
    )

    assert [member.portfolio_id for member in members] == ["PORT-A"]


async def test_portfolio_manager_book_excludes_foreign_tenant_authoritative_roles(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio(tenant_id="tenant-a", portfolio_id="PORT-A"),
            _portfolio(tenant_id="tenant-b", portfolio_id="PORT-B"),
        ]
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            PortfolioPartyRoleAssignment(
                portfolio_id=portfolio_id,
                party_id="MANAGER-SHARED",
                role_type=PortfolioPartyRoleType.DISCRETIONARY_PORTFOLIO_MANAGER.value,
                role_scope=PortfolioPartyRoleScope.PORTFOLIO_MANAGEMENT.value,
                effective_from=date(2025, 1, 1),
                assignment_version=1,
                source_system="relationship-master",
                source_record_id=f"ROLE-{portfolio_id}",
                observed_at=datetime(2025, 1, 1, tzinfo=UTC),
                quality_status=PortfolioPartyRoleQualityStatus.ACCEPTED.value,
            )
            for portfolio_id in ("PORT-A", "PORT-B")
        ]
    )
    await async_db_session.flush()

    members = await portfolio_manager_book_sources.SqlAlchemyPortfolioManagerBookReader(
        async_db_session
    ).list_members(
        tenant_id="tenant-a",
        portfolio_manager_id="MANAGER-SHARED",
        as_of_date=date(2026, 1, 1),
        booking_center_code=None,
        portfolio_types=(),
        include_inactive=False,
    )

    assert [member.portfolio_id for member in members] == ["PORT-A"]


async def test_portfolio_financial_evidence_boundaries_exclude_foreign_tenant(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio(tenant_id="tenant-a", portfolio_id="PORT-A"),
            _portfolio(tenant_id="tenant-b", portfolio_id="PORT-B"),
        ]
    )
    await async_db_session.flush()

    ownership_repositories = (
        BuyStateRepository(async_db_session),
        SellStateRepository(async_db_session),
        LotDisposalRepository(async_db_session),
        LotBasisTransferRepository(async_db_session),
        CashAccountRepository(async_db_session),
    )
    for repository in ownership_repositories:
        assert await repository.portfolio_exists(
            tenant_id="tenant-a",
            portfolio_id="PORT-A",
        )
        assert not await repository.portfolio_exists(
            tenant_id="tenant-a",
            portfolio_id="PORT-B",
        )

    cashflow_repository = CashflowRepository(async_db_session)
    assert (
        await cashflow_repository.get_portfolio_currency(
            tenant_id="tenant-a",
            portfolio_id="PORT-A",
        )
        == "USD"
    )
    assert (
        await cashflow_repository.get_portfolio_currency(
            tenant_id="tenant-a",
            portfolio_id="PORT-B",
        )
        is None
    )


async def test_control_plane_economics_excludes_foreign_tenant(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio(tenant_id="tenant-a", portfolio_id="PORT-A"),
            _portfolio(tenant_id="tenant-b", portfolio_id="PORT-B"),
        ]
    )
    await async_db_session.flush()

    economics = transaction_economics_sources.SqlAlchemyTransactionEconomicsReader(async_db_session)
    assert await economics.portfolio_exists(tenant_id="tenant-a", portfolio_id="PORT-A")
    assert not await economics.portfolio_exists(tenant_id="tenant-a", portfolio_id="PORT-B")
    assert (
        await economics.get_portfolio_base_currency(tenant_id="tenant-a", portfolio_id="PORT-B")
        is None
    )


async def test_control_plane_analytics_excludes_foreign_tenant(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio(tenant_id="tenant-a", portfolio_id="PORT-A"),
            _portfolio(tenant_id="tenant-b", portfolio_id="PORT-B"),
        ]
    )
    await async_db_session.flush()

    analytics = AnalyticsTimeseriesRepository(async_db_session)
    assert (await analytics.get_portfolio(tenant_id="tenant-a", portfolio_id="PORT-A")) is not None
    assert (await analytics.get_portfolio(tenant_id="tenant-a", portfolio_id="PORT-B")) is None
