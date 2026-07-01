from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.events import TransactionEvent
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
    transaction_event_to_record_values,
)


@pytest.mark.asyncio
async def test_create_or_update_transaction_uses_canonical_currency_codes() -> None:
    db = AsyncMock(spec=AsyncSession)
    repo = TransactionDBRepository(db)
    event = TransactionEvent(
        transaction_id="TX_CANONICAL_CCY_001",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency=" usd ",
        currency=" usd ",
        pair_base_currency=" eur ",
        pair_quote_currency=" usd ",
        buy_currency=" usd ",
        sell_currency=" eur ",
        synthetic_flow_currency=" sgd ",
    )

    persisted = await repo.create_or_update_transaction(event)

    assert persisted.trade_currency == "USD"
    assert persisted.currency == "USD"
    assert persisted.pair_base_currency == "EUR"
    assert persisted.pair_quote_currency == "USD"
    assert persisted.buy_currency == "USD"
    assert persisted.sell_currency == "EUR"
    assert persisted.synthetic_flow_currency == "SGD"
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_or_update_transaction_persists_aggregated_trade_fee() -> None:
    db = AsyncMock(spec=AsyncSession)
    repo = TransactionDBRepository(db)
    event = TransactionEvent(
        transaction_id="TX_FEE_COMPONENTS_001",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        trade_fee=Decimal("0.00"),
        brokerage=Decimal("2.50"),
        stamp_duty=Decimal("1.20"),
        exchange_fee=Decimal("0.70"),
        gst=Decimal("0.45"),
        other_fees=Decimal("0.15"),
    )

    persisted = await repo.create_or_update_transaction(event)

    assert persisted.trade_fee == Decimal("5.00")
    assert not hasattr(persisted, "brokerage")
    db.execute.assert_awaited_once()


def test_transaction_event_to_record_values_excludes_traceparent_envelope() -> None:
    event = TransactionEvent(
        transaction_id="TX_TRACEPARENT_001",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date="2026-05-28T10:00:00Z",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        correlation_id="corr-transaction",
        traceparent="00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
    )

    values = transaction_event_to_record_values(event)

    assert "correlation_id" not in values
    assert "traceparent" not in values
    assert values["transaction_id"] == "TX_TRACEPARENT_001"


@pytest.mark.asyncio
async def test_check_instrument_exists_queries_instrument_master() -> None:
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar.return_value = True
    db.execute.return_value = result
    repo = TransactionDBRepository(db)

    assert await repo.check_instrument_exists(" SEC-1 ") is True

    stmt = db.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(instruments.security_id) = 'SEC-1'" in compiled_query


@pytest.mark.asyncio
async def test_check_instrument_exists_skips_blank_security_id() -> None:
    db = AsyncMock(spec=AsyncSession)
    repo = TransactionDBRepository(db)

    assert await repo.check_instrument_exists("   ") is False

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_active_cash_account_exists_queries_active_effective_master() -> None:
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar.return_value = True
    db.execute.return_value = result
    repo = TransactionDBRepository(db)

    assert (
        await repo.check_active_cash_account_exists(
            portfolio_id="P1",
            cash_account_id=" CASH-ACC-1 ",
            cash_security_id=" CASH_USD ",
            as_of_date=date(2026, 3, 27),
        )
        is True
    )

    stmt = db.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "cash_account_masters.portfolio_id = 'P1'" in compiled_query
    assert "cash_account_masters.cash_account_id = 'CASH-ACC-1'" in compiled_query
    assert "upper(trim(cash_account_masters.lifecycle_status)) = 'ACTIVE'" in compiled_query
    assert "cash_account_masters.opened_on <= '2026-03-27'" in compiled_query
    assert "cash_account_masters.closed_on >= '2026-03-27'" in compiled_query
    assert "trim(cash_account_masters.security_id) = 'CASH_USD'" in compiled_query


@pytest.mark.asyncio
async def test_check_active_cash_account_exists_skips_blank_cash_account_id() -> None:
    db = AsyncMock(spec=AsyncSession)
    repo = TransactionDBRepository(db)

    assert (
        await repo.check_active_cash_account_exists(
            portfolio_id="P1",
            cash_account_id="   ",
            cash_security_id="CASH_USD",
            as_of_date=date(2026, 3, 27),
        )
        is False
    )

    db.execute.assert_not_awaited()
