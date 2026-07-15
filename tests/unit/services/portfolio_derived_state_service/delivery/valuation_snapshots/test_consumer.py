"""Prove the position-timeseries Kafka delivery boundary."""

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.events import DailyPositionSnapshotPersistedEvent
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.services.portfolio_derived_state_service.app.application.position_timeseries import (
    MaterializePositionTimeseries,
    PositionTimeseriesMaterializationResult,
)
from src.services.portfolio_derived_state_service.app.delivery.valuation_snapshots.consumer import (
    PositionTimeseriesConsumer,
)
from src.services.portfolio_derived_state_service.app.delivery.valuation_snapshots.mapper import (
    map_position_snapshot_event,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def use_case() -> AsyncMock:
    """Provide the application boundary consumed by the delivery adapter."""

    materializer = AsyncMock(spec=MaterializePositionTimeseries)
    materializer.execute.return_value = PositionTimeseriesMaterializationResult(
        snapshot_found=True,
        current_day_changed=True,
        dependent_days_changed=0,
    )
    return materializer


@pytest.fixture
def consumer(use_case: AsyncMock) -> PositionTimeseriesConsumer:
    """Build a consumer without persistence or broker dependencies."""

    adapter = PositionTimeseriesConsumer(
        bootstrap_servers="mock_server",
        topic="valuation.snapshot.persisted",
        group_id="test_group",
        use_case=use_case,
    )
    adapter._send_to_dlq_async = AsyncMock()
    return adapter


@pytest.fixture
def event() -> DailyPositionSnapshotPersistedEvent:
    """Return one authoritative valuation snapshot event."""

    return DailyPositionSnapshotPersistedEvent(
        id=123,
        portfolio_id="PORT_TS_POS_01",
        security_id="SEC_TS_POS_01",
        date=date(2025, 8, 12),
        epoch=1,
    )


def _message(payload: bytes | None, *, headers: list[tuple[str, bytes]] | None = None) -> MagicMock:
    message = MagicMock()
    message.value.return_value = payload
    message.headers.return_value = headers or []
    return message


async def test_process_message_maps_header_lineage_and_delegates(
    consumer: PositionTimeseriesConsumer,
    use_case: AsyncMock,
    event: DailyPositionSnapshotPersistedEvent,
) -> None:
    message = _message(
        event.model_dump_json().encode("utf-8"),
        headers=[("correlation_id", b"ts-corr-id")],
    )

    await consumer._process_message_with_retry(message)

    command = use_case.execute.await_args.args[0]
    assert command.snapshot_id == 123
    assert command.portfolio_id == "PORT_TS_POS_01"
    assert command.security_id == "SEC_TS_POS_01"
    assert command.valuation_date == date(2025, 8, 12)
    assert command.epoch == 1
    assert command.correlation_id == "ts-corr-id"
    consumer._send_to_dlq_async.assert_not_awaited()


async def test_process_message_rejects_unsupported_event_shape(
    consumer: PositionTimeseriesConsumer,
    use_case: AsyncMock,
) -> None:
    message = _message(
        b'{"daily_position_snapshot_id":123,"portfolio_id":"PORT_TS_POS_01",'
        b'"security_id":"SEC_TS_POS_01","valuation_date":"2025-08-12","epoch":1}'
    )

    with pytest.raises(ValidationError):
        await consumer._process_message_with_retry(message)

    use_case.execute.assert_not_awaited()
    consumer._send_to_dlq_async.assert_not_awaited()


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [(b"not-json", json.JSONDecodeError), (None, ValueError)],
)
async def test_process_message_rejects_unreadable_payload(
    consumer: PositionTimeseriesConsumer,
    use_case: AsyncMock,
    payload: bytes | None,
    expected_error: type[Exception],
) -> None:
    message = _message(payload)

    with pytest.raises(expected_error):
        await consumer._process_message_with_retry(message)

    use_case.execute.assert_not_awaited()
    consumer._send_to_dlq_async.assert_not_awaited()


async def test_process_message_surfaces_application_failure(
    consumer: PositionTimeseriesConsumer,
    use_case: AsyncMock,
    event: DailyPositionSnapshotPersistedEvent,
) -> None:
    failure = RuntimeError("materialization failed")
    use_case.execute.side_effect = failure
    message = _message(event.model_dump_json().encode("utf-8"))

    with pytest.raises(RuntimeError, match="materialization failed"):
        await consumer._process_message_with_retry(message)

    consumer._send_to_dlq_async.assert_not_awaited()


async def test_process_message_rethrows_integrity_race_for_retry(
    consumer: PositionTimeseriesConsumer,
    use_case: AsyncMock,
    event: DailyPositionSnapshotPersistedEvent,
) -> None:
    failure = IntegrityError("insert", {}, Exception("concurrent writer"))
    use_case.execute.side_effect = failure
    message = _message(event.model_dump_json().encode("utf-8"))

    with pytest.raises(IntegrityError):
        await consumer._process_message_with_retry(message)

    consumer._send_to_dlq_async.assert_not_awaited()


async def test_event_mapper_falls_back_to_source_event_correlation() -> None:
    source_event = DailyPositionSnapshotPersistedEvent(
        id=124,
        portfolio_id="PORT_TS_POS_01",
        security_id="SEC_TS_POS_01",
        date=date(2025, 8, 13),
        epoch=2,
        correlation_id="source-correlation",
    )

    command = map_position_snapshot_event(source_event, correlation_id=None)

    assert command.correlation_id == "source-correlation"
