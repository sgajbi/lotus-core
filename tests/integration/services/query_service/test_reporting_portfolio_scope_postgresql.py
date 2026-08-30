"""PostgreSQL proof for tenant-fenced reporting portfolio resolution."""

from datetime import date

import pytest
from portfolio_common.database_models import Portfolio
from sqlalchemy.ext.asyncio import AsyncSession

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
