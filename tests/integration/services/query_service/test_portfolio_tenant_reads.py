"""PostgreSQL proof for tenant-scoped portfolio discovery and detail reads."""

from datetime import date

import pytest
from portfolio_common.database_models import Portfolio
from portfolio_common.domain.tenant import TenantContext, TenantId
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.services.portfolio_service import PortfolioService

pytestmark = pytest.mark.asyncio

TENANT_A = TenantContext(tenant_id=TenantId("TENANT_A"))
TENANT_B = TenantContext(tenant_id=TenantId("TENANT_B"))


def _portfolio(*, portfolio_id: str, tenant_id: str) -> Portfolio:
    return Portfolio(
        portfolio_id=portfolio_id,
        tenant_id=tenant_id,
        legal_book_id=f"{tenant_id}-BOOK",
        base_currency="USD",
        open_date=date(2026, 1, 1),
        risk_exposure="MODERATE",
        investment_time_horizon="MEDIUM_TERM",
        portfolio_type="DISCRETIONARY",
        objective="CAPITAL_GROWTH",
        booking_center_code="SG",
        client_id=f"{tenant_id}-CLIENT",
        status="ACTIVE",
        is_leverage_allowed=False,
    )


async def _seed_tenant_portfolios(session: AsyncSession) -> None:
    session.add_all(
        [
            _portfolio(portfolio_id="PF-TENANT-A", tenant_id="TENANT_A"),
            _portfolio(portfolio_id="PF-TENANT-B", tenant_id="TENANT_B"),
        ]
    )
    await session.commit()


async def test_portfolio_discovery_returns_only_persisted_tenant_rows(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_tenant_portfolios(async_db_session)
    service = PortfolioService(async_db_session)

    response = await service.get_portfolios(tenant_context=TENANT_A)

    assert [(item.portfolio_id, item.tenant_id) for item in response.portfolios] == [
        ("PF-TENANT-A", "TENANT_A")
    ]


async def test_cross_tenant_portfolio_detail_is_indistinguishable_from_absence(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_tenant_portfolios(async_db_session)
    service = PortfolioService(async_db_session)

    with pytest.raises(LookupError, match="Portfolio with id PF-TENANT-B not found"):
        await service.get_portfolio_by_id(
            "PF-TENANT-B",
            tenant_context=TENANT_A,
        )

    own_record = await service.get_portfolio_by_id(
        "PF-TENANT-B",
        tenant_context=TENANT_B,
    )
    assert own_record.tenant_id == "TENANT_B"
