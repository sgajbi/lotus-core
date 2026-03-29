# tests/unit/services/timeseries_generator_service/timeseries-generator-service/consumers/test_position_timeseries_consumer.py  # noqa: E501
import logging
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
)
from portfolio_common.events import DailyPositionSnapshotPersistedEvent, ValuationDayCompletedEvent
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

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
    mock_outbox_repo = AsyncMock(spec=OutboxRepository)

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
        patch(
            "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.OutboxRepository",
            return_value=mock_outbox_repo,
        ),
    ):
        yield {"repo": mock_repo, "db_session": mock_db_session, "outbox_repo": mock_outbox_repo}


async def test_process_message_success(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
):
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    mock_repo.get_instrument.return_value = Instrument(
        security_id=mock_event.security_id, currency="USD"
    )
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

    # Mock the fencer to return True (process the message)
    with patch(
        "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        # ACT
        await consumer._process_message_with_retry(mock_kafka_message)

        # ASSERT
        mock_fencer_class.assert_not_called()
        mock_repo.upsert_position_timeseries.assert_awaited_once()
        mock_outbox_repo.create_outbox_event.assert_awaited_once()
        assert mock_outbox_repo.create_outbox_event.call_args.kwargs["correlation_id"] == (
            "ts-corr-id"
        )
        created_record = mock_repo.upsert_position_timeseries.call_args[0][0]
        assert created_record.epoch == 1


async def test_process_message_skips_stale_epoch(
    consumer: PositionTimeseriesConsumer,
    mock_dependencies: dict,
    caplog,
):
    # ARRANGE
    mock_repo = mock_dependencies["repo"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    valuation_event = ValuationDayCompletedEvent(
        daily_position_snapshot_id=123,
        portfolio_id="PORT_TS_POS_01",
        security_id="SEC_TS_POS_01",
        valuation_date=date(2025, 8, 12),
        epoch=1,
    )
    msg = MagicMock()
    msg.value.return_value = valuation_event.model_dump_json().encode("utf-8")
    msg.headers.return_value = []

    # Mock the fencer to return False (discard the message)
    with patch(
        "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = False
        mock_fencer_class.return_value = mock_fencer_instance

        # ACT
        with caplog.at_level(logging.WARNING):
            await consumer._process_message_with_retry(msg)

        # ASSERT
        mock_repo.get_instrument.assert_not_called()
        mock_repo.upsert_position_timeseries.assert_not_called()
        mock_outbox_repo.create_outbox_event.assert_not_called()
        # The fencer now handles logging, so we don't need to check caplog here.
        # The key assertion is that the business logic was not executed.


async def test_process_message_bypasses_epoch_fencing_for_snapshot_backfill(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    mock_repo.get_instrument.return_value = Instrument(
        security_id=mock_event.security_id, currency="USD"
    )
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

    with patch(
        "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = False
        mock_fencer_class.return_value = mock_fencer_instance

        await consumer._process_message_with_retry(mock_kafka_message)

    mock_fencer_class.assert_not_called()
    mock_repo.upsert_position_timeseries.assert_awaited_once()
    mock_outbox_repo.create_outbox_event.assert_awaited_once()


async def test_process_message_accepts_valuation_completed_event(
    consumer: PositionTimeseriesConsumer,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]
    valuation_event = ValuationDayCompletedEvent(
        daily_position_snapshot_id=123,
        portfolio_id="PORT_TS_POS_01",
        security_id="SEC_TS_POS_01",
        valuation_date=date(2025, 8, 12),
        epoch=1,
    )
    msg = MagicMock()
    msg.value.return_value = valuation_event.model_dump_json().encode("utf-8")
    msg.headers.return_value = []

    mock_repo.get_instrument.return_value = Instrument(
        security_id=valuation_event.security_id, currency="USD"
    )
    mock_db_session.get.return_value = DailyPositionSnapshot(
        id=valuation_event.daily_position_snapshot_id,
        portfolio_id=valuation_event.portfolio_id,
        security_id=valuation_event.security_id,
        date=valuation_event.valuation_date,
        quantity=Decimal(100),
        cost_basis_local=Decimal(1000),
        market_value_local=Decimal(1100),
    )
    mock_repo.get_last_snapshot_before.return_value = DailyPositionSnapshot(
        market_value_local=Decimal(1050)
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = []
    mock_repo.get_position_timeseries.return_value = None

    with patch(
        "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        await consumer._process_message_with_retry(msg)

    mock_repo.upsert_position_timeseries.assert_awaited_once()
    mock_outbox_repo.create_outbox_event.assert_awaited_once()


async def test_process_message_uses_header_correlation_on_direct_path(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    mock_repo.get_instrument.return_value = Instrument(
        security_id=mock_event.security_id, currency="USD"
    )
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
        with patch(
            "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.EpochFencer"
        ) as mock_fencer_class:
            mock_fencer_instance = AsyncMock()
            mock_fencer_instance.check.return_value = True
            mock_fencer_class.return_value = mock_fencer_instance

            await consumer._process_message_with_retry(mock_kafka_message)
    finally:
        correlation_id_var.reset(token)

    assert mock_outbox_repo.create_outbox_event.call_args.kwargs["correlation_id"] == (
        "ts-corr-id"
    )


async def test_process_message_skips_downstream_fanout_for_identical_timeseries(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_event: DailyPositionSnapshotPersistedEvent,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_db_session = mock_dependencies["db_session"]
    mock_outbox_repo = mock_dependencies["outbox_repo"]

    mock_repo.get_instrument.return_value = Instrument(
        security_id=mock_event.security_id, currency="USD"
    )
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

    with patch(
        "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = True
        mock_fencer_class.return_value = mock_fencer_instance

        await consumer._process_message_with_retry(mock_kafka_message)

    mock_repo.upsert_position_timeseries.assert_not_awaited()
    mock_outbox_repo.create_outbox_event.assert_not_awaited()


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
    compiled_stmt = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "DO UPDATE SET status" in compiled_stmt
    assert "correlation_id" in compiled_stmt
    assert "WHERE NOT (" not in compiled_stmt
