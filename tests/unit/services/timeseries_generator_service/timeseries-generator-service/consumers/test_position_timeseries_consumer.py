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
from portfolio_common.events import DailyPositionSnapshotPersistedEvent
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
        topic="daily_position_snapshot_persisted",
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
    mock_msg.headers.return_value = []
    return mock_msg


@pytest.fixture
def mock_dependencies():
    mock_repo = AsyncMock(spec=TimeseriesRepository)

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

    mock_repo.get_instrument.return_value = Instrument(
        security_id=mock_event.security_id, currency="USD"
    )
    mock_db_session.get.return_value = DailyPositionSnapshot(
        id=mock_event.id,
        quantity=Decimal(100),
        cost_basis=Decimal(1000),
        market_value_local=Decimal(1100),
    )
    mock_repo.get_last_snapshot_before.return_value = DailyPositionSnapshot(
        market_value_local=Decimal(1050)
    )
    mock_repo.get_all_cashflows_for_security_date.return_value = []

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
        mock_fencer_instance.check.assert_awaited_once()
        mock_repo.upsert_position_timeseries.assert_awaited_once()
        created_record = mock_repo.upsert_position_timeseries.call_args[0][0]
        assert created_record.epoch == 1


async def test_process_message_skips_stale_epoch(
    consumer: PositionTimeseriesConsumer,
    mock_kafka_message: MagicMock,
    mock_dependencies: dict,
    caplog,
):
    # ARRANGE
    mock_repo = mock_dependencies["repo"]

    # Mock the fencer to return False (discard the message)
    with patch(
        "services.timeseries_generator_service.app.consumers.position_timeseries_consumer.EpochFencer"
    ) as mock_fencer_class:
        mock_fencer_instance = AsyncMock()
        mock_fencer_instance.check.return_value = False
        mock_fencer_class.return_value = mock_fencer_instance

        # ACT
        with caplog.at_level(logging.WARNING):
            await consumer._process_message_with_retry(mock_kafka_message)

        # ASSERT
        mock_repo.get_instrument.assert_not_called()
        mock_repo.upsert_position_timeseries.assert_not_called()
        # The fencer now handles logging, so we don't need to check caplog here.
        # The key assertion is that the business logic was not executed.
