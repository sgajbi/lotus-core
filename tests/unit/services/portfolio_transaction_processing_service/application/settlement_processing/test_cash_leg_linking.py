"""Application tests for settlement cash-leg validation, generation, and linking."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, call

import pytest

from src.services.portfolio_transaction_processing_service.app.application import (
    settlement_processing,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    SettlementTransactionLookupPort,
    SettlementTransactionPersistencePort,
)

pytestmark = pytest.mark.asyncio

link_settlement_cash_leg = settlement_processing.link_settlement_cash_leg


def _product_leg(**overrides: object) -> BookedTransaction:
    transaction = BookedTransaction(
        transaction_id="DIV-GENERATED-01",
        portfolio_id="PORT-001",
        instrument_id="FUND-001",
        security_id="FUND-001",
        transaction_date=datetime(2026, 3, 5, 12, 0, tzinfo=UTC),
        settlement_date=datetime(2026, 3, 7, 12, 0, tzinfo=UTC),
        transaction_type="DIVIDEND",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("25"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="AUTO_GENERATE",
        settlement_cash_account_id="CASH-USD-001",
        settlement_cash_instrument_id="CASH-USD",
        economic_event_id="EVT-001",
        linked_transaction_group_id="GROUP-001",
    )
    return replace(transaction, **overrides)


async def test_generated_cash_leg_is_persisted_before_linked_product_leg() -> None:
    product_leg = _product_leg()
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    persistence = AsyncMock(spec=SettlementTransactionPersistencePort)

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
    )

    assert result.product_leg.external_cash_transaction_id == "DIV-GENERATED-01-CASHLEG"
    assert result.generated_cash_leg is not None
    assert result.generated_cash_leg.transaction_id == "DIV-GENERATED-01-CASHLEG"
    assert result.generated_cash_leg.originating_transaction_id == product_leg.transaction_id
    assert product_leg.external_cash_transaction_id is None
    assert persistence.upsert_booked_transaction.await_args_list == [
        call(result.generated_cash_leg),
        call(result.product_leg),
    ]
    lookup.get_booked_transaction.assert_not_awaited()


async def test_upstream_provided_product_leg_is_validated_without_generated_writes() -> None:
    cash_leg = _product_leg(
        transaction_id="CASH-001",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_type="ADJUSTMENT",
        cash_entry_mode=None,
        external_cash_transaction_id=None,
    )
    product_leg = _product_leg(
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id=cash_leg.transaction_id,
    )
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    lookup.get_booked_transaction.return_value = cash_leg
    persistence = AsyncMock(spec=SettlementTransactionPersistencePort)

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
    )

    assert result.product_leg is product_leg
    assert result.generated_cash_leg is None
    lookup.get_booked_transaction.assert_awaited_once_with(
        cash_leg.transaction_id,
        portfolio_id=product_leg.portfolio_id,
    )
    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_non_cash_linking_transaction_remains_unchanged() -> None:
    product_leg = _product_leg(cash_entry_mode=None)
    lookup = AsyncMock(spec=SettlementTransactionLookupPort)
    persistence = AsyncMock(spec=SettlementTransactionPersistencePort)

    result = await link_settlement_cash_leg(
        product_leg=product_leg,
        transaction_lookup=lookup,
        transaction_persistence=persistence,
    )

    assert result.product_leg is product_leg
    assert result.generated_cash_leg is None
    lookup.get_booked_transaction.assert_not_awaited()
    persistence.upsert_booked_transaction.assert_not_awaited()
