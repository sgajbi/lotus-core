"""Verify deterministic cost-basis calculation coordination through application ports."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.cost_basis_method import CostBasisMethod
from portfolio_common.events import TransactionEvent

from src.services.portfolio_transaction_processing_service.app.application import (
    cost_basis_processing,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    AverageCostPoolCheckpoint,
    CostBasisProcessingCheckpoint,
    OpenLotState,
    build_cost_basis_engine_input,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction as EngineTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_mapping import (  # noqa: E501
    booked_transaction,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    AverageCostPoolCheckpointRecord,
    CostBasisAverageCostPoolPort,
    CostBasisCalculationObserver,
    CostBasisExecutionMode,
    CostBasisFxRatePort,
    CostBasisInstrumentReference,
    CostBasisLotStatePort,
    CostBasisProcessingStatePort,
    CostBasisTransactionStatePort,
    OpenLotCheckpointRecord,
)

pytestmark = pytest.mark.asyncio

OpenLotPersistenceScope = cost_basis_processing.OpenLotPersistenceScope
CostBasisCalculationCoordinator = cost_basis_processing.CostBasisCalculationCoordinator
CostBasisCalculationResult = cost_basis_processing.CostBasisCalculationResult
persist_open_lot_state = cost_basis_processing.persist_open_lot_state


def _fx_rate_port() -> AsyncMock:
    """Provide an isolated effective-rate dependency for one workflow test."""

    return AsyncMock(spec=CostBasisFxRatePort)


def _processing_state_port() -> AsyncMock:
    """Provide an isolated replay-frontier dependency for one workflow test."""

    return AsyncMock(spec=CostBasisProcessingStatePort)


def _average_cost_pool_port() -> AsyncMock:
    """Provide an isolated average-cost persistence dependency for one workflow test."""

    return AsyncMock(spec=CostBasisAverageCostPoolPort)


def _lot_state_port() -> AsyncMock:
    """Provide an isolated open-lot persistence dependency for one workflow test."""

    return AsyncMock(spec=CostBasisLotStatePort)


def _calculation_coordinator(
    *,
    transactions: CostBasisTransactionStatePort,
    average_cost_pools: CostBasisAverageCostPoolPort,
    lot_states: CostBasisLotStatePort,
    fx_rates: CostBasisFxRatePort,
    processing_state: CostBasisProcessingStatePort,
    observer: CostBasisCalculationObserver | None = None,
) -> CostBasisCalculationCoordinator:
    """Build the application coordinator with isolated state ports."""

    return CostBasisCalculationCoordinator(
        transactions=transactions,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        fx_rates=fx_rates,
        processing_state=processing_state,
        observer=observer,
    )


async def _calculate_cost_basis(
    *,
    event: TransactionEvent,
    event_transaction_type: str,
    portfolio_base_currency: str,
    instrument: CostBasisInstrumentReference | None,
    repo: CostBasisTransactionStatePort,
    average_cost_pools: CostBasisAverageCostPoolPort,
    lot_states: CostBasisLotStatePort,
    fx_rates: CostBasisFxRatePort,
    processing_state: CostBasisProcessingStatePort,
    cost_basis_method: CostBasisMethod,
    observer: CostBasisCalculationObserver | None = None,
) -> CostBasisCalculationResult:
    """Calculate through the framework-neutral application boundary used in production."""

    return await _calculation_coordinator(
        transactions=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        fx_rates=fx_rates,
        processing_state=processing_state,
        observer=observer,
    ).calculate(
        transaction=booked_transaction.to_booked_transaction(event),
        transaction_type=event_transaction_type,
        portfolio_base_currency=portfolio_base_currency,
        instrument=instrument,
        cost_basis_method=cost_basis_method,
    )


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
    payload = build_cost_basis_engine_input(
        booked_transaction.to_booked_transaction(
            _event(
                transaction_id=transaction_id,
                transaction_date=transaction_date,
                transaction_type="BUY",
                quantity="10",
            )
        )
    )
    payload.update(
        portfolio_base_currency="USD",
        net_cost_local=Decimal("100"),
        net_cost=Decimal("100"),
    )
    return EngineTransaction(**payload)


def _prepare_event(
    event: TransactionEvent,
    cost_basis_method: CostBasisMethod,
) -> tuple[TransactionEvent, str, CostBasisMethod]:
    prepared = cost_basis_processing.prepare_cost_transaction(
        booked_transaction.to_booked_transaction(event),
        cost_basis_method=cost_basis_method,
        instrument_reference_available=True,
    )
    return (
        booked_transaction.with_booked_transaction_fields(event, prepared.transaction),
        prepared.transaction_type,
        prepared.cost_basis_method,
    )


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


def _history_transaction(transaction: DBTransaction) -> BookedTransaction:
    """Map a persisted test row through the repository's canonical history boundary."""

    return booked_transaction.to_booked_transaction(TransactionEvent.model_validate(transaction))


async def test_later_sell_restores_open_lots_without_loading_full_history() -> None:
    observer = MagicMock(spec=CostBasisCalculationObserver)
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    processing_state = _processing_state_port()
    average_cost_pools = _average_cost_pool_port()
    lot_states = _lot_state_port()
    buy_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    sell_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    prior_buy = _processed_buy("BUY-1", buy_date)
    processing_state.get_cost_basis_processing_checkpoint.return_value = (
        CostBasisProcessingCheckpoint.from_transaction(
            prior_buy, cost_basis_method=CostBasisMethod.FIFO
        )
    )
    lot_states.get_fifo_disposal_lot_checkpoint_records.return_value = [
        OpenLotCheckpointRecord(
            transaction=_history_transaction(_persisted_buy("BUY-1", buy_date)),
            quantity=Decimal("10"),
            cost_local=Decimal("100"),
            cost_base=Decimal("100"),
        )
    ]
    sell_event, sell_type, method = _prepare_event(
        _event(
            transaction_id="SELL-1",
            transaction_date=sell_date,
            transaction_type="SELL",
            quantity="4",
        ),
        CostBasisMethod.FIFO,
    )

    calculation = await _calculate_cost_basis(
        event=sell_event,
        event_transaction_type=sell_type,
        portfolio_base_currency="USD",
        instrument=MagicMock(product_type="EQUITY", asset_class="EQUITY"),
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        fx_rates=_fx_rate_port(),
        processing_state=processing_state,
        cost_basis_method=method,
        observer=observer,
    )

    assert calculation.incremental is True
    assert calculation.open_lot_persistence_scope is OpenLotPersistenceScope.SELECTED_LOTS
    assert calculation.errored == []
    assert calculation.processed[0].realized_gain_loss == Decimal("8")
    assert calculation.open_lot_states["BUY-1"].quantity == Decimal("6")
    assert calculation.open_lot_states["BUY-1"].cost_base == Decimal("60")
    repo.get_transaction_history.assert_not_awaited()
    lot_states.get_fifo_disposal_lot_checkpoint_records.assert_awaited_once_with(
        portfolio_id="P1",
        security_id="S1",
        required_quantity=Decimal("4"),
    )
    lot_states.get_open_lot_checkpoint_records.assert_not_awaited()
    observer.record_execution.assert_called_once_with(CostBasisExecutionMode.ORDERED_APPEND, "FIFO")
    observer.record_restored_open_lots.assert_called_once_with(
        cost_basis_method="FIFO",
        lot_count=1,
    )


async def test_ordered_avco_sell_restores_one_aggregate_pool_source() -> None:
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    processing_state = _processing_state_port()
    average_cost_pools = _average_cost_pool_port()
    lot_states = _lot_state_port()
    buy_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    sell_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    prior_buy = _processed_buy("BUY-AVCO-1", buy_date)
    processing_state.get_cost_basis_processing_checkpoint.return_value = (
        CostBasisProcessingCheckpoint.from_transaction(
            prior_buy, cost_basis_method=CostBasisMethod.AVCO
        )
    )
    average_cost_pools.get_average_cost_pool_checkpoint_record.return_value = (
        AverageCostPoolCheckpointRecord(
            checkpoint=AverageCostPoolCheckpoint(
                portfolio_id="P1",
                instrument_id="I1",
                security_id="S1",
                representative_source_transaction_id="BUY-AVCO-1",
                quantity=Decimal("10"),
                cost_local=Decimal("100"),
                cost_base=Decimal("100"),
            ),
            representative_transaction=_history_transaction(_persisted_buy("BUY-AVCO-1", buy_date)),
        )
    )
    sell_event, sell_type, method = _prepare_event(
        _event(
            transaction_id="SELL-AVCO-1",
            transaction_date=sell_date,
            transaction_type="SELL",
            quantity="4",
        ),
        CostBasisMethod.AVCO,
    )

    calculation = await _calculate_cost_basis(
        event=sell_event,
        event_transaction_type=sell_type,
        portfolio_base_currency="USD",
        instrument=MagicMock(product_type="EQUITY", asset_class="EQUITY"),
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        fx_rates=_fx_rate_port(),
        processing_state=processing_state,
        cost_basis_method=method,
    )

    assert calculation.incremental is True
    assert calculation.errored == []
    assert calculation.open_lot_persistence_scope is OpenLotPersistenceScope.AVERAGE_COST_POOL
    assert calculation.average_cost_pool_transition is not None
    assert calculation.average_cost_pool_transition.existing_sources_after.quantity == Decimal("6")
    assert calculation.average_cost_pool_transition.existing_sources_after.cost_base == Decimal(
        "60"
    )
    assert calculation.average_cost_pool_transition.explicit_sources_after == {}
    average_cost_pools.get_average_cost_pool_checkpoint_record.assert_awaited_once_with(
        portfolio_id="P1",
        security_id="S1",
    )
    lot_states.get_open_lot_checkpoint_records.assert_not_awaited()
    lot_states.get_fifo_disposal_lot_checkpoint_records.assert_not_awaited()


async def test_ordered_avco_buy_preserves_existing_pool_and_adds_explicit_source() -> None:
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    processing_state = _processing_state_port()
    average_cost_pools = _average_cost_pool_port()
    lot_states = _lot_state_port()
    first_buy_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    second_buy_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    prior_buy = _processed_buy("BUY-AVCO-1", first_buy_date)
    processing_state.get_cost_basis_processing_checkpoint.return_value = (
        CostBasisProcessingCheckpoint.from_transaction(
            prior_buy, cost_basis_method=CostBasisMethod.AVCO
        )
    )
    average_cost_pools.get_average_cost_pool_checkpoint_record.return_value = (
        AverageCostPoolCheckpointRecord(
            checkpoint=AverageCostPoolCheckpoint(
                portfolio_id="P1",
                instrument_id="I1",
                security_id="S1",
                representative_source_transaction_id="BUY-AVCO-1",
                quantity=Decimal("10"),
                cost_local=Decimal("100"),
                cost_base=Decimal("100"),
            ),
            representative_transaction=_history_transaction(
                _persisted_buy("BUY-AVCO-1", first_buy_date)
            ),
        )
    )
    buy_event, buy_type, method = _prepare_event(
        _event(
            transaction_id="BUY-AVCO-2",
            transaction_date=second_buy_date,
            transaction_type="BUY",
            quantity="5",
        ),
        CostBasisMethod.AVCO,
    )

    calculation = await _calculate_cost_basis(
        event=buy_event,
        event_transaction_type=buy_type,
        portfolio_base_currency="USD",
        instrument=MagicMock(product_type="EQUITY", asset_class="EQUITY"),
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        fx_rates=_fx_rate_port(),
        processing_state=processing_state,
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
    lot_states.get_open_lot_checkpoint_records.assert_not_awaited()


async def test_ordered_avco_event_without_pool_checkpoint_uses_full_rebuild() -> None:
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    processing_state = _processing_state_port()
    average_cost_pools = _average_cost_pool_port()
    lot_states = _lot_state_port()
    buy_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    sell_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    prior_buy = _processed_buy("BUY-AVCO-1", buy_date)
    processing_state.get_cost_basis_processing_checkpoint.return_value = (
        CostBasisProcessingCheckpoint.from_transaction(
            prior_buy, cost_basis_method=CostBasisMethod.AVCO
        )
    )
    average_cost_pools.get_average_cost_pool_checkpoint_record.return_value = None
    repo.get_transaction_history.return_value = [
        _history_transaction(_persisted_buy("BUY-AVCO-1", buy_date))
    ]
    sell_event, sell_type, method = _prepare_event(
        _event(
            transaction_id="SELL-AVCO-1",
            transaction_date=sell_date,
            transaction_type="SELL",
            quantity="4",
        ),
        CostBasisMethod.AVCO,
    )

    calculation = await _calculate_cost_basis(
        event=sell_event,
        event_transaction_type=sell_type,
        portfolio_base_currency="USD",
        instrument=MagicMock(product_type="EQUITY", asset_class="EQUITY"),
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        fx_rates=_fx_rate_port(),
        processing_state=processing_state,
        cost_basis_method=method,
    )

    assert calculation.incremental is False
    assert calculation.average_cost_pool_transition is None
    assert calculation.errored == []
    repo.get_transaction_history.assert_awaited_once()
    lot_states.get_open_lot_checkpoint_records.assert_not_awaited()


async def test_backdated_transaction_uses_full_deterministic_history() -> None:
    observer = MagicMock(spec=CostBasisCalculationObserver)
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    processing_state = _processing_state_port()
    average_cost_pools = _average_cost_pool_port()
    lot_states = _lot_state_port()
    later_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    earlier_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    later_buy = _processed_buy("BUY-LATER", later_date)
    processing_state.get_cost_basis_processing_checkpoint.return_value = (
        CostBasisProcessingCheckpoint.from_transaction(
            later_buy, cost_basis_method=CostBasisMethod.FIFO
        )
    )
    repo.get_transaction_history.return_value = [
        _history_transaction(_persisted_buy("BUY-LATER", later_date))
    ]

    calculation = await _calculate_cost_basis(
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
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        fx_rates=_fx_rate_port(),
        processing_state=processing_state,
        cost_basis_method=CostBasisMethod.FIFO,
        observer=observer,
    )

    assert calculation.incremental is False
    assert calculation.open_lot_persistence_scope is OpenLotPersistenceScope.COMPLETE_SNAPSHOT
    assert calculation.errored == []
    assert [transaction.transaction_id for transaction in calculation.processed] == [
        "BUY-EARLIER",
        "BUY-LATER",
    ]
    repo.get_transaction_history.assert_awaited_once()
    observer.record_execution.assert_called_once_with(CostBasisExecutionMode.FULL_REBUILD, "FIFO")


@pytest.mark.parametrize("cost_basis_method", [CostBasisMethod.FIFO, CostBasisMethod.AVCO])
async def test_non_lot_full_rebuild_refreshes_open_lot_cost_snapshot(
    cost_basis_method: CostBasisMethod,
) -> None:
    repo = AsyncMock(spec=CostBasisTransactionStatePort)
    processing_state = _processing_state_port()
    average_cost_pools = _average_cost_pool_port()
    lot_states = _lot_state_port()
    buy_date = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    dividend_date = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    processing_state.get_cost_basis_processing_checkpoint.return_value = None
    repo.get_transaction_history.return_value = [
        _history_transaction(_persisted_buy("BUY-1", buy_date))
    ]
    dividend = _event(
        transaction_id="DIVIDEND-1",
        transaction_date=dividend_date,
        transaction_type="DIVIDEND",
        quantity="0",
    )

    calculation = await _calculate_cost_basis(
        event=dividend,
        event_transaction_type="DIVIDEND",
        portfolio_base_currency="USD",
        instrument=MagicMock(product_type="EQUITY", asset_class="EQUITY"),
        repo=repo,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        fx_rates=_fx_rate_port(),
        processing_state=processing_state,
        cost_basis_method=cost_basis_method,
    )
    await persist_open_lot_state(
        transaction=booked_transaction.to_booked_transaction(dividend),
        effective_transaction_type="DIVIDEND",
        open_lot_states=calculation.open_lot_states,
        average_cost_pools=average_cost_pools,
        lot_states=lot_states,
        incremental=calculation.incremental,
        persistence_scope=calculation.open_lot_persistence_scope,
        cost_basis_method=cost_basis_method,
        average_cost_pool_transition=calculation.average_cost_pool_transition,
    )

    assert calculation.incremental is False
    assert calculation.open_lot_persistence_scope is OpenLotPersistenceScope.COMPLETE_SNAPSHOT
    assert calculation.open_lot_states["BUY-1"].quantity == Decimal("10")
    assert calculation.open_lot_states["BUY-1"].cost_base == Decimal("100")
    if cost_basis_method is CostBasisMethod.FIFO:
        lot_states.update_open_lot_states.assert_awaited_once_with(
            portfolio_id="P1",
            security_id="S1",
            states_by_source_transaction_id=calculation.open_lot_states,
        )
        average_cost_pools.upsert_average_cost_pool_checkpoint.assert_not_awaited()
    else:
        lot_states.update_open_lot_states.assert_awaited_once_with(
            portfolio_id="P1",
            security_id="S1",
            states_by_source_transaction_id=calculation.open_lot_states,
        )
        persisted_pool = average_cost_pools.upsert_average_cost_pool_checkpoint.await_args.args[0]
        assert persisted_pool.quantity == Decimal("10")
        assert persisted_pool.cost_base == Decimal("100")


async def test_positive_average_cost_pool_without_representative_row_is_not_restored() -> None:
    average_cost_pools = _average_cost_pool_port()
    event = _event(
        transaction_id="SELL-AVCO-MISSING-ROW",
        transaction_date=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
        transaction_type="SELL",
        quantity="2",
    )
    average_cost_pools.get_average_cost_pool_checkpoint_record.return_value = (
        AverageCostPoolCheckpointRecord(
            checkpoint=AverageCostPoolCheckpoint(
                portfolio_id="P1",
                instrument_id="I1",
                security_id="S1",
                representative_source_transaction_id="BUY-AVCO-1",
                quantity=Decimal("10"),
                cost_local=Decimal("100"),
                cost_base=Decimal("100"),
            ),
            representative_transaction=None,
        )
    )

    coordinator = _calculation_coordinator(
        transactions=AsyncMock(spec=CostBasisTransactionStatePort),
        average_cost_pools=average_cost_pools,
        lot_states=_lot_state_port(),
        fx_rates=_fx_rate_port(),
        processing_state=_processing_state_port(),
    )
    checkpoint = await coordinator._get_compatible_average_cost_pool_checkpoint(
        booked_transaction.to_booked_transaction(event)
    )

    assert checkpoint is None


async def test_average_cost_pool_checkpoint_restore_handles_closed_missing_and_open_sources() -> (
    None
):
    closed_record = AverageCostPoolCheckpointRecord(
        checkpoint=AverageCostPoolCheckpoint(
            portfolio_id="P1",
            instrument_id="I1",
            security_id="S1",
            representative_source_transaction_id=None,
            quantity=Decimal(0),
            cost_local=Decimal(0),
            cost_base=Decimal(0),
        ),
        representative_transaction=None,
    )
    open_checkpoint = AverageCostPoolCheckpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id="BUY-AVCO-1",
        quantity=Decimal("10"),
        cost_local=Decimal("100"),
        cost_base=Decimal("100"),
    )

    assert (
        CostBasisCalculationCoordinator._load_average_cost_pool_checkpoint_transaction(
            record=closed_record,
            portfolio_base_currency="USD",
            instrument=None,
        )
        == []
    )
    with pytest.raises(ValueError, match="no representative transaction"):
        CostBasisCalculationCoordinator._load_average_cost_pool_checkpoint_transaction(
            record=AverageCostPoolCheckpointRecord(
                checkpoint=open_checkpoint,
                representative_transaction=None,
            ),
            portfolio_base_currency="USD",
            instrument=None,
        )

    restored = CostBasisCalculationCoordinator._load_average_cost_pool_checkpoint_transaction(
        record=AverageCostPoolCheckpointRecord(
            checkpoint=open_checkpoint,
            representative_transaction=_history_transaction(
                _persisted_buy(
                    "BUY-AVCO-1",
                    datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
                )
            ),
        ),
        portfolio_base_currency="USD",
        instrument=None,
    )

    assert len(restored) == 1
    assert restored[0]["quantity"] == Decimal("10")
    assert restored[0]["net_cost"] == Decimal("100")


async def test_average_cost_pool_transition_rejects_missing_representative_state() -> None:
    closed_checkpoint = AverageCostPoolCheckpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id=None,
        quantity=Decimal(0),
        cost_local=Decimal(0),
        cost_base=Decimal(0),
    )
    closed_transition = CostBasisCalculationCoordinator._build_average_cost_pool_transition(
        checkpoint=closed_checkpoint,
        open_lot_states={},
    )
    assert closed_transition.existing_sources_after == OpenLotState(
        quantity=Decimal(0),
        cost_local=Decimal(0),
        cost_base=Decimal(0),
    )

    open_checkpoint = AverageCostPoolCheckpoint(
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        representative_source_transaction_id="BUY-AVCO-1",
        quantity=Decimal("10"),
        cost_local=Decimal("100"),
        cost_base=Decimal("100"),
    )
    with pytest.raises(ValueError, match="omitted the aggregate representative source"):
        CostBasisCalculationCoordinator._build_average_cost_pool_transition(
            checkpoint=open_checkpoint,
            open_lot_states={},
        )

    malformed_checkpoint = MagicMock(
        quantity=Decimal("10"),
        representative_source_transaction_id=None,
    )
    with pytest.raises(ValueError, match="no representative source"):
        CostBasisCalculationCoordinator._build_average_cost_pool_transition(
            checkpoint=malformed_checkpoint,
            open_lot_states={},
        )
