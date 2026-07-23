"""Application tests for validated foreign-exchange transaction booking."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application import (
    foreign_exchange_processing,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    ForeignExchangeTransactionPersistencePort,
)

pytestmark = pytest.mark.asyncio

book_foreign_exchange_transaction = foreign_exchange_processing.book_foreign_exchange_transaction


def _foreign_exchange_transaction(**updates: object) -> BookedTransaction:
    transaction = BookedTransaction(
        transaction_id="FX-OPEN-001",
        portfolio_id="PORT-FX-1",
        instrument_id="FXC-EURUSD-001",
        security_id="FXC-EURUSD-001",
        transaction_date=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        settlement_date=datetime(2026, 7, 1, 9, 0, tzinfo=UTC),
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        component_id="FX-COMP-OPEN-001",
        linked_component_ids=("FX-COMP-BUY-001", "FX-COMP-SELL-001"),
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("1095000"),
        trade_currency="USD",
        currency="USD",
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        fx_rate_quote_convention="QUOTE_PER_BASE",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1095000"),
        sell_amount=Decimal("1000000"),
        contract_rate=Decimal("1.095"),
        economic_event_id="EVT-FX-001",
        linked_transaction_group_id="LTG-FX-001",
        calculation_policy_id="FX_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        fx_contract_id="FXC-2026-0001",
        spot_exposure_model="NONE",
        fx_realized_pnl_mode="UPSTREAM_PROVIDED",
        realized_capital_pnl_local=Decimal(0),
        realized_fx_pnl_local=Decimal("1250"),
        realized_total_pnl_local=Decimal("1250"),
        realized_capital_pnl_base=Decimal(0),
        realized_fx_pnl_base=Decimal("1250"),
        realized_total_pnl_base=Decimal("1250"),
    )
    return replace(transaction, **updates)


async def test_booking_persists_validated_fx_transaction_and_returns_contract_instrument() -> None:
    transaction = _foreign_exchange_transaction(fx_realized_pnl_mode=" upstream_provided ")
    persistence = AsyncMock(spec=ForeignExchangeTransactionPersistencePort)

    result = await book_foreign_exchange_transaction(
        transaction=transaction,
        transaction_persistence=persistence,
    )

    assert result.transaction.fx_realized_pnl_mode == "UPSTREAM_PROVIDED"
    persistence.upsert_booked_transaction.assert_awaited_once_with(result.transaction)
    assert result.contract_instrument is not None
    assert result.contract_instrument.security_id == "FXC-2026-0001"


async def test_booking_returns_no_contract_instrument_for_cash_settlement_component() -> None:
    transaction = _foreign_exchange_transaction(
        component_type="FX_CASH_SETTLEMENT_BUY",
        fx_cash_leg_role="BUY",
        linked_fx_cash_leg_id="FX-CASH-SELL-001",
    )
    persistence = AsyncMock(spec=ForeignExchangeTransactionPersistencePort)

    result = await book_foreign_exchange_transaction(
        transaction=transaction,
        transaction_persistence=persistence,
    )

    assert result.contract_instrument is None
    persistence.upsert_booked_transaction.assert_awaited_once_with(result.transaction)


async def test_booking_rejects_invalid_fx_transaction_before_persistence() -> None:
    transaction = _foreign_exchange_transaction(buy_currency="USD", sell_currency="USD")
    persistence = AsyncMock(spec=ForeignExchangeTransactionPersistencePort)

    with pytest.raises(ValueError, match="FX validation failed"):
        await book_foreign_exchange_transaction(
            transaction=transaction,
            transaction_persistence=persistence,
        )

    persistence.upsert_booked_transaction.assert_not_awaited()


@pytest.mark.parametrize(
    "fee_update",
    [
        {"trade_fee": Decimal("1")},
        {"trade_fee": Decimal("0"), "brokerage": Decimal("1")},
    ],
)
async def test_booking_rejects_embedded_fx_fee_before_persistence(
    fee_update: dict[str, Decimal],
) -> None:
    transaction = _foreign_exchange_transaction(**fee_update)
    persistence = AsyncMock(spec=ForeignExchangeTransactionPersistencePort)

    with pytest.raises(ValueError, match="FX_025_NON_ZERO_EMBEDDED_FEE:trade_fee"):
        await book_foreign_exchange_transaction(
            transaction=transaction,
            transaction_persistence=persistence,
        )

    persistence.upsert_booked_transaction.assert_not_awaited()
