# tests/unit/services/timeseries_generator_service/timeseries-generator-service/consumers/test_position_timeseries_consumer.py  # noqa: E501
import logging
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
)
from portfolio_common.events import DailyPositionSnapshotPersistedEvent
from portfolio_common.logging_utils import correlation_id_var
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from services.timeseries_generator_service.app.consumers import (
    position_timeseries_consumer as consumer_module,
)
from services.timeseries_generator_service.app.consumers.position_timeseries_consumer import (
    PositionTimeseriesConsumer,
)
from src.services.timeseries_generator_service.app.repositories.timeseries_repository import (
    TimeseriesRepository,
)
from tests.unit.test_support.async_session_iter import make_single_session_getter

logger = logging.getLogger(__name__)
pytestmark = pytest.mark.asyncio


@pytest.fixture
def consumer() -> PositionTimeseriesConsumer:
    consumer = PositionTimeseriesConsumer(
        bootstrap_servers="mock_server",
        topic="valuation.snapshot.persisted",
        group_id="test_group",
    )
    consumer._send_to_dlq_async = AsyncMock()
    return consumer


@pytest.fixture
def mock_event() -> DailyPositionSnapshotPersistedEvent:
    return DailyPositionSnapshotPersistedEvent(
        id=123,
        portfolio_id="PORT_TS_POS_01",
        security_id="SEC_TS_POS_01",
        date=date(2025, 8, 12),
        epoch=1,
    )


@pytest.fixture
def mock_kafka_message(mock_event: DailyPositionSnapshotPersistedEvent) -> MagicMock:
    """Creates a mock Kafka message from the event."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = mock_event.model_dump_json().encode("utf-8")
    mock_msg.headers.return_value = [("correlation_id", b"ts-corr-id")]
    return mock_msg


@pytest.fixture
def mock_dependencies():
    mock_repo = AsyncMock(spec=TimeseriesRepository)
    mock_repo.get_next_snapshots_after.return_value = []
    mock_repo.get_position_timeseries_for_dates.return_value = {}
    mock_repo.get_cashflows_for_security_dates.return_value = {}

    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction

    get_session_gen = make_single_session_getter(mock_db_session)

    with (
        patch(
            "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.TimeseriesRepository",
            return_value=mock_repo,
        ),
    ):
        yield {"repo": mock_repo, "db_session": mock_db_session}


async def test_process_message_success(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
):
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    mock_db_session.get.return_value = DailyPositionSnapshot(
        id=mock_event.id,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.date,
        quantity=Decimal(100),
        cost_basis_local=Decimal(1000),
        market_value_local=Decimal(1100),
    )
    mock_repo.get_last_snapshot_before.return_value = DailyPositionSnapshot(
        market_value_local=Decimal(1050)
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = []
    mock_repo.get_position_timeseries.return_value = None

    await consumer._process_message_with_retry(mock_kafka_message)

    mock_repo.get_last_snapshot_before.assert_awaited_once_with(
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        a_date=mock_event.date,
        epoch=mock_event.epoch,
    )
    mock_repo.get_all_cashflows_for_security_date.assert_awaited_once_with(
        mock_event.portfolio_id,
        mock_event.security_id,
        mock_event.date,
        mock_event.epoch,
    )
    mock_repo.get_next_snapshots_after.assert_awaited_once_with(
        mock_event.portfolio_id,
        mock_event.security_id,
        mock_event.date,
        mock_event.epoch,
        501,
    )
    mock_repo.get_position_timeseries_for_dates.assert_not_awaited()
    mock_repo.get_cashflows_for_security_dates.assert_not_awaited()
    mock_repo.get_instrument.assert_not_called()
    mock_repo.upsert_position_timeseries.assert_awaited_once()
    assert mock_db_session.execute.await_count == 1
    created_record = mock_repo.upsert_position_timeseries.call_args[0][0]
    assert created_record.epoch == 1


async def test_process_message_sends_unsupported_event_shape_to_dlq(
    consumer: PositionTimeseriesConsumer,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    msg = MagicMock()
    msg.value.return_value = (
        b'{"daily_position_snapshot_id":123,"portfolio_id":"PORT_TS_POS_01",'
        b'"security_id":"SEC_TS_POS_01","valuation_date":"2025-08-12","epoch":1}'
    )
    msg.headers.return_value = []

    await consumer._process_message_with_retry(msg)

    mock_repo.get_instrument.assert_not_called()
    mock_repo.upsert_position_timeseries.assert_not_called()
    consumer._send_to_dlq_async.assert_awaited_once()


async def test_process_message_supports_snapshot_backfill_without_epoch_fencing(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    mock_db_session.get.return_value = DailyPositionSnapshot(
        id=mock_event.id,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.date,
        quantity=Decimal(100),
        cost_basis_local=Decimal(1000),
        market_value_local=Decimal(1100),
    )
    mock_repo.get_last_snapshot_before.return_value = DailyPositionSnapshot(
        market_value_local=Decimal(1050)
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = []
    mock_repo.get_position_timeseries.return_value = None

    await consumer._process_message_with_retry(mock_kafka_message)

    mock_repo.upsert_position_timeseries.assert_awaited_once()
    assert mock_db_session.execute.await_count == 1


async def test_process_message_uses_header_correlation_on_direct_path(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    mock_db_session.get.return_value = DailyPositionSnapshot(
        id=mock_event.id,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.date,
        quantity=Decimal(100),
        cost_basis_local=Decimal(1000),
        market_value_local=Decimal(1100),
    )
    mock_repo.get_last_snapshot_before.return_value = DailyPositionSnapshot(
        market_value_local=Decimal(1050)
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = []
    mock_repo.get_position_timeseries.return_value = None

    token = correlation_id_var.set("<not-set>")
    try:
        await consumer._process_message_with_retry(mock_kafka_message)
    finally:
        correlation_id_var.reset(token)

    compiled_stmt = str(
        mock_db_session.execute.call_args.args[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "'ts-corr-id'" in compiled_stmt


async def test_process_message_skips_downstream_fanout_for_identical_timeseries(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    mock_db_session.get.return_value = DailyPositionSnapshot(
        id=mock_event.id,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.date,
        quantity=Decimal(100),
        cost_basis_local=Decimal(1000),
        market_value_local=Decimal(1100),
    )
    mock_repo.get_last_snapshot_before.return_value = DailyPositionSnapshot(
        market_value_local=Decimal(1050)
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = []
    mock_repo.get_position_timeseries.return_value = MagicMock(
        bod_market_value=Decimal("1050"),
        bod_cashflow_position=Decimal("0"),
        eod_cashflow_position=Decimal("0"),
        bod_cashflow_portfolio=Decimal("0"),
        eod_cashflow_portfolio=Decimal("0"),
        eod_market_value=Decimal("1100"),
        fees=Decimal("0"),
        quantity=Decimal("100"),
        cost=Decimal("10"),
    )

    await consumer._process_message_with_retry(mock_kafka_message)

    mock_repo.upsert_position_timeseries.assert_not_awaited()
    mock_db_session.execute.assert_not_awaited()


async def test_has_material_change_only_tracks_persisted_business_fields(
    consumer: PositionTimeseriesConsumer,
):
    existing_record = MagicMock(
        bod_market_value=Decimal("1050"),
        bod_cashflow_position=Decimal("0"),
        eod_cashflow_position=Decimal("0"),
        bod_cashflow_portfolio=Decimal("0"),
        eod_cashflow_portfolio=Decimal("0"),
        eod_market_value=Decimal("1100"),
        fees=Decimal("0"),
        quantity=Decimal("100"),
        cost=Decimal("10"),
        updated_at="old-timestamp",
    )
    new_record = MagicMock(
        bod_market_value=Decimal("1050"),
        bod_cashflow_position=Decimal("0"),
        eod_cashflow_position=Decimal("0"),
        bod_cashflow_portfolio=Decimal("0"),
        eod_cashflow_portfolio=Decimal("0"),
        eod_market_value=Decimal("1100"),
        fees=Decimal("0"),
        quantity=Decimal("100"),
        cost=Decimal("10"),
        updated_at="new-timestamp",
    )

    assert consumer._has_material_change(existing_record, new_record) is False


async def test_process_message_recalculates_dependent_next_day_bod(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    current_snapshot = DailyPositionSnapshot(
        id=mock_event.id,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.date,
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1100"),
    )
    next_snapshot = DailyPositionSnapshot(
        id=124,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=date(2025, 8, 13),
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1150"),
    )

    mock_db_session.get.return_value = current_snapshot
    mock_repo.get_last_snapshot_before.return_value = DailyPositionSnapshot(
        market_value_local=Decimal("1050")
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = []
    mock_repo.get_position_timeseries.side_effect = [
        None,
    ]
    dependent_existing = MagicMock(
        bod_market_value=Decimal("0"),
        bod_cashflow_position=Decimal("0"),
        eod_cashflow_position=Decimal("0"),
        bod_cashflow_portfolio=Decimal("0"),
        eod_cashflow_portfolio=Decimal("0"),
        eod_market_value=Decimal("1150"),
        fees=Decimal("0"),
        quantity=Decimal("100"),
        cost=Decimal("10"),
    )
    mock_repo.get_position_timeseries_for_dates.return_value = {
        next_snapshot.date: dependent_existing
    }
    mock_repo.get_cashflows_for_security_dates.return_value = {next_snapshot.date: []}
    mock_repo.get_next_snapshots_after.return_value = [next_snapshot]

    await consumer._process_message_with_retry(mock_kafka_message)

    assert mock_repo.upsert_position_timeseries.await_count == 2
    assert mock_repo.get_position_timeseries.await_count == 1
    assert mock_repo.get_all_cashflows_for_security_date.await_count == 1
    propagated_record = mock_repo.upsert_position_timeseries.await_args_list[1].args[0]
    assert propagated_record.date == date(2025, 8, 13)
    assert propagated_record.bod_market_value == Decimal("1100")
    assert propagated_record.eod_market_value == Decimal("1150")
    assert mock_dependencies["db_session"].execute.await_count == 2


async def test_process_message_batches_changed_dependent_aggregation_staging(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    current_snapshot = DailyPositionSnapshot(
        id=mock_event.id,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.date,
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1100"),
    )
    next_snapshot_1 = DailyPositionSnapshot(
        id=124,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=date(2025, 8, 13),
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1150"),
    )
    next_snapshot_2 = DailyPositionSnapshot(
        id=125,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=date(2025, 8, 14),
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1200"),
    )

    mock_db_session.get.return_value = current_snapshot
    mock_repo.get_last_snapshot_before.return_value = DailyPositionSnapshot(
        market_value_local=Decimal("1050")
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = []
    mock_repo.get_position_timeseries.return_value = None
    mock_repo.get_position_timeseries_for_dates.return_value = {
        next_snapshot_1.date: MagicMock(
            bod_market_value=Decimal("0"),
            bod_cashflow_position=Decimal("0"),
            eod_cashflow_position=Decimal("0"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("0"),
            eod_market_value=Decimal("1150"),
            fees=Decimal("0"),
            quantity=Decimal("100"),
            cost=Decimal("10"),
        ),
        next_snapshot_2.date: MagicMock(
            bod_market_value=Decimal("0"),
            bod_cashflow_position=Decimal("0"),
            eod_cashflow_position=Decimal("0"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("0"),
            eod_market_value=Decimal("1200"),
            fees=Decimal("0"),
            quantity=Decimal("100"),
            cost=Decimal("10"),
        ),
    }
    mock_repo.get_cashflows_for_security_dates.return_value = {
        next_snapshot_1.date: [],
        next_snapshot_2.date: [],
    }
    mock_repo.get_next_snapshots_after.return_value = [next_snapshot_1, next_snapshot_2]

    await consumer._process_message_with_retry(mock_kafka_message)

    assert mock_repo.upsert_position_timeseries.await_count == 3
    assert mock_db_session.execute.await_count == 2
    dependent_stage_stmt = mock_db_session.execute.await_args_list[1].args[0]
    compiled_stmt = str(
        dependent_stage_stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "VALUES ('PORT_TS_POS_01', '2025-08-13'" in compiled_stmt
    assert ", ('PORT_TS_POS_01', '2025-08-14'" in compiled_stmt
    assert compiled_stmt.count("'ts-corr-id'") >= 2


async def test_process_message_does_not_precompute_absent_dependent_day(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    current_snapshot = DailyPositionSnapshot(
        id=mock_event.id,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.date,
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1100"),
    )
    next_snapshot = DailyPositionSnapshot(
        id=124,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=date(2025, 8, 13),
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1150"),
    )

    mock_db_session.get.return_value = current_snapshot
    mock_repo.get_last_snapshot_before.return_value = DailyPositionSnapshot(
        market_value_local=Decimal("1050")
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = []
    mock_repo.get_position_timeseries.return_value = None
    mock_repo.get_position_timeseries_for_dates.return_value = {}
    mock_repo.get_cashflows_for_security_dates.return_value = {next_snapshot.date: []}
    mock_repo.get_next_snapshots_after.return_value = [next_snapshot]

    await consumer._process_message_with_retry(mock_kafka_message)

    mock_repo.upsert_position_timeseries.assert_awaited_once()
    created_record = mock_repo.upsert_position_timeseries.await_args.args[0]
    assert created_record.date == mock_event.date
    assert mock_repo.get_position_timeseries.await_count == 1
    assert mock_repo.get_all_cashflows_for_security_date.await_count == 1
    assert mock_db_session.execute.await_count == 1


async def test_stage_aggregation_job_rearms_completed_job_for_late_material_input(
    consumer: PositionTimeseriesConsumer,
    mock_dependencies: dict,
):
    await consumer._stage_aggregation_job(
        mock_dependencies["db_session"],
        "PORT_TS_POS_01",
        date(2025, 8, 12),
        "corr-456",
    )

    executed_stmt = mock_dependencies["db_session"].execute.call_args[0][0]
    compiled = executed_stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    compiled_stmt = str(compiled)
    compiled_values = set(compiled.params.values())

    assert "DO UPDATE SET status" in compiled_stmt
    assert "correlation_id" in compiled_stmt
    assert "portfolio_aggregation_jobs.status !=" in compiled_stmt
    assert "REPROCESS_REQUESTED" in compiled_stmt or "REPROCESS_REQUESTED" in compiled_values
    assert "coalesce(portfolio_aggregation_jobs.correlation_id" in compiled_stmt


async def test_stage_aggregation_jobs_deduplicates_dates_before_bulk_insert(
    consumer: PositionTimeseriesConsumer,
    mock_dependencies: dict,
):
    await consumer._stage_aggregation_jobs(
        mock_dependencies["db_session"],
        "PORT_TS_POS_01",
        [date(2025, 8, 13), date(2025, 8, 13), date(2025, 8, 14)],
        "corr-789",
    )

    executed_stmt = mock_dependencies["db_session"].execute.call_args[0][0]
    compiled_stmt = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert compiled_stmt.count("'2025-08-13'") == 1
    assert compiled_stmt.count("'2025-08-14'") == 1


async def test_process_message_warns_only_when_future_chain_exceeds_cap(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    monkeypatch.setattr(consumer_module, "MAX_DEPENDENT_PROPAGATION_ROWS", 2)
    monkeypatch.setattr(consumer_module, "MAX_DEPENDENT_PROPAGATION_BATCHES_PER_MESSAGE", 2)
    monkeypatch.setattr(consumer_module, "MAX_DEPENDENT_PROPAGATION_ROWS_PER_MESSAGE", 4)
    current_snapshot = DailyPositionSnapshot(
        id=mock_event.id,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.date,
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1100"),
    )
    exact_cap_snapshots = [
        DailyPositionSnapshot(
            id=1000 + index,
            portfolio_id=mock_event.portfolio_id,
            security_id=mock_event.security_id,
            date=date(2025, 8, 13 + index),
            quantity=Decimal("100"),
            cost_basis_local=Decimal("1000"),
            market_value_local=Decimal("1150"),
        )
        for index in range(4)
    ]
    overflow_snapshot = DailyPositionSnapshot(
        id=2001,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=date(2025, 8, 17),
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1200"),
    )
    mock_db_session.get.return_value = current_snapshot
    mock_repo.get_last_snapshot_before.return_value = DailyPositionSnapshot(
        market_value_local=Decimal("1050")
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = []
    mock_repo.get_position_timeseries.return_value = None

    def _existing_row(eod_market_value: str) -> MagicMock:
        return MagicMock(
            bod_market_value=Decimal("0"),
            bod_cashflow_position=Decimal("0"),
            eod_cashflow_position=Decimal("0"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("0"),
            eod_market_value=Decimal(eod_market_value),
            fees=Decimal("0"),
            quantity=Decimal("100"),
            cost=Decimal("10"),
        )

    caplog.set_level(logging.WARNING)
    mock_repo.get_position_timeseries_for_dates.side_effect = [
        {
            exact_cap_snapshots[0].date: _existing_row("1150"),
            exact_cap_snapshots[1].date: _existing_row("1150"),
        },
        {
            exact_cap_snapshots[2].date: _existing_row("1150"),
            exact_cap_snapshots[3].date: _existing_row("1150"),
        },
    ]
    mock_repo.get_cashflows_for_security_dates.side_effect = [
        {exact_cap_snapshots[0].date: [], exact_cap_snapshots[1].date: []},
        {exact_cap_snapshots[2].date: [], exact_cap_snapshots[3].date: []},
    ]
    mock_repo.get_next_snapshots_after.side_effect = [
        exact_cap_snapshots[:3],
        exact_cap_snapshots[2:],
    ]
    await consumer._process_message_with_retry(mock_kafka_message)
    assert "Stopped dependent position-timeseries propagation after 4 rows" not in caplog.text

    caplog.clear()
    mock_repo.get_position_timeseries_for_dates.side_effect = [
        {
            exact_cap_snapshots[0].date: _existing_row("1150"),
            exact_cap_snapshots[1].date: _existing_row("1150"),
        },
        {
            exact_cap_snapshots[2].date: _existing_row("1150"),
            exact_cap_snapshots[3].date: _existing_row("1150"),
        },
    ]
    mock_repo.get_cashflows_for_security_dates.side_effect = [
        {exact_cap_snapshots[0].date: [], exact_cap_snapshots[1].date: []},
        {exact_cap_snapshots[2].date: [], exact_cap_snapshots[3].date: []},
    ]
    mock_repo.get_next_snapshots_after.side_effect = [
        exact_cap_snapshots[:3],
        exact_cap_snapshots[2:] + [overflow_snapshot],
    ]
    await consumer._process_message_with_retry(mock_kafka_message)
    assert "Stopped dependent position-timeseries propagation after 4 rows" in caplog.text


async def test_process_message_propagates_dependent_timeseries_across_bounded_batches(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    monkeypatch.setattr(consumer_module, "MAX_DEPENDENT_PROPAGATION_ROWS", 2)
    monkeypatch.setattr(consumer_module, "MAX_DEPENDENT_PROPAGATION_BATCHES_PER_MESSAGE", 2)
    monkeypatch.setattr(consumer_module, "MAX_DEPENDENT_PROPAGATION_ROWS_PER_MESSAGE", 4)

    current_snapshot = DailyPositionSnapshot(
        id=mock_event.id,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=mock_event.date,
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1100"),
    )
    next_snapshot_1 = DailyPositionSnapshot(
        id=124,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=date(2025, 8, 13),
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1150"),
    )
    next_snapshot_2 = DailyPositionSnapshot(
        id=125,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=date(2025, 8, 14),
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1200"),
    )
    next_snapshot_3 = DailyPositionSnapshot(
        id=126,
        portfolio_id=mock_event.portfolio_id,
        security_id=mock_event.security_id,
        date=date(2025, 8, 15),
        quantity=Decimal("100"),
        cost_basis_local=Decimal("1000"),
        market_value_local=Decimal("1250"),
    )

    def _existing_row(eod_market_value: str) -> MagicMock:
        return MagicMock(
            bod_market_value=Decimal("0"),
            bod_cashflow_position=Decimal("0"),
            eod_cashflow_position=Decimal("0"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("0"),
            eod_market_value=Decimal(eod_market_value),
            fees=Decimal("0"),
            quantity=Decimal("100"),
            cost=Decimal("10"),
        )

    mock_db_session.get.return_value = current_snapshot
    mock_repo.get_last_snapshot_before.return_value = DailyPositionSnapshot(
        market_value_local=Decimal("1050")
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = []
    mock_repo.get_position_timeseries.return_value = None
    mock_repo.get_next_snapshots_after.side_effect = [
        [next_snapshot_1, next_snapshot_2, next_snapshot_3],
        [next_snapshot_3],
    ]
    mock_repo.get_position_timeseries_for_dates.side_effect = [
        {
            next_snapshot_1.date: _existing_row("1150"),
            next_snapshot_2.date: _existing_row("1200"),
        },
        {next_snapshot_3.date: _existing_row("1250")},
    ]
    mock_repo.get_cashflows_for_security_dates.side_effect = [
        {next_snapshot_1.date: [], next_snapshot_2.date: []},
        {next_snapshot_3.date: []},
    ]

    await consumer._process_message_with_retry(mock_kafka_message)

    assert mock_repo.get_next_snapshots_after.await_count == 2
    assert mock_repo.get_next_snapshots_after.await_args_list[0].args == (
        mock_event.portfolio_id,
        mock_event.security_id,
        mock_event.date,
        mock_event.epoch,
        3,
    )
    assert mock_repo.get_next_snapshots_after.await_args_list[1].args == (
        mock_event.portfolio_id,
        mock_event.security_id,
        next_snapshot_2.date,
        mock_event.epoch,
        3,
    )
    assert mock_repo.upsert_position_timeseries.await_count == 4
    assert mock_db_session.execute.await_count == 2
    dependent_stage_stmt = mock_db_session.execute.await_args_list[1].args[0]
    compiled_stmt = str(
        dependent_stage_stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "VALUES ('PORT_TS_POS_01', '2025-08-13'" in compiled_stmt
    assert ", ('PORT_TS_POS_01', '2025-08-14'" in compiled_stmt
    assert ", ('PORT_TS_POS_01', '2025-08-15'" in compiled_stmt
