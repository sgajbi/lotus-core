"""PostgreSQL proof for tenant-scoped transaction-economics source evidence."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import Portfolio, Transaction
from portfolio_common.domain.tenant import TenantId
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure.transaction_economics_sources import (  # noqa: E501
    SqlAlchemyTransactionEconomicsReader,
)

pytestmark = pytest.mark.asyncio

TENANT_A = TenantId("ISSUE_798_TENANT_A")
TENANT_B = TenantId("ISSUE_798_TENANT_B")
PORTFOLIO_A = "ISSUE_798_ECONOMICS_A"
PORTFOLIO_B = "ISSUE_798_ECONOMICS_B"


def _portfolio(*, portfolio_id: str, tenant_id: TenantId, currency: str) -> Portfolio:
    return Portfolio(
        portfolio_id=portfolio_id,
        tenant_id=tenant_id.value,
        base_currency=currency,
        open_date=date(2026, 1, 1),
        risk_exposure="BALANCED",
        investment_time_horizon="LONG_TERM",
        portfolio_type="discretionary",
        booking_center_code="Singapore",
        client_id=f"CLIENT_{tenant_id.value}",
        is_leverage_allowed=False,
        status="active",
    )


def _transaction(*, transaction_id: str, portfolio_id: str, security_id: str) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id=security_id,
        security_id=security_id,
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        transaction_date=datetime(2026, 4, 10, 9, tzinfo=UTC),
        settlement_date=datetime(2026, 4, 12, 9, tzinfo=UTC),
        trade_fee=Decimal("1"),
    )


async def test_transaction_economics_reads_are_isolated_by_persisted_portfolio_tenant(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio(portfolio_id=PORTFOLIO_A, tenant_id=TENANT_A, currency="USD"),
            _portfolio(portfolio_id=PORTFOLIO_B, tenant_id=TENANT_B, currency="SGD"),
            _transaction(
                transaction_id="ISSUE_798_TX_A",
                portfolio_id=PORTFOLIO_A,
                security_id="ISSUE_798_SECURITY_A",
            ),
            _transaction(
                transaction_id="ISSUE_798_TX_B",
                portfolio_id=PORTFOLIO_B,
                security_id="ISSUE_798_SECURITY_B",
            ),
        ]
    )
    await async_db_session.commit()
    reader = SqlAlchemyTransactionEconomicsReader(async_db_session)

    assert await reader.portfolio_exists(PORTFOLIO_A, tenant_id=TENANT_A)
    assert not await reader.portfolio_exists(PORTFOLIO_A, tenant_id=TENANT_B)
    assert await reader.get_portfolio_base_currency(PORTFOLIO_B, tenant_id=TENANT_B) == "SGD"
    assert await reader.get_portfolio_base_currency(PORTFOLIO_B, tenant_id=TENANT_A) is None

    owned_curve_keys = await reader.list_transaction_cost_curve_keys(
        portfolio_id=PORTFOLIO_A,
        tenant_id=TENANT_A,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 4, 30),
        security_ids=None,
        transaction_types=None,
        min_observation_count=1,
        after_key=(),
        limit=10,
    )
    foreign_curve_keys = await reader.list_transaction_cost_curve_keys(
        portfolio_id=PORTFOLIO_A,
        tenant_id=TENANT_B,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 4, 30),
        security_ids=None,
        transaction_types=None,
        min_observation_count=1,
        after_key=(),
        limit=10,
    )

    assert owned_curve_keys == [("ISSUE_798_SECURITY_A", "BUY", "USD")]
    assert foreign_curve_keys == []

    owned_performance = await reader.list_performance_component_economics_evidence(
        portfolio_id=PORTFOLIO_B,
        tenant_id=TENANT_B,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 4, 30),
        security_ids=None,
        transaction_types=None,
        after_key=(),
        limit=10,
    )
    foreign_performance = await reader.list_performance_component_economics_evidence(
        portfolio_id=PORTFOLIO_B,
        tenant_id=TENANT_A,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 4, 30),
        security_ids=None,
        transaction_types=None,
        after_key=(),
        limit=10,
    )

    assert [row.transaction_id for row in owned_performance] == ["ISSUE_798_TX_B"]
    assert foreign_performance == []
