from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.events import TransactionEvent
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.persistence_service.app.repositories.transaction_db_repo import (
    TransactionDBRepository,
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
