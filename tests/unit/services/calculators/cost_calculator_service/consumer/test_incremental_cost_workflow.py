from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.cost_basis import CostBasisMethod
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent

from src.services.calculators.cost_calculator_service.app.average_cost_pool_checkpoint import (
    AverageCostPoolCheckpoint,
)
from src.services.calculators.cost_calculator_service.app.cost_calculation_workflow import (
    CostCalculationWorkflow,
    OpenLotStateUpdateScope,
)
from src.services.calculators.cost_calculator_service.app.cost_processing_checkpoint import (
    CostBasisProcessingCheckpoint,
)
from src.services.calculators.cost_calculator_service.app.repository import (
    AverageCostPoolCheckpointRecord,
    CostCalculatorRepository,
    OpenLotCheckpointRecord,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (  # noqa: E501
    CostBasisTransaction as EngineTransaction,
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
    repo.get_fifo_disposal_lot_checkpoint_records.return_value = [
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

    with (
        patch(
            "src.services.calculators.cost_calculator_service.app.cost_calculation_workflow."
            "COST_PROCESSING_EXECUTION_TOTAL"
        ) as execution_metric,
        patch(
            "src.services.calculators.cost_calculator_service.app.cost_calculation_workflow."
            "COST_PROCESSING_OPEN_LOTS_RESTORED"
        ) as restore_metric,
    ):
        calculation = await workflow._calculate_cost_basis(
            event=sell_event,
            event_transaction_type=sell_type,
            portfolio_base_currency="USD",
            instrument=MagicMock(product_type="EQUITY", asset_class="EQUITY"),
            repo=repo,
            cost_basis_method=method,
        )

    assert calculation.incremental is True
    assert calculation.open_lot_state_update_scope is OpenLotStateUpdateScope.SELECTED_LOTS
    assert calculation.errored == []
    assert calculation.processed[0].realized_gain_loss == Decimal("8")
    assert calculation.open_lot_states["BUY-1"].quantity == Decimal("6")
    assert calculation.open_lot_states["BUY-1"].cost_base == Decimal("60")
    repo.get_transaction_history.assert_not_awaited()
    repo.get_fifo_disposal_lot_checkpoint_records.assert_awaited_once_with(
        portfolio_id="P1",
        security_id="S1",
        required_quantity=Decimal("4"),
    )
    repo.get_open_lot_checkpoint_records.assert_not_awaited()
    execution_metric.labels.assert_called_once_with(mode="ordered_append", cost_basis_method="FIFO")
    execution_metric.labels.return_value.inc.assert_called_once_with()
    restore_metric.labels.assert_called_once_with(cost_basis_method="FIFO")
    restore_metric.labels.return_value.observe.assert_called_once_with(1)


async def test_ordered_avco_sell_restores_one_aggregate_pool_source() -> None:
    workflow = CostCalculationWorkflow()
    repo = AsyncMock(spec=CostCalculatorRepository)
    buy_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    sell_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    prior_buy = _processed_buy("BUY-AVCO-1", buy_date)
    repo.get_cost_basis_processing_checkpoint.return_value = (
        CostBasisProcessingCheckpoint.from_transaction(
            prior_buy, cost_basis_method=CostBasisMethod.AVCO
        )
    )
    repo.get_average_cost_pool_checkpoint_record.return_value = AverageCostPoolCheckpointRecord(
        checkpoint=AverageCostPoolCheckpoint(
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            representative_source_transaction_id="BUY-AVCO-1",
            quantity=Decimal("10"),
            cost_local=Decimal("100"),
            cost_base=Decimal("100"),
        ),
        representative_transaction=_persisted_buy("BUY-AVCO-1", buy_date),
    )
    sell_event, sell_type, method = await workflow._prepare_transaction_event(
        _event(
            transaction_id="SELL-AVCO-1",
            transaction_date=sell_date,
            transaction_type="SELL",
            quantity="4",
        ),
        MagicMock(cost_basis_method="AVCO"),
    )

    calculation = await workflow._calculate_cost_basis(
        event=sell_event,
        event_transaction_type=sell_type,
        portfolio_base_currency="USD",
        instrument=MagicMock(product_type="EQUITY", asset_class="EQUITY"),
        repo=repo,
        cost_basis_method=method,
    )

    assert calculation.incremental is True
    assert calculation.errored == []
    assert calculation.open_lot_state_update_scope is OpenLotStateUpdateScope.AVERAGE_COST_POOL
    assert calculation.average_cost_pool_transition is not None
    assert calculation.average_cost_pool_transition.existing_sources_after.quantity == Decimal("6")
    assert calculation.average_cost_pool_transition.existing_sources_after.cost_base == Decimal(
        "60"
    )
    assert calculation.average_cost_pool_transition.explicit_sources_after == {}
    repo.get_average_cost_pool_checkpoint_record.assert_awaited_once_with(
        portfolio_id="P1",
        security_id="S1",
    )
    repo.get_open_lot_checkpoint_records.assert_not_awaited()
    repo.get_fifo_disposal_lot_checkpoint_records.assert_not_awaited()


async def test_ordered_avco_buy_preserves_existing_pool_and_adds_explicit_source() -> None:
    workflow = CostCalculationWorkflow()
    repo = AsyncMock(spec=CostCalculatorRepository)
    first_buy_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    second_buy_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    prior_buy = _processed_buy("BUY-AVCO-1", first_buy_date)
    repo.get_cost_basis_processing_checkpoint.return_value = (
        CostBasisProcessingCheckpoint.from_transaction(
            prior_buy, cost_basis_method=CostBasisMethod.AVCO
        )
    )
    repo.get_average_cost_pool_checkpoint_record.return_value = AverageCostPoolCheckpointRecord(
        checkpoint=AverageCostPoolCheckpoint(
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            representative_source_transaction_id="BUY-AVCO-1",
            quantity=Decimal("10"),
            cost_local=Decimal("100"),
            cost_base=Decimal("100"),
        ),
        representative_transaction=_persisted_buy("BUY-AVCO-1", first_buy_date),
    )
    buy_event, buy_type, method = await workflow._prepare_transaction_event(
        _event(
            transaction_id="BUY-AVCO-2",
            transaction_date=second_buy_date,
            transaction_type="BUY",
            quantity="5",
        ),
        MagicMock(cost_basis_method="AVCO"),
    )

    calculation = await workflow._calculate_cost_basis(
        event=buy_event,
        event_transaction_type=buy_type,
        portfolio_base_currency="USD",
        instrument=MagicMock(product_type="EQUITY", asset_class="EQUITY"),
        repo=repo,
        cost_basis_method=method,
    )

    assert calculation.incremental is True
    assert calculation.errored == []
    assert calculation.average_cost_pool_transition is not None
    transition = calculation.average_cost_pool_transition
    assert transition.existing_sources_after.quantity == Decimal("10")
    assert transition.explicit_sources_after["BUY-AVCO-2"].quantity == Decimal("5")
    assert transition.after.quantity == Decimal("15")
    assert transition.after.representative_source_transaction_id == "BUY-AVCO-2"
    repo.get_transaction_history.assert_not_awaited()
    repo.get_open_lot_checkpoint_records.assert_not_awaited()


async def test_ordered_avco_event_without_pool_checkpoint_uses_full_rebuild() -> None:
    workflow = CostCalculationWorkflow()
    repo = AsyncMock(spec=CostCalculatorRepository)
    buy_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    sell_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    prior_buy = _processed_buy("BUY-AVCO-1", buy_date)
    repo.get_cost_basis_processing_checkpoint.return_value = (
        CostBasisProcessingCheckpoint.from_transaction(
            prior_buy, cost_basis_method=CostBasisMethod.AVCO
        )
    )
    repo.get_average_cost_pool_checkpoint_record.return_value = None
    repo.get_transaction_history.return_value = [_persisted_buy("BUY-AVCO-1", buy_date)]
    sell_event, sell_type, method = await workflow._prepare_transaction_event(
        _event(
            transaction_id="SELL-AVCO-1",
            transaction_date=sell_date,
            transaction_type="SELL",
            quantity="4",
        ),
        MagicMock(cost_basis_method="AVCO"),
    )

    calculation = await workflow._calculate_cost_basis(
        event=sell_event,
        event_transaction_type=sell_type,
        portfolio_base_currency="USD",
        instrument=MagicMock(product_type="EQUITY", asset_class="EQUITY"),
        repo=repo,
        cost_basis_method=method,
    )

    assert calculation.incremental is False
    assert calculation.average_cost_pool_transition is None
    assert calculation.errored == []
    repo.get_transaction_history.assert_awaited_once()
    repo.get_open_lot_checkpoint_records.assert_not_awaited()


async def test_average_cost_pool_rebuild_plan_replays_complete_canonical_history() -> None:
    workflow = CostCalculationWorkflow()
    repo = AsyncMock(spec=CostCalculatorRepository)
    first_buy_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    second_buy_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    sell_date = datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc)
    repo.get_portfolio.return_value = MagicMock(cost_basis_method="AVCO", base_currency="USD")
    repo.get_instrument.return_value = MagicMock(product_type="EQUITY", asset_class="EQUITY")
    repo.get_transaction_history.return_value = [
        _persisted_buy("BUY-AVCO-1", first_buy_date),
        DBTransaction(
            transaction_id="BUY-AVCO-2",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_type="BUY",
            transaction_date=second_buy_date,
            quantity=Decimal("5"),
            price=Decimal("10"),
            gross_transaction_amount=Decimal("50"),
            trade_currency="USD",
            currency="USD",
        ),
        DBTransaction(
            transaction_id="SELL-AVCO-1",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_type="SELL",
            transaction_date=sell_date,
            quantity=Decimal("4"),
            price=Decimal("12"),
            gross_transaction_amount=Decimal("48"),
            trade_currency="USD",
            currency="USD",
        ),
    ]

    plan = await workflow.build_average_cost_pool_rebuild_plan(
        portfolio_id="P1",
        security_id="S1",
        repo=repo,
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
    repo.get_transaction_history.assert_awaited_once_with(
        portfolio_id="P1",
        security_id="S1",
    )


async def test_average_cost_pool_rebuild_plan_rejects_non_avco_portfolio() -> None:
    repo = AsyncMock(spec=CostCalculatorRepository)
    repo.get_portfolio.return_value = MagicMock(cost_basis_method="FIFO", base_currency="USD")

    with pytest.raises(ValueError, match="requires an AVCO portfolio"):
        await CostCalculationWorkflow().build_average_cost_pool_rebuild_plan(
            portfolio_id="P1",
            security_id="S1",
            repo=repo,
        )

    repo.get_transaction_history.assert_not_awaited()


async def test_average_cost_pool_rebuild_plan_fails_closed_on_invalid_history() -> None:
    repo = AsyncMock(spec=CostCalculatorRepository)
    repo.get_portfolio.return_value = MagicMock(cost_basis_method="AVCO", base_currency="USD")
    repo.get_instrument.return_value = MagicMock(product_type="EQUITY", asset_class="EQUITY")
    repo.get_transaction_history.return_value = [
        DBTransaction(
            transaction_id="SELL-AVCO-INVALID",
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            transaction_type="SELL",
            transaction_date=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            quantity=Decimal("1"),
            price=Decimal("12"),
            gross_transaction_amount=Decimal("12"),
            trade_currency="USD",
            currency="USD",
        )
    ]

    with pytest.raises(ValueError, match="Cost-basis calculation failed"):
        await CostCalculationWorkflow().build_average_cost_pool_rebuild_plan(
            portfolio_id="P1",
            security_id="S1",
            repo=repo,
        )


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

    with patch(
        "src.services.calculators.cost_calculator_service.app.cost_calculation_workflow."
        "COST_PROCESSING_EXECUTION_TOTAL"
    ) as execution_metric:
        calculation = await workflow._calculate_cost_basis(
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
    assert calculation.open_lot_state_update_scope is OpenLotStateUpdateScope.COMPLETE_SNAPSHOT
    assert calculation.errored == []
    assert [transaction.transaction_id for transaction in calculation.processed] == [
        "BUY-EARLIER",
        "BUY-LATER",
    ]
    repo.get_transaction_history.assert_awaited_once()
    execution_metric.labels.assert_called_once_with(mode="full_rebuild", cost_basis_method="FIFO")


@pytest.mark.parametrize("cost_basis_method", [CostBasisMethod.FIFO, CostBasisMethod.AVCO])
async def test_non_lot_full_rebuild_refreshes_open_lot_cost_snapshot(
    cost_basis_method: CostBasisMethod,
) -> None:
    workflow = CostCalculationWorkflow()
    repo = AsyncMock(spec=CostCalculatorRepository)
    buy_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    dividend_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    repo.get_cost_basis_processing_checkpoint.return_value = None
    repo.get_transaction_history.return_value = [_persisted_buy("BUY-1", buy_date)]
    dividend = _event(
        transaction_id="DIVIDEND-1",
        transaction_date=dividend_date,
        transaction_type="DIVIDEND",
        quantity="0",
    )

    calculation = await workflow._calculate_cost_basis(
        event=dividend,
        event_transaction_type="DIVIDEND",
        portfolio_base_currency="USD",
        instrument=MagicMock(product_type="EQUITY", asset_class="EQUITY"),
        repo=repo,
        cost_basis_method=cost_basis_method,
    )
    await workflow._update_open_lot_states_if_required(
        event=dividend,
        event_transaction_type="DIVIDEND",
        open_lot_states=calculation.open_lot_states,
        repo=repo,
        incremental=calculation.incremental,
        update_scope=calculation.open_lot_state_update_scope,
        cost_basis_method=cost_basis_method,
        average_cost_pool_transition=calculation.average_cost_pool_transition,
    )

    assert calculation.incremental is False
    assert calculation.open_lot_state_update_scope is OpenLotStateUpdateScope.COMPLETE_SNAPSHOT
    assert calculation.open_lot_states["BUY-1"].quantity == Decimal("10")
    assert calculation.open_lot_states["BUY-1"].cost_base == Decimal("100")
    if cost_basis_method is CostBasisMethod.FIFO:
        repo.update_open_lot_states.assert_awaited_once_with(
            portfolio_id="P1",
            security_id="S1",
            states_by_source_transaction_id=calculation.open_lot_states,
        )
        repo.upsert_average_cost_pool_checkpoint.assert_not_awaited()
    else:
        repo.update_open_lot_states.assert_awaited_once_with(
            portfolio_id="P1",
            security_id="S1",
            states_by_source_transaction_id=calculation.open_lot_states,
        )
        persisted_pool = repo.upsert_average_cost_pool_checkpoint.await_args.args[0]
        assert persisted_pool.quantity == Decimal("10")
        assert persisted_pool.cost_base == Decimal("100")
