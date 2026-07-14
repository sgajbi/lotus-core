"""Verify deterministic AVCO rebuild planning from canonical booked history."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    AverageCostPoolRebuildPlanner,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    CostBasisFxRatePort,
    CostBasisInstrumentReference,
    CostBasisPortfolioReference,
    CostBasisReferenceDataPort,
    CostBasisTransactionStatePort,
)

pytestmark = pytest.mark.asyncio


def _booked_transaction(
    transaction_id: str,
    transaction_type: str,
    transaction_date: datetime,
    *,
    quantity: str,
    price: str,
) -> BookedTransaction:
    quantity_value = Decimal(quantity)
    price_value = Decimal(price)
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=transaction_date,
        transaction_type=transaction_type,
        quantity=quantity_value,
        price=price_value,
        gross_transaction_amount=quantity_value * price_value,
        trade_currency="USD",
        currency="USD",
    )


def _reference_data(cost_basis_method: CostBasisMethod) -> AsyncMock:
    reference_data = AsyncMock(spec=CostBasisReferenceDataPort)
    reference_data.get_cost_basis_portfolio.return_value = CostBasisPortfolioReference(
        portfolio_id="P1",
        base_currency="USD",
        cost_basis_method=cost_basis_method,
    )
    reference_data.get_cost_basis_instrument.return_value = CostBasisInstrumentReference(
        security_id="S1",
        product_type="EQUITY",
        asset_class="EQUITY",
    )
    return reference_data


async def test_rebuild_plan_replays_complete_canonical_history() -> None:
    transactions = AsyncMock(spec=CostBasisTransactionStatePort)
    transactions.get_transaction_history.return_value = [
        _booked_transaction(
            "BUY-AVCO-1",
            "BUY",
            datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            quantity="10",
            price="10",
        ),
        _booked_transaction(
            "BUY-AVCO-2",
            "BUY",
            datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
            quantity="5",
            price="10",
        ),
        _booked_transaction(
            "SELL-AVCO-1",
            "SELL",
            datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc),
            quantity="4",
            price="12",
        ),
    ]

    plan = await AverageCostPoolRebuildPlanner().build(
        portfolio_id="P1",
        security_id="S1",
        transactions=transactions,
        reference_data=_reference_data(CostBasisMethod.AVCO),
        fx_rates=AsyncMock(spec=CostBasisFxRatePort),
    )

    assert [transaction.transaction_id for transaction in plan.source_transactions] == [
        "BUY-AVCO-1",
        "BUY-AVCO-2",
    ]
    assert plan.checkpoint.quantity == Decimal("11")
    assert plan.checkpoint.cost_local == Decimal("110")
    assert plan.checkpoint.cost_base == Decimal("110")
    assert plan.checkpoint.representative_source_transaction_id == "BUY-AVCO-2"
    assert sum(state.quantity for state in plan.source_states.values()) == Decimal("11")
    assert sum(state.cost_base for state in plan.source_states.values()) == Decimal("110")
    assert plan.processing_checkpoint.latest_transaction_id == "SELL-AVCO-1"
    transactions.get_transaction_history.assert_awaited_once_with(
        portfolio_id="P1",
        security_id="S1",
    )


async def test_rebuild_plan_rejects_non_avco_portfolio_before_history_read() -> None:
    transactions = AsyncMock(spec=CostBasisTransactionStatePort)

    with pytest.raises(ValueError, match="requires an AVCO portfolio"):
        await AverageCostPoolRebuildPlanner().build(
            portfolio_id="P1",
            security_id="S1",
            transactions=transactions,
            reference_data=_reference_data(CostBasisMethod.FIFO),
            fx_rates=AsyncMock(spec=CostBasisFxRatePort),
        )

    transactions.get_transaction_history.assert_not_awaited()


async def test_rebuild_plan_fails_closed_on_invalid_history() -> None:
    transactions = AsyncMock(spec=CostBasisTransactionStatePort)
    transactions.get_transaction_history.return_value = [
        _booked_transaction(
            "SELL-AVCO-INVALID",
            "SELL",
            datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            quantity="1",
            price="12",
        )
    ]

    with pytest.raises(ValueError, match="Cost-basis calculation failed"):
        await AverageCostPoolRebuildPlanner().build(
            portfolio_id="P1",
            security_id="S1",
            transactions=transactions,
            reference_data=_reference_data(CostBasisMethod.AVCO),
            fx_rates=AsyncMock(spec=CostBasisFxRatePort),
        )


async def test_rebuild_plan_rejects_missing_instrument_before_history_read() -> None:
    transactions = AsyncMock(spec=CostBasisTransactionStatePort)
    reference_data = _reference_data(CostBasisMethod.AVCO)
    reference_data.get_cost_basis_instrument.return_value = None

    with pytest.raises(ValueError, match="Instrument S1 was not found"):
        await AverageCostPoolRebuildPlanner().build(
            portfolio_id="P1",
            security_id="S1",
            transactions=transactions,
            reference_data=reference_data,
            fx_rates=AsyncMock(spec=CostBasisFxRatePort),
        )

    transactions.get_transaction_history.assert_not_awaited()


async def test_rebuild_plan_rejects_empty_canonical_history() -> None:
    transactions = AsyncMock(spec=CostBasisTransactionStatePort)
    transactions.get_transaction_history.return_value = []

    with pytest.raises(ValueError, match="requires transaction history"):
        await AverageCostPoolRebuildPlanner().build(
            portfolio_id="P1",
            security_id="S1",
            transactions=transactions,
            reference_data=_reference_data(CostBasisMethod.AVCO),
            fx_rates=AsyncMock(spec=CostBasisFxRatePort),
        )
