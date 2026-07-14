"""Verify upstream settlement cash-leg resolution at the application boundary."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    UpstreamCashLegUnavailableError,
    validate_upstream_cash_leg,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisTransactionStatePort,
)

pytestmark = pytest.mark.asyncio


def _product_leg() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TXN-PRODUCT-001",
        portfolio_id="PORT-001",
        instrument_id="SEC-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 3, 5, 12, 0, tzinfo=UTC),
        transaction_type="DIVIDEND",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id="TXN-CASH-001",
        economic_event_id="EVT-001",
        linked_transaction_group_id="GROUP-001",
    )


def _cash_leg() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TXN-CASH-001",
        portfolio_id="PORT-001",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_date=datetime(2026, 3, 5, 12, 0, tzinfo=UTC),
        transaction_type="ADJUSTMENT",
        quantity=Decimal(0),
        price=Decimal(1),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
        economic_event_id="EVT-001",
        linked_transaction_group_id="GROUP-001",
    )


async def test_upstream_product_leg_requires_external_cash_transaction_id() -> None:
    transactions = AsyncMock(spec=CostBasisTransactionStatePort)

    with pytest.raises(
        ValueError,
        match="UPSTREAM_PROVIDED requires external_cash_transaction_id on product leg",
    ):
        await validate_upstream_cash_leg(
            product_leg=replace(_product_leg(), external_cash_transaction_id=" "),
            transactions=transactions,
        )

    transactions.get_booked_transaction.assert_not_awaited()


async def test_upstream_product_leg_fails_retryably_when_cash_leg_is_unavailable() -> None:
    transactions = AsyncMock(spec=CostBasisTransactionStatePort)
    transactions.get_booked_transaction.return_value = None

    with pytest.raises(UpstreamCashLegUnavailableError, match="TXN-CASH-001"):
        await validate_upstream_cash_leg(
            product_leg=_product_leg(),
            transactions=transactions,
        )

    transactions.get_booked_transaction.assert_awaited_once_with(
        "TXN-CASH-001",
        portfolio_id="PORT-001",
    )


async def test_upstream_product_leg_validates_canonical_cash_pair() -> None:
    transactions = AsyncMock(spec=CostBasisTransactionStatePort)
    transactions.get_booked_transaction.return_value = _cash_leg()

    await validate_upstream_cash_leg(
        product_leg=_product_leg(),
        transactions=transactions,
    )

    transactions.get_booked_transaction.assert_awaited_once_with(
        "TXN-CASH-001",
        portfolio_id="PORT-001",
    )


@pytest.mark.parametrize(
    "product_leg",
    [
        replace(_product_leg(), cash_entry_mode=None, external_cash_transaction_id=None),
        replace(
            _product_leg(),
            transaction_type=" adjustment ",
            external_cash_transaction_id=None,
        ),
    ],
)
async def test_transaction_without_external_product_cash_dependency_skips_lookup(
    product_leg: BookedTransaction,
) -> None:
    transactions = AsyncMock(spec=CostBasisTransactionStatePort)

    await validate_upstream_cash_leg(product_leg=product_leg, transactions=transactions)

    transactions.get_booked_transaction.assert_not_awaited()
