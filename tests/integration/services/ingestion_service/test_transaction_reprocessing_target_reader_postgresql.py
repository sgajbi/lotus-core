"""PostgreSQL proof for tenant-fenced transaction reprocessing lookup."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import Portfolio, Transaction
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ingestion_service.app.infrastructure import (
    transaction_reprocessing_target_reader as target_reader,
)

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


def _transaction(*, transaction_id: str, portfolio_id: str) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id=f"INST-{transaction_id}",
        security_id=f"SEC-{transaction_id}",
        transaction_type="BUY",
        quantity=Decimal("1"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
        transaction_date=datetime(2026, 8, 31, tzinfo=UTC),
    )


async def test_reader_returns_only_transactions_owned_by_admitted_tenant(
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
            _transaction(transaction_id="TXN-A", portfolio_id="PORT-A"),
            _transaction(transaction_id="TXN-B", portfolio_id="PORT-B"),
        ]
    )
    await async_db_session.flush()

    targets = await target_reader.SqlAlchemyTransactionReprocessingTargetReader(
        async_db_session
    ).read_targets(
        tenant_id="tenant-a",
        transaction_ids=["TXN-A", "TXN-B"],
    )

    assert [(target.transaction_id, target.portfolio_id) for target in targets] == [
        ("TXN-A", "PORT-A")
    ]
