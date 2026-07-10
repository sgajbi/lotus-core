from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.cost_basis import CostBasisMethod
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent

from src.services.calculators.cost_calculator_service.app.consumer import CostCalculationWorkflow
from src.services.calculators.cost_calculator_service.app.cost_engine.domain.models.transaction import (  # noqa: E501
    Transaction as EngineTransaction,
)
from src.services.calculators.cost_calculator_service.app.cost_processing_checkpoint import (
    CostBasisProcessingCheckpoint,
)
from src.services.calculators.cost_calculator_service.app.repository import (
    CostCalculatorRepository,
    OpenLotCheckpointRecord,
)

pytestmark = pytest.mark.asyncio


def _event(
    *, transaction_id: str, transaction_date: datetime, transaction_type: str, quantity: str
) -> TransactionEvent:
    gross_amount = Decimal(quantity) * (
        Decimal("12") if transaction_type == "SELL" else Decimal("10")
    )
    return TransactionEvent(
        transaction_id=transaction_id,
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_type=transaction_type,
        transaction_date=transaction_date,
        quantity=Decimal(quantity),
        price=Decimal("12") if transaction_type == "SELL" else Decimal("10"),
        gross_transaction_amount=gross_amount,
        trade_currency="USD",
        currency="USD",
        transaction_fx_rate=Decimal("1"),
    )


def _processed_buy(transaction_id: str, transaction_date: datetime) -> EngineTransaction:
    payload = CostCalculationWorkflow()._transform_event_for_engine(
        _event(
            transaction_id=transaction_id,
            transaction_date=transaction_date,
            transaction_type="BUY",
            quantity="10",
        )
    )
    payload.update(
        portfolio_base_currency="USD",
        net_cost_local=Decimal("100"),
        net_cost=Decimal("100"),
    )
    return EngineTransaction(**payload)


def _persisted_buy(transaction_id: str, transaction_date: datetime) -> DBTransaction:
    return DBTransaction(
        transaction_id=transaction_id,
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=transaction_date,
        quantity=Decimal("10"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("100"),
        trade_currency="USD",
        currency="USD",
        transaction_fx_rate=Decimal("1"),
        net_cost_local=Decimal("100"),
        net_cost=Decimal("100"),
    )


async def test_later_sell_restores_open_lots_without_loading_full_history() -> None:
    workflow = CostCalculationWorkflow()
    repo = AsyncMock(spec=CostCalculatorRepository)
    buy_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    sell_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    prior_buy = _processed_buy("BUY-1", buy_date)
    repo.get_cost_basis_processing_checkpoint.return_value = (
        CostBasisProcessingCheckpoint.from_transaction(
            prior_buy, cost_basis_method=CostBasisMethod.FIFO
        )
    )
    repo.get_open_lot_checkpoint_records.return_value = [
        OpenLotCheckpointRecord(
            transaction=_persisted_buy("BUY-1", buy_date),
            quantity=Decimal("10"),
            cost_local=Decimal("100"),
            cost_base=Decimal("100"),
        )
    ]
    sell_event, sell_type, method = await workflow._prepare_transaction_event(
        _event(
            transaction_id="SELL-1",
            transaction_date=sell_date,
            transaction_type="SELL",
            quantity="4",
        ),
        MagicMock(cost_basis_method="FIFO"),
    )

    calculation = await workflow._calculate_cost_engine(
        event=sell_event,
        event_transaction_type=sell_type,
        portfolio_base_currency="USD",
        instrument=MagicMock(product_type="EQUITY", asset_class="EQUITY"),
        repo=repo,
        cost_basis_method=method,
    )

    assert calculation.incremental is True
    assert calculation.errored == []
    assert calculation.processed[0].realized_gain_loss == Decimal("8")
    assert calculation.open_lot_states["BUY-1"].quantity == Decimal("6")
    assert calculation.open_lot_states["BUY-1"].cost_base == Decimal("60")
    repo.get_transaction_history.assert_not_awaited()


async def test_backdated_transaction_uses_full_deterministic_history() -> None:
    workflow = CostCalculationWorkflow()
    repo = AsyncMock(spec=CostCalculatorRepository)
    later_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    earlier_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    later_buy = _processed_buy("BUY-LATER", later_date)
    repo.get_cost_basis_processing_checkpoint.return_value = (
        CostBasisProcessingCheckpoint.from_transaction(
            later_buy, cost_basis_method=CostBasisMethod.FIFO
        )
    )
    repo.get_transaction_history.return_value = [_persisted_buy("BUY-LATER", later_date)]

    calculation = await workflow._calculate_cost_engine(
        event=_event(
            transaction_id="BUY-EARLIER",
            transaction_date=earlier_date,
            transaction_type="BUY",
            quantity="5",
        ),
        event_transaction_type="BUY",
        portfolio_base_currency="USD",
        instrument=MagicMock(product_type="EQUITY", asset_class="EQUITY"),
        repo=repo,
        cost_basis_method=CostBasisMethod.FIFO,
    )

    assert calculation.incremental is False
    assert calculation.errored == []
    assert [transaction.transaction_id for transaction in calculation.processed] == [
        "BUY-EARLIER",
        "BUY-LATER",
    ]
    repo.get_transaction_history.assert_awaited_once()
