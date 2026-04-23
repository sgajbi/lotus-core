# tests/unit/services/calculators/position_calculator/core/test_position_logic.py
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import PositionState
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.position_state_repository import PositionStateRepository

from src.services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from src.services.calculators.position_calculator.app.core.position_models import (
    PositionState as PositionStateDTO,
)
from src.services.calculators.position_calculator.app.repositories.position_repository import (
    PositionRepository,
)

# The module-level pytestmark is removed to apply the asyncio mark selectively.


@pytest.fixture
def mock_repo() -> AsyncMock:
    """Provides a mock PositionRepository."""
    repo = AsyncMock(spec=PositionRepository)
    repo.get_transactions_on_or_after.return_value = []
    repo.get_last_position_before.return_value = None
    repo.get_latest_completed_snapshot_date.return_value = None
    repo.get_latest_position_history_date.return_value = None
    return repo


@pytest.fixture
def mock_state_repo() -> AsyncMock:
    """Provides a mock PositionStateRepository."""
    repo = AsyncMock(spec=PositionStateRepository)
    return repo


@pytest.fixture
def mock_outbox_repo() -> AsyncMock:
    """Provides a mock OutboxRepository."""
    return AsyncMock(spec=OutboxRepository)


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
@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_discards_stale_epoch_event(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
    sample_event: TransactionEvent,
):
    """
    GIVEN an event that the EpochFencer deems stale
    WHEN PositionCalculator.calculate is called
    THEN it should not perform any calculations or repository writes.
    """
    # ARRANGE
    mock_fencer_instance = mock_fencer_class.return_value
    mock_fencer_instance.check = AsyncMock(return_value=False)

    # ACT
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
    )

    # ASSERT
    mock_fencer_instance.check.assert_awaited_once_with(sample_event)
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.save_positions.assert_not_called()
    mock_outbox_repo.create_outbox_event.assert_not_called()


@pytest.mark.asyncio
@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_normal_flow(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
    sample_event: TransactionEvent,
):
    """
    GIVEN a transaction that is NOT backdated
    WHEN PositionCalculator.calculate runs
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
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
    )

    # ASSERT
    mock_fencer_instance.check.assert_awaited_once()
    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.save_positions.assert_awaited_once()
    mock_outbox_repo.create_outbox_event.assert_not_called()


@pytest.mark.asyncio
@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_rearms_current_epoch_when_position_history_arrives_after_valuation(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
    sample_event: TransactionEvent,
):
    """
    GIVEN a replay/current-epoch event materializes position history for a date
    already covered by valuation snapshots
    WHEN PositionCalculator persists the corrected history
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

    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
    )

    mock_state_repo.increment_epoch_and_reset_watermark.assert_not_called()
    mock_repo.save_positions.assert_awaited_once()
    mock_state_repo.update_watermarks_if_older.assert_awaited_once_with(
        keys=[("P1", "S1")],
        new_watermark_date=date(2026, 3, 10),
    )
    mock_outbox_repo.create_outbox_event.assert_not_called()


@pytest.mark.asyncio
@patch(
    "src.services.calculators.position_calculator.app.core.position_logic.REPROCESSING_EPOCH_BUMPED_TOTAL"
)
@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_re_emits_and_increments_metric_for_backdated_event(
    mock_fencer_class: MagicMock,
    mock_metric: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
    sample_event: TransactionEvent,
):
    """
    GIVEN a transaction that IS backdated
    WHEN PositionCalculator.calculate runs for an original event (epoch is None)
    THEN it should increment epoch, re-emit all historical events plus the triggering event.
    """
    # ARRANGE
    mock_fencer_instance = mock_fencer_class.return_value
    mock_fencer_instance.check = AsyncMock(return_value=True)
    sample_event.epoch = None

    current_state = PositionState(watermark_date=date(2025, 8, 25), epoch=0)
    mock_state_repo.get_or_create_state.return_value = current_state

    new_state = PositionState(epoch=1)
    mock_state_repo.increment_epoch_and_reset_watermark.return_value = new_state

    mock_repo.get_all_transactions_for_security.return_value = [
        DBTransaction(
            transaction_id="TXN_HIST_1",
            portfolio_id="P1",
            security_id="S1",
            instrument_id="I1",
            transaction_date=datetime(2025, 1, 5),
            transaction_type="BUY",
            quantity=Decimal("1"),
            price=Decimal("1"),
            gross_transaction_amount=Decimal("1"),
            trade_currency="USD",
            currency="USD",
            trade_fee=Decimal("0"),
        ),
    ]

    # ACT
    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
    )

    # ASSERT
    mock_state_repo.increment_epoch_and_reset_watermark.assert_awaited_once_with(
        "P1", "S1", 0, date(2025, 8, 19)
    )

    # Assert that the metric was instrumented correctly
    mock_metric.labels.assert_called_once_with(portfolio_id="P1", security_id="S1")
    mock_metric.labels.return_value.inc.assert_called_once()

    # Assert that it tried to publish TWO events: one historical + the triggering one
    assert mock_outbox_repo.create_outbox_event.call_count == 2

    # Check that both events were tagged with the new epoch
    first_call_args = mock_outbox_repo.create_outbox_event.call_args_list[0].kwargs
    assert first_call_args["payload"]["epoch"] == 1
    second_call_args = mock_outbox_repo.create_outbox_event.call_args_list[1].kwargs
    assert second_call_args["payload"]["epoch"] == 1


@pytest.mark.asyncio
@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_treats_existing_position_history_as_backdated_boundary(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
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

    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
    )

    mock_state_repo.increment_epoch_and_reset_watermark.assert_awaited_once_with(
        "P1", "S1", 0, date(2025, 8, 19)
    )
    assert mock_outbox_repo.create_outbox_event.await_count == 1


@pytest.mark.asyncio
@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_skips_backdated_replay_when_epoch_bump_is_stale(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
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

    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
    )

    mock_state_repo.increment_epoch_and_reset_watermark.assert_awaited_once_with(
        "P1", "S1", 0, date(2025, 8, 19)
    )
    mock_repo.get_all_transactions_for_security.assert_not_awaited()
    mock_outbox_repo.create_outbox_event.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_backdated_replay_has_deterministic_tie_break_order(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
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

    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
    )

    replay_ids = [
        call.kwargs["payload"]["transaction_id"]
        for call in mock_outbox_repo.create_outbox_event.call_args_list
    ]
    assert replay_ids == ["TXN_A", "TXN_B", "TXN_C"]


@pytest.mark.asyncio
@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_backdated_replay_deduplicates_triggering_transaction_if_already_persisted(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
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

    await PositionCalculator.calculate(
        sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
    )

    replay_ids = [
        call.kwargs["payload"]["transaction_id"]
        for call in mock_outbox_repo.create_outbox_event.call_args_list
    ]
    assert replay_ids == ["TXN_OLDER", "TXN_DUP"]


@pytest.mark.asyncio
@patch("src.services.calculators.position_calculator.app.core.position_logic.EpochFencer")
async def test_calculate_backdated_replay_preserves_outbox_correlation_id(
    mock_fencer_class: MagicMock,
    mock_repo: AsyncMock,
    mock_state_repo: AsyncMock,
    mock_outbox_repo: AsyncMock,
    sample_event: TransactionEvent,
):
    mock_fencer_instance = mock_fencer_class.return_value
    mock_fencer_instance.check = AsyncMock(return_value=True)
    sample_event.epoch = None

    mock_state_repo.get_or_create_state.return_value = PositionState(
        watermark_date=date(2025, 8, 25), epoch=0
    )
    mock_state_repo.increment_epoch_and_reset_watermark.return_value = PositionState(epoch=1)
    mock_repo.get_all_transactions_for_security.return_value = []

    token = correlation_id_var.set("corr-replay-001")
    try:
        await PositionCalculator.calculate(
            sample_event, AsyncMock(), mock_repo, mock_state_repo, mock_outbox_repo
        )
    finally:
        correlation_id_var.reset(token)

    assert mock_outbox_repo.create_outbox_event.await_count == 1
    first_call = mock_outbox_repo.create_outbox_event.call_args_list[0].kwargs
    assert first_call["correlation_id"] == "corr-replay-001"


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
    new_state = PositionCalculator.calculate_next_position(initial_state, sell_event)

    # ASSERT
    assert new_state.quantity == Decimal("50")
    assert new_state.cost_basis == Decimal("650")
    assert new_state.cost_basis_local == Decimal("500")


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

    mid_state = PositionCalculator.calculate_next_position(initial_state, inflow_event)
    final_state = PositionCalculator.calculate_next_position(mid_state, outflow_event)

    assert mid_state.quantity == Decimal("1050")
    assert mid_state.cost_basis == Decimal("1050")
    assert final_state.quantity == Decimal("1030")
    assert final_state.cost_basis == Decimal("1030")


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

    next_state = PositionCalculator.calculate_next_position(initial_state, event)

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

    open_state = PositionCalculator.calculate_next_position(initial_state, open_event)
    closed_state = PositionCalculator.calculate_next_position(open_state, close_event)

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

    next_state = PositionCalculator.calculate_next_position(initial_state, event)

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

    next_state = PositionCalculator.calculate_next_position(initial_state, event)

    assert next_state.quantity == expected_quantity
    assert next_state.cost_basis == expected_cost
    assert next_state.cost_basis_local == expected_cost


def test_calculate_next_position_for_foreign_currency_cash_flow_uses_booked_base_and_local_costs(
) -> None:
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

    next_state = PositionCalculator.calculate_next_position(initial_state, event)

    assert next_state.quantity == Decimal("252448")
    assert next_state.cost_basis == Decimal("270659.568696")
    assert next_state.cost_basis_local == Decimal("252448")


def test_calculate_next_position_for_foreign_currency_cash_deposit_preserves_base_fx_basis(
) -> None:
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

    next_state = PositionCalculator.calculate_next_position(initial_state, event)

    assert next_state.quantity == Decimal("335000")
    assert next_state.cost_basis == Decimal("359349.475")
    assert next_state.cost_basis_local == Decimal("335000")


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "gross_amount", "expected_quantity", "expected_cost"),
    [
        ("MERGER_OUT", Decimal("10"), Decimal("1000"), Decimal("90"), Decimal("9000")),
        ("EXCHANGE_OUT", Decimal("10"), Decimal("1000"), Decimal("90"), Decimal("9000")),
        ("REPLACEMENT_OUT", Decimal("10"), Decimal("1000"), Decimal("90"), Decimal("9000")),
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

    next_state = PositionCalculator.calculate_next_position(initial_state, event)
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

    next_state = PositionCalculator.calculate_next_position(initial_state, event)
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

    next_state = PositionCalculator.calculate_next_position(initial_state, event)
    assert next_state.quantity == Decimal("100")
    assert next_state.cost_basis == Decimal("7500")
    assert next_state.cost_basis_local == Decimal("7500")
