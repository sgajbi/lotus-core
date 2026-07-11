# tests/unit/services/calculators/position_calculator/core/test_position_logic.py
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import PositionState
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from portfolio_common.position_state_repository import PositionStateRepository

from src.services.portfolio_transaction_processing_service.app.domain.position_reducer import (
    PositionBalanceState as PositionStateDTO,
)
from src.services.portfolio_transaction_processing_service.app.domain.position_reducer import (
    cash_position_deltas,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow import (  # noqa: E501
    PositionCalculationResult,
    PositionCalculationWorkflow,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position_repository import (  # noqa: E501
    PositionRepository,
)

# The module-level pytestmark is removed to apply the asyncio mark selectively.


class _StringCountedAmount:
    def __init__(self, value: str) -> None:
        self.value = value
        self.string_call_count = 0

    def __str__(self) -> str:
        self.string_call_count += 1
        return self.value


@pytest.fixture
def mock_repo() -> AsyncMock:
    """Provides a mock PositionRepository."""
    repo = AsyncMock(spec=PositionRepository)
    repo.get_transactions_on_or_after.return_value = []
    repo.get_last_position_before.return_value = None
    repo.get_latest_completed_snapshot_date.return_value = None
    repo.get_latest_position_history_date.return_value = None
    repo.is_transaction_materialized.return_value = False
    return repo


@pytest.fixture
def mock_state_repo() -> AsyncMock:
    """Provides a mock PositionStateRepository."""
    repo = AsyncMock(spec=PositionStateRepository)
    return repo


@pytest.fixture
def sample_event() -> TransactionEvent:
    """Provides a sample transaction event."""
    return TransactionEvent(
        transaction_id="T1",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime(2025, 8, 20),
        transaction_type="BUY",
        quantity=Decimal("50"),
        price=Decimal("110"),
        gross_transaction_amount=Decimal("5500"),
        trade_currency="USD",
        currency="USD",
        net_cost=Decimal("5505"),
        epoch=1,
    )


@pytest.mark.asyncio
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow.EpochFencer"
)
async def test_calculate_discards_stale_epoch_event(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    sample_event: TransactionEvent,
):
    """
    GIVEN an event that the EpochFencer deems stale
    WHEN PositionCalculationWorkflow.calculate is called
    THEN it should not perform any calculations or repository writes.
    """
    # ARRANGE
    mock_fencer_instance = mock_fencer_class.return_value
    mock_fencer_instance.check = AsyncMock(return_value=False)

    # ACT
    result = await PositionCalculationWorkflow.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo
    )

    # ASSERT
    mock_fencer_instance.check.assert_awaited_once_with(sample_event)
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.save_positions.assert_not_called()
    assert result.position_record_count == 0


@pytest.mark.asyncio
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow.EpochFencer"
)
async def test_calculate_normal_flow(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    sample_event: TransactionEvent,
):
    """
    GIVEN a transaction that is NOT backdated
    WHEN PositionCalculationWorkflow.calculate runs
    THEN it should proceed with the standard position calculation logic.
    """
    # ARRANGE
    mock_fencer_instance = mock_fencer_class.return_value
    mock_fencer_instance.check = AsyncMock(return_value=True)

    # Simulate a state where the transaction is not backdated
    mock_state_repo.get_or_create_state.return_value = PositionState(
        watermark_date=date(2025, 8, 19), epoch=1
    )
    mock_repo.get_latest_completed_snapshot_date.return_value = None
    mock_repo.get_transactions_on_or_after.return_value = [sample_event]

    # ACT
    result = await PositionCalculationWorkflow.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo
    )

    # ASSERT
    mock_fencer_instance.check.assert_awaited_once()
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.acquire_position_history_replay_lock.assert_awaited_once_with("P1", "S1", 1)
    mock_repo.save_positions.assert_awaited_once()
    assert result.position_record_count == 1


@pytest.mark.asyncio
async def test_recalculate_position_history_locks_key_before_delete(sample_event: TransactionEvent):
    """
    GIVEN concurrent workers may rebuild the same key/date window
    WHEN position history is recalculated
    THEN the transaction-scoped key lock is acquired before destructive replay starts.
    """
    call_order: list[str] = []
    repo = AsyncMock(spec=PositionRepository)
    state_repo = AsyncMock(spec=PositionStateRepository)
    state_repo.update_watermarks_if_older.return_value = 1
    current_state = PositionState(watermark_date=date(2025, 8, 19), epoch=1)

    async def acquire_lock(*_args, **_kwargs):
        call_order.append("lock")

    async def delete_positions(*_args, **_kwargs):
        call_order.append("delete")
        return 0

    repo.acquire_position_history_replay_lock.side_effect = acquire_lock
    repo.delete_positions_from.side_effect = delete_positions
    repo.get_last_position_before.return_value = None
    repo.get_transactions_on_or_after.return_value = [sample_event]

    await PositionCalculationWorkflow._recalculate_position_history(
        event=sample_event,
        repo=repo,
        position_state_repo=state_repo,
        current_state=current_state,
        transaction_date=sample_event.transaction_date.date(),
    )

    assert call_order[:2] == ["lock", "delete"]
    repo.acquire_position_history_replay_lock.assert_awaited_once_with("P1", "S1", 1)
    repo.delete_positions_from.assert_awaited_once_with("P1", "S1", date(2025, 8, 20), 1)


@pytest.mark.asyncio
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow.EpochFencer"
)
async def test_calculate_rearms_current_epoch_when_position_history_arrives_after_valuation(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    sample_event: TransactionEvent,
):
    """
    GIVEN a replay/current-epoch event materializes position history for a date
    already covered by valuation snapshots
    WHEN PositionCalculationWorkflow persists the corrected history
    THEN the current epoch watermark is reset so valuation and timeseries jobs
    are regenerated instead of leaving stale snapshots marked current.
    """
    mock_fencer_instance = mock_fencer_class.return_value
    mock_fencer_instance.check = AsyncMock(return_value=True)
    sample_event.epoch = 2
    sample_event.transaction_date = datetime(2026, 3, 11, 9, 0, 0)

    mock_state_repo.get_or_create_state.return_value = PositionState(
        watermark_date=date(2026, 4, 22), epoch=2, status="CURRENT"
    )
    mock_repo.get_latest_completed_snapshot_date.return_value = date(2026, 4, 22)
    mock_repo.get_latest_position_history_date.return_value = None
    mock_repo.get_transactions_on_or_after.return_value = [sample_event]
    mock_state_repo.update_watermarks_if_older.return_value = 1

    await PositionCalculationWorkflow.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo
    )

    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.save_positions.assert_awaited_once()
    mock_state_repo.update_watermarks_if_older.assert_awaited_once_with(
        keys=[("P1", "S1")],
        new_watermark_date=date(2026, 3, 10),
        touch_if_already_lagging=True,
    )


@pytest.mark.asyncio
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow."
    "POSITION_RECALCULATION_WORK_ITEMS"
)
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow.REPROCESSING_EPOCH_BUMPED_TOTAL"
)
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow.EpochFencer"
)
async def test_calculate_rebuilds_backdated_history_inline_without_replay_outbox(
    mock_fencer_class: MagicMock,
    mock_metric: MagicMock,
    mock_work_metric: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    sample_event: TransactionEvent,
) -> None:
    mock_fencer_class.return_value.check = AsyncMock(return_value=True)
    sample_event.epoch = None
    mock_state_repo.get_or_create_state.return_value = PositionState(
        watermark_date=date(2025, 8, 25),
        epoch=0,
    )
    mock_state_repo.increment_epoch_and_reset_watermark.return_value = PositionState(epoch=1)
    mock_state_repo.update_watermarks_if_older.return_value = 1
    mock_repo.get_all_transactions_for_security.return_value = [
        DBTransaction(
            transaction_id="TXN_HIST_1",
            portfolio_id="P1",
            security_id="S1",
            instrument_id="I1",
            transaction_date=datetime(2025, 1, 5),
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("100"),
            gross_transaction_amount=Decimal("100"),
            trade_currency="USD",
            currency="USD",
            trade_fee=Decimal("0"),
            net_cost=Decimal("100"),
        )
    ]

    result = await PositionCalculationWorkflow.calculate(
        sample_event,
        AsyncMock(),
        mock_repo,
        mock_state_repo,
    )

    mock_state_repo.increment_epoch_and_reset_watermark.assert_awaited_once_with(
        "P1", "S1", 0, date(2025, 8, 19)
    )
    mock_metric.labels.assert_called_once_with(trigger="backdated_transaction")
    mock_repo.acquire_position_history_replay_lock.assert_awaited_once_with("P1", "S1", 1)
    mock_repo.delete_positions_from.assert_awaited_once_with("P1", "S1", date(2025, 1, 5), 1)
    saved_positions = mock_repo.save_positions.await_args.args[0]
    assert [position.transaction_id for position in saved_positions] == ["TXN_HIST_1", "T1"]
    assert [position.epoch for position in saved_positions] == [1, 1]
    mock_work_metric.labels.assert_called_once_with(mode="inline_rebuild")
    mock_work_metric.labels.return_value.observe.assert_called_once_with(2)
    assert result.position_record_count == 2


@pytest.mark.asyncio
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow.EpochFencer"
)
async def test_calculate_treats_existing_position_history_as_backdated_boundary(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    sample_event: TransactionEvent,
):
    """
    GIVEN valuation snapshots have not advanced but position_history already
    exists past the incoming transaction date
    WHEN an original event arrives
    THEN reprocessing is still triggered because the position calculator has
    already materialized later-dated state in the current epoch.
    """
    mock_fencer_instance = mock_fencer_class.return_value
    mock_fencer_instance.check = AsyncMock(return_value=True)
    sample_event.epoch = None
    sample_event.transaction_date = datetime(2025, 8, 20, 10, 0, 0)

    mock_state_repo.get_or_create_state.return_value = PositionState(
        watermark_date=date(1970, 1, 1), epoch=0
    )
    mock_repo.get_latest_completed_snapshot_date.return_value = None
    mock_repo.get_latest_position_history_date.return_value = date(2025, 8, 21)
    mock_state_repo.increment_epoch_and_reset_watermark.return_value = PositionState(epoch=1)
    mock_repo.get_all_transactions_for_security.return_value = []

    result = await PositionCalculationWorkflow.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo
    )

    mock_state_repo.increment_epoch_and_reset_watermark.assert_awaited_once_with(
        "P1", "S1", 0, date(2025, 8, 19)
    )
    assert result.position_record_count == 1


@pytest.mark.asyncio
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow."
    "REPROCESSING_EPOCH_BUMPED_TOTAL"
)
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow."
    "POSITION_RECALCULATION_COORDINATION_TOTAL"
)
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow.EpochFencer"
)
async def test_calculate_skips_backdated_replay_when_epoch_bump_is_stale(
    mock_fencer_class: MagicMock,
    mock_coordination_metric: MagicMock,
    mock_epoch_metric: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    sample_event: TransactionEvent,
):
    """
    GIVEN a back-dated original event
    WHEN the epoch bump loses its fence because another worker already advanced state
    THEN no replay outbox events should be staged from the stale loser path.
    """
    mock_fencer_instance = mock_fencer_class.return_value
    mock_fencer_instance.check = AsyncMock(return_value=True)
    sample_event.epoch = None

    mock_state_repo.get_or_create_state.return_value = PositionState(
        watermark_date=date(2025, 8, 25), epoch=0
    )
    mock_repo.get_latest_completed_snapshot_date.return_value = None
    mock_repo.get_latest_position_history_date.return_value = None
    mock_state_repo.increment_epoch_and_reset_watermark.return_value = None

    await PositionCalculationWorkflow.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo
    )

    mock_state_repo.increment_epoch_and_reset_watermark.assert_awaited_once_with(
        "P1", "S1", 0, date(2025, 8, 19)
    )
    mock_repo.get_all_transactions_for_security.assert_not_awaited()
    mock_epoch_metric.labels.assert_not_called()
    mock_coordination_metric.labels.assert_called_once_with(
        outcome="coalesced",
        reason="stale_epoch",
    )
    mock_coordination_metric.labels.return_value.inc.assert_called_once_with()


@pytest.mark.asyncio
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow."
    "POSITION_RECALCULATION_COORDINATION_TOTAL"
)
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow."
    "POSITION_RECALCULATION_WORK_ITEMS"
)
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow.EpochFencer"
)
async def test_calculate_coalesces_backdated_event_already_materialized_in_current_epoch(
    mock_fencer_class: MagicMock,
    mock_work_metric: MagicMock,
    mock_coordination_metric: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    sample_event: TransactionEvent,
) -> None:
    mock_fencer_class.return_value.check = AsyncMock(return_value=True)
    sample_event.epoch = None
    mock_state_repo.get_or_create_state.return_value = PositionState(
        watermark_date=date(2025, 8, 25), epoch=3
    )
    mock_repo.get_latest_position_history_date.return_value = date(2025, 8, 25)
    mock_repo.is_transaction_materialized.return_value = True

    result = await PositionCalculationWorkflow.calculate(
        sample_event,
        AsyncMock(),
        mock_repo,
        mock_state_repo,
    )

    assert result.position_record_count == 0
    mock_repo.is_transaction_materialized.assert_awaited_once_with("P1", "S1", "T1", 3)
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_awaited()
    mock_repo.get_all_transactions_for_security.assert_not_awaited()
    mock_coordination_metric.labels.assert_called_once_with(
        outcome="coalesced",
        reason="already_materialized",
    )
    mock_coordination_metric.labels.return_value.inc.assert_called_once_with()
    mock_work_metric.labels.assert_called_once_with(mode="coalesced")
    mock_work_metric.labels.return_value.observe.assert_called_once_with(0)


@pytest.mark.asyncio
@patch.object(
    PositionCalculationWorkflow,
    "_rebuild_backdated_position_history",
    new_callable=AsyncMock,
)
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow.EpochFencer"
)
async def test_calculate_rebuilds_materialized_backdated_event_for_explicit_correction(
    mock_fencer_class: MagicMock,
    mock_rebuild: AsyncMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    sample_event: TransactionEvent,
) -> None:
    mock_fencer_class.return_value.check = AsyncMock(return_value=True)
    mock_rebuild.return_value = PositionCalculationResult(position_record_count=2)
    sample_event.epoch = None
    current_state = PositionState(watermark_date=date(2025, 8, 25), epoch=3)
    mock_state_repo.get_or_create_state.return_value = current_state
    mock_repo.get_latest_position_history_date.return_value = date(2025, 8, 25)
    mock_repo.is_transaction_materialized.return_value = True

    result = await PositionCalculationWorkflow.calculate(
        sample_event,
        AsyncMock(),
        mock_repo,
        mock_state_repo,
        rebuild_existing=True,
    )

    assert result.position_record_count == 2
    mock_repo.is_transaction_materialized.assert_not_awaited()
    mock_rebuild.assert_awaited_once()


@pytest.mark.asyncio
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow.EpochFencer"
)
async def test_calculate_backdated_replay_has_deterministic_tie_break_order(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    sample_event: TransactionEvent,
):
    """
    GIVEN backdated replay candidates with identical transaction_date
    WHEN reprocessing is triggered
    THEN replay order is deterministic by transaction ordering key, not DB arrival order.
    """
    mock_fencer_instance = mock_fencer_class.return_value
    mock_fencer_instance.check = AsyncMock(return_value=True)
    sample_event.epoch = None
    sample_event.transaction_id = "TXN_C"
    sample_event.transaction_date = datetime(2025, 8, 20, 10, 0, 0)

    mock_state_repo.get_or_create_state.return_value = PositionState(
        watermark_date=date(2025, 8, 25), epoch=0
    )
    mock_state_repo.increment_epoch_and_reset_watermark.return_value = PositionState(epoch=1)

    # Intentionally unsorted by transaction_id.
    mock_repo.get_all_transactions_for_security.return_value = [
        DBTransaction(
            transaction_id="TXN_B",
            portfolio_id="P1",
            security_id="S1",
            instrument_id="I1",
            transaction_date=datetime(2025, 8, 20, 10, 0, 0),
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("1"),
            gross_transaction_amount=Decimal("1"),
            trade_currency="USD",
            currency="USD",
            trade_fee=Decimal("0"),
        ),
        DBTransaction(
            transaction_id="TXN_A",
            portfolio_id="P1",
            security_id="S1",
            instrument_id="I1",
            transaction_date=datetime(2025, 8, 20, 10, 0, 0),
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("1"),
            gross_transaction_amount=Decimal("1"),
            trade_currency="USD",
            currency="USD",
            trade_fee=Decimal("0"),
        ),
    ]

    await PositionCalculationWorkflow.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo
    )

    positions = mock_repo.save_positions.await_args.args[0]
    assert [position.transaction_id for position in positions] == ["TXN_A", "TXN_B", "TXN_C"]


@pytest.mark.asyncio
@patch(
    "src.services.portfolio_transaction_processing_service.app.infrastructure.position_calculation_workflow.EpochFencer"
)
async def test_calculate_backdated_replay_deduplicates_triggering_transaction_if_already_persisted(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    sample_event: TransactionEvent,
):
    """
    GIVEN the triggering back-dated transaction is already present in the canonical
    transaction table
    WHEN reprocessing is triggered
    THEN the replay batch should not include the triggering transaction twice.
    """
    mock_fencer_instance = mock_fencer_class.return_value
    mock_fencer_instance.check = AsyncMock(return_value=True)
    sample_event.epoch = None
    sample_event.transaction_id = "TXN_DUP"
    sample_event.transaction_date = datetime(2025, 8, 20, 10, 0, 0)

    mock_state_repo.get_or_create_state.return_value = PositionState(
        watermark_date=date(2025, 8, 25), epoch=0
    )
    mock_state_repo.increment_epoch_and_reset_watermark.return_value = PositionState(epoch=1)
    mock_repo.get_all_transactions_for_security.return_value = [
        DBTransaction(
            transaction_id="TXN_DUP",
            portfolio_id="P1",
            security_id="S1",
            instrument_id="I1",
            transaction_date=datetime(2025, 8, 20, 10, 0, 0),
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("1"),
            gross_transaction_amount=Decimal("1"),
            trade_currency="USD",
            currency="USD",
            trade_fee=Decimal("0"),
        ),
        DBTransaction(
            transaction_id="TXN_OLDER",
            portfolio_id="P1",
            security_id="S1",
            instrument_id="I1",
            transaction_date=datetime(2025, 8, 19, 10, 0, 0),
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("1"),
            gross_transaction_amount=Decimal("1"),
            trade_currency="USD",
            currency="USD",
            trade_fee=Decimal("0"),
        ),
    ]

    await PositionCalculationWorkflow.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo
    )

    positions = mock_repo.save_positions.await_args.args[0]
    assert [position.transaction_id for position in positions] == ["TXN_OLDER", "TXN_DUP"]


def test_calculate_next_position_for_sell_uses_net_cost():
    """
    Verifies that for a SELL transaction, the cost basis is correctly reduced
    by the `net_cost` (COGS) from the event, not by a proportional amount.
    """
    # ARRANGE
    initial_state = PositionStateDTO(
        quantity=Decimal("100"), cost_basis=Decimal("1200"), cost_basis_local=Decimal("1000")
    )
    sell_event = TransactionEvent(
        transaction_id="SELL_FIFO_01",
        transaction_type="SELL",
        quantity=Decimal("50"),
        net_cost=Decimal("-550"),
        net_cost_local=Decimal("-500"),
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime.now(),
        price=Decimal(0),
        gross_transaction_amount=Decimal(0),
        trade_currency="USD",
        currency="USD",
    )

    # ACT
    new_state = PositionCalculationWorkflow.calculate_next_position(initial_state, sell_event)

    # ASSERT
    assert new_state.quantity == Decimal("50")
    assert new_state.cost_basis == Decimal("650")
    assert new_state.cost_basis_local == Decimal("500")


def test_calculate_next_position_normalizes_transaction_type_before_calculation() -> None:
    initial_state = PositionStateDTO(
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("100"),
    )
    buy_event = TransactionEvent(
        transaction_id="BUY_LOWERCASE_TYPE_01",
        transaction_type=" buy ",
        quantity=Decimal("5"),
        net_cost=Decimal("55"),
        net_cost_local=Decimal("55"),
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime.now(),
        price=Decimal("11"),
        gross_transaction_amount=Decimal("55"),
        trade_currency="USD",
        currency="USD",
    )

    new_state = PositionCalculationWorkflow.calculate_next_position(initial_state, buy_event)

    assert new_state.quantity == Decimal("15")
    assert new_state.cost_basis == Decimal("155")
    assert new_state.cost_basis_local == Decimal("155")


def test_calculate_next_position_for_adjustment_uses_movement_direction():
    initial_state = PositionStateDTO(
        quantity=Decimal("1000"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
    )
    inflow_event = TransactionEvent(
        transaction_id="ADJ_IN_01",
        transaction_type="ADJUSTMENT",
        movement_direction="INFLOW",
        quantity=Decimal("0"),
        net_cost=Decimal("0"),
        net_cost_local=Decimal("0"),
        portfolio_id="P1",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_date=datetime.now(),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("50"),
        trade_currency="USD",
        currency="USD",
    )
    outflow_event = inflow_event.model_copy(
        update={
            "transaction_id": "ADJ_OUT_01",
            "movement_direction": "OUTFLOW",
            "gross_transaction_amount": Decimal("20"),
        }
    )

    mid_state = PositionCalculationWorkflow.calculate_next_position(initial_state, inflow_event)
    final_state = PositionCalculationWorkflow.calculate_next_position(mid_state, outflow_event)

    assert mid_state.quantity == Decimal("1050")
    assert mid_state.cost_basis == Decimal("1050")
    assert final_state.quantity == Decimal("1030")
    assert final_state.cost_basis == Decimal("1030")


def test_calculate_next_position_for_adjustment_normalizes_movement_direction():
    initial_state = PositionStateDTO(
        quantity=Decimal("1000"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
    )
    outflow_event = TransactionEvent(
        transaction_id="ADJ_PADDED_OUT_01",
        transaction_type="ADJUSTMENT",
        movement_direction=" outflow ",
        quantity=Decimal("0"),
        net_cost=Decimal("0"),
        net_cost_local=Decimal("0"),
        portfolio_id="P1",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_date=datetime.now(),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("20"),
        trade_currency="USD",
        currency="USD",
    )

    next_state = PositionCalculationWorkflow.calculate_next_position(initial_state, outflow_event)

    assert next_state.quantity == Decimal("980")
    assert next_state.cost_basis == Decimal("980")
    assert next_state.cost_basis_local == Decimal("980")


def test_calculate_next_position_for_fx_cash_settlement_buy_updates_cash_position() -> None:
    initial_state = PositionStateDTO(
        quantity=Decimal("1000"),
        cost_basis=Decimal("1000"),
        cost_basis_local=Decimal("1000"),
    )
    event = TransactionEvent(
        transaction_id="FX-CASH-BUY-01",
        transaction_type="FX_FORWARD",
        component_type="FX_CASH_SETTLEMENT_BUY",
        quantity=Decimal("0"),
        portfolio_id="P1",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_date=datetime.now(),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("1095"),
        trade_currency="USD",
        currency="USD",
    )

    next_state = PositionCalculationWorkflow.calculate_next_position(initial_state, event)

    assert next_state.quantity == Decimal("2095")
    assert next_state.cost_basis == Decimal("2095")
    assert next_state.cost_basis_local == Decimal("2095")


def test_calculate_next_position_for_fx_contract_lifecycle_tracks_open_state() -> None:
    initial_state = PositionStateDTO(
        quantity=Decimal("0"),
        cost_basis=Decimal("0"),
        cost_basis_local=Decimal("0"),
    )
    open_event = TransactionEvent(
        transaction_id="FX-OPEN-01",
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        quantity=Decimal("0"),
        portfolio_id="P1",
        instrument_id="FXC-2026-0001",
        security_id="FXC-2026-0001",
        transaction_date=datetime.now(),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        currency="USD",
    )
    close_event = open_event.model_copy(
        update={
            "transaction_id": "FX-CLOSE-01",
            "component_type": "FX_CONTRACT_CLOSE",
        }
    )

    open_state = PositionCalculationWorkflow.calculate_next_position(initial_state, open_event)
    closed_state = PositionCalculationWorkflow.calculate_next_position(open_state, close_event)

    assert open_state.quantity == Decimal("1")
    assert open_state.cost_basis == Decimal("0")
    assert closed_state.quantity == Decimal("0")
    assert closed_state.cost_basis == Decimal("0")


@pytest.mark.parametrize(
    ("transaction_type", "gross_amount", "expected_quantity", "expected_cost"),
    [
        ("DEPOSIT", Decimal("25"), Decimal("125"), Decimal("125")),
        ("WITHDRAWAL", Decimal("30"), Decimal("70"), Decimal("70")),
        ("FEE", Decimal("5"), Decimal("95"), Decimal("95")),
        ("TAX", Decimal("7"), Decimal("93"), Decimal("93")),
    ],
)
def test_calculate_next_position_for_cash_portfolio_flows_updates_cash_balance(
    transaction_type: str,
    gross_amount: Decimal,
    expected_quantity: Decimal,
    expected_cost: Decimal,
) -> None:
    initial_state = PositionStateDTO(
        quantity=Decimal("100"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("100"),
    )
    event = TransactionEvent(
        transaction_id=f"{transaction_type}_CASH_01",
        transaction_type=transaction_type,
        quantity=Decimal("0"),
        portfolio_id="P1",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_date=datetime.now(),
        price=Decimal("1"),
        gross_transaction_amount=gross_amount,
        trade_currency="USD",
        currency="USD",
    )

    next_state = PositionCalculationWorkflow.calculate_next_position(initial_state, event)

    assert next_state.quantity == expected_quantity
    assert next_state.cost_basis == expected_cost
    assert next_state.cost_basis_local == expected_cost


@pytest.mark.parametrize(
    ("transaction_type", "gross_amount", "expected_quantity", "expected_cost"),
    [
        ("DEPOSIT", Decimal("25"), Decimal("125"), Decimal("125")),
        ("WITHDRAWAL", Decimal("30"), Decimal("70"), Decimal("70")),
        ("FEE", Decimal("5"), Decimal("95"), Decimal("95")),
        ("TAX", Decimal("7"), Decimal("93"), Decimal("93")),
    ],
)
def test_cash_portfolio_flows_treat_zero_booked_cost_as_amount_fallback(
    transaction_type: str,
    gross_amount: Decimal,
    expected_quantity: Decimal,
    expected_cost: Decimal,
) -> None:
    initial_state = PositionStateDTO(
        quantity=Decimal("100"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("100"),
    )
    event = TransactionEvent(
        transaction_id=f"{transaction_type}_ZERO_NET_COST_01",
        transaction_type=transaction_type,
        quantity=Decimal("0"),
        portfolio_id="P1",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_date=datetime.now(),
        price=Decimal("1"),
        gross_transaction_amount=gross_amount,
        trade_currency="USD",
        currency="USD",
        net_cost=Decimal("0"),
        net_cost_local=Decimal("0"),
    )

    next_state = PositionCalculationWorkflow.calculate_next_position(initial_state, event)

    assert next_state.quantity == expected_quantity
    assert next_state.cost_basis == expected_cost
    assert next_state.cost_basis_local == expected_cost


def test_cash_fee_uses_fee_inclusive_booked_local_cost_for_quantity_delta() -> None:
    initial_state = PositionStateDTO(
        quantity=Decimal("100"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("100"),
    )
    event = TransactionEvent(
        transaction_id="FEE_CASH_BOOKED_COMPONENTS_01",
        transaction_type="FEE",
        quantity=Decimal("0"),
        portfolio_id="P1",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_date=datetime.now(),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("25"),
        trade_currency="USD",
        currency="USD",
        net_cost=Decimal("-26.75"),
        net_cost_local=Decimal("-26.75"),
    )

    next_state = PositionCalculationWorkflow.calculate_next_position(initial_state, event)

    assert next_state.quantity == Decimal("73.25")
    assert next_state.cost_basis == Decimal("73.25")
    assert next_state.cost_basis_local == Decimal("73.25")


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "expected_quantity", "expected_cost"),
    [
        ("DEPOSIT", Decimal("25"), Decimal("125"), Decimal("125")),
        ("WITHDRAWAL", Decimal("30"), Decimal("70"), Decimal("70")),
        ("FEE", Decimal("5"), Decimal("95"), Decimal("95")),
        ("TAX", Decimal("7"), Decimal("93"), Decimal("93")),
    ],
)
def test_cash_portfolio_flows_fall_back_to_quantity_when_gross_amount_is_zero(
    transaction_type: str,
    quantity: Decimal,
    expected_quantity: Decimal,
    expected_cost: Decimal,
) -> None:
    initial_state = PositionStateDTO(
        quantity=Decimal("100"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("100"),
    )
    event = TransactionEvent(
        transaction_id=f"{transaction_type}_QUANTITY_AMOUNT_01",
        transaction_type=transaction_type,
        quantity=quantity,
        portfolio_id="P1",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_date=datetime.now(),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        currency="USD",
    )

    next_state = PositionCalculationWorkflow.calculate_next_position(initial_state, event)

    assert next_state.quantity == expected_quantity
    assert next_state.cost_basis == expected_cost
    assert next_state.cost_basis_local == expected_cost


def test_cash_position_deltas_normalize_booked_costs_once() -> None:
    net_cost = _StringCountedAmount("30")
    net_cost_local = _StringCountedAmount("30")
    transaction = SimpleNamespace(
        gross_transaction_amount="0",
        quantity="25",
        net_cost=net_cost,
        net_cost_local=net_cost_local,
        movement_direction=None,
    )

    quantity_delta, cost_basis_delta, cost_basis_local_delta = cash_position_deltas(
        transaction, "DEPOSIT"
    )

    assert quantity_delta == Decimal("25")
    assert cost_basis_delta == Decimal("30")
    assert cost_basis_local_delta == Decimal("30")
    assert net_cost.string_call_count == 1
    assert net_cost_local.string_call_count == 1


def test_foreign_currency_cash_flow_uses_booked_base_and_local_costs() -> None:
    initial_state = PositionStateDTO(
        quantity=Decimal("335000"),
        cost_basis=Decimal("359349.475"),
        cost_basis_local=Decimal("335000"),
    )
    event = TransactionEvent(
        transaction_id="TXN-CASH-BUY-SAP-001",
        transaction_type="SELL",
        quantity=Decimal("82552"),
        portfolio_id="P1",
        instrument_id="EUR-CASH",
        security_id="CASH_EUR_BOOK_OPERATING",
        transaction_date=datetime.now(),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("82552"),
        trade_currency="EUR",
        currency="EUR",
        net_cost=Decimal("-88689.906304"),
        net_cost_local=Decimal("-82552"),
    )

    next_state = PositionCalculationWorkflow.calculate_next_position(initial_state, event)

    assert next_state.quantity == Decimal("252448")
    assert next_state.cost_basis == Decimal("270659.568696")
    assert next_state.cost_basis_local == Decimal("252448")


def test_foreign_currency_cash_deposit_preserves_base_fx_basis() -> None:
    initial_state = PositionStateDTO()
    event = TransactionEvent(
        transaction_id="TXN-DEP-EUR-001",
        transaction_type="DEPOSIT",
        quantity=Decimal("335000"),
        portfolio_id="P1",
        instrument_id="EUR-CASH",
        security_id="CASH_EUR_BOOK_OPERATING",
        transaction_date=datetime.now(),
        price=Decimal("1"),
        gross_transaction_amount=Decimal("335000"),
        trade_currency="EUR",
        currency="EUR",
        net_cost=Decimal("359349.475"),
        net_cost_local=Decimal("335000"),
    )

    next_state = PositionCalculationWorkflow.calculate_next_position(initial_state, event)

    assert next_state.quantity == Decimal("335000")
    assert next_state.cost_basis == Decimal("359349.475")
    assert next_state.cost_basis_local == Decimal("335000")


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "gross_amount", "expected_quantity", "expected_cost"),
    [
        ("MERGER_OUT", Decimal("10"), Decimal("1000"), Decimal("90"), Decimal("9000")),
        ("EXCHANGE_OUT", Decimal("10"), Decimal("1000"), Decimal("90"), Decimal("9000")),
        ("REPLACEMENT_OUT", Decimal("10"), Decimal("1000"), Decimal("90"), Decimal("9000")),
        ("SPIN_IN", Decimal("10"), Decimal("1000"), Decimal("110"), Decimal("11000")),
        ("DEMERGER_IN", Decimal("10"), Decimal("1000"), Decimal("110"), Decimal("11000")),
        ("MERGER_IN", Decimal("10"), Decimal("1000"), Decimal("110"), Decimal("11000")),
        ("EXCHANGE_IN", Decimal("10"), Decimal("1000"), Decimal("110"), Decimal("11000")),
        ("REPLACEMENT_IN", Decimal("10"), Decimal("1000"), Decimal("110"), Decimal("11000")),
        ("RIGHTS_ALLOCATE", Decimal("5"), Decimal("0"), Decimal("105"), Decimal("10000")),
        ("RIGHTS_SHARE_DELIVERY", Decimal("2"), Decimal("0"), Decimal("102"), Decimal("10000")),
        ("RIGHTS_SUBSCRIBE", Decimal("3"), Decimal("0"), Decimal("97"), Decimal("10000")),
        ("RIGHTS_SELL", Decimal("4"), Decimal("0"), Decimal("96"), Decimal("10000")),
    ],
)
def test_calculate_next_position_for_ca_transfer_types(
    transaction_type: str,
    quantity: Decimal,
    gross_amount: Decimal,
    expected_quantity: Decimal,
    expected_cost: Decimal,
) -> None:
    initial_state = PositionStateDTO(
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
    )
    event = TransactionEvent(
        transaction_id=f"{transaction_type}_01",
        transaction_type=transaction_type,
        quantity=quantity,
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime.now(),
        price=Decimal("0"),
        gross_transaction_amount=gross_amount,
        trade_currency="USD",
        currency="USD",
    )

    next_state = PositionCalculationWorkflow.calculate_next_position(initial_state, event)
    assert next_state.quantity == expected_quantity
    assert next_state.cost_basis == expected_cost
    assert next_state.cost_basis_local == expected_cost


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "expected_quantity", "expected_cost"),
    [
        ("SPLIT", Decimal("20"), Decimal("120"), Decimal("10000")),
        ("BONUS_ISSUE", Decimal("10"), Decimal("110"), Decimal("10000")),
        ("STOCK_DIVIDEND", Decimal("5"), Decimal("105"), Decimal("10000")),
        ("REVERSE_SPLIT", Decimal("15"), Decimal("85"), Decimal("10000")),
        ("CONSOLIDATION", Decimal("12"), Decimal("88"), Decimal("10000")),
    ],
)
def test_calculate_next_position_for_ca_same_instrument_restatement_types(
    transaction_type: str,
    quantity: Decimal,
    expected_quantity: Decimal,
    expected_cost: Decimal,
) -> None:
    initial_state = PositionStateDTO(
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
    )
    event = TransactionEvent(
        transaction_id=f"{transaction_type}_01",
        transaction_type=transaction_type,
        quantity=quantity,
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime.now(),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        currency="USD",
    )

    next_state = PositionCalculationWorkflow.calculate_next_position(initial_state, event)
    assert next_state.quantity == expected_quantity
    assert next_state.cost_basis == expected_cost
    assert next_state.cost_basis_local == expected_cost


def test_calculate_next_position_for_spin_off_basis_only_transfer() -> None:
    initial_state = PositionStateDTO(
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        cost_basis_local=Decimal("10000"),
    )
    event = TransactionEvent(
        transaction_id="SPIN_OFF_BASIS_ONLY_01",
        transaction_type="SPIN_OFF",
        quantity=Decimal("0"),
        portfolio_id="P1",
        instrument_id="SRC_SEC",
        security_id="SRC_SEC",
        transaction_date=datetime.now(),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("2500"),
        net_cost=Decimal("-2500"),
        net_cost_local=Decimal("-2500"),
        trade_currency="USD",
        currency="USD",
    )

    next_state = PositionCalculationWorkflow.calculate_next_position(initial_state, event)
    assert next_state.quantity == Decimal("100")
    assert next_state.cost_basis == Decimal("7500")
    assert next_state.cost_basis_local == Decimal("7500")
