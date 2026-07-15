"""Prove the portfolio-timeseries Kafka delivery boundary."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.events import PortfolioAggregationRequiredEvent

from src.services.portfolio_aggregation_service.app.application.portfolio_timeseries import (
    MaterializePortfolioTimeseries,
    PortfolioTimeseriesMaterializationResult,
    PortfolioTimeseriesMaterializationStatus,
)
from src.services.portfolio_aggregation_service.app.consumers import (
    portfolio_aggregation_event_mapper,
)
from src.services.portfolio_aggregation_service.app.consumers.portfolio_timeseries_consumer import (
    PortfolioTimeseriesConsumer,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def use_case() -> AsyncMock:
    """Provide the application boundary consumed by the delivery adapter."""

    materializer = AsyncMock(spec=MaterializePortfolioTimeseries)
    materializer.execute.return_value = PortfolioTimeseriesMaterializationResult(
        status=PortfolioTimeseriesMaterializationStatus.COMPLETE,
        target_epoch=4,
    )
    return materializer


@pytest.fixture
def consumer(use_case: AsyncMock) -> PortfolioTimeseriesConsumer:
    """Build a consumer without database, outbox, or calculator dependencies."""

    adapter = PortfolioTimeseriesConsumer(
        bootstrap_servers="mock_server",
        topic="portfolio_day.aggregation.job.requested",
        group_id="test_group",
        dlq_topic="test.dlq",
        use_case=use_case,
    )
    adapter._send_to_dlq_async = AsyncMock()
    return adapter


@pytest.fixture
def event() -> PortfolioAggregationRequiredEvent:
    """Return one claimed portfolio aggregation event."""

    return PortfolioAggregationRequiredEvent(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        aggregation_date=date(2026, 4, 10),
    )


def _message(payload: bytes | None, *, headers: list[tuple[str, bytes]] | None = None) -> MagicMock:
    message = MagicMock()
    message.value.return_value = payload
    message.headers.return_value = headers or []
    return message


async def test_process_message_maps_header_lineage_and_delegates(
    consumer: PortfolioTimeseriesConsumer,
    use_case: AsyncMock,
    event: PortfolioAggregationRequiredEvent,
) -> None:
    message = _message(
        event.model_dump_json().encode("utf-8"),
        headers=[("correlation_id", b"corr-portfolio-001")],
    )

    await consumer.process_message(message)

    command = use_case.execute.await_args.args[0]
    assert command.portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert command.aggregation_date == date(2026, 4, 10)
    assert command.correlation_id == "corr-portfolio-001"
    consumer._send_to_dlq_async.assert_not_awaited()


async def test_process_message_accepts_recorded_application_failure(
    consumer: PortfolioTimeseriesConsumer,
    use_case: AsyncMock,
    event: PortfolioAggregationRequiredEvent,
) -> None:
    use_case.execute.return_value = PortfolioTimeseriesMaterializationResult(
        status=PortfolioTimeseriesMaterializationStatus.FAILED,
        failure_recorded=True,
    )
    message = _message(event.model_dump_json().encode("utf-8"))

    await consumer.process_message(message)

    use_case.execute.assert_awaited_once()
    consumer._send_to_dlq_async.assert_not_awaited()


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b'{"portfolio_id":"PB_SG_GLOBAL_BAL_001"}',
        None,
    ],
)
async def test_process_message_routes_invalid_payload_to_dlq(
    consumer: PortfolioTimeseriesConsumer,
    use_case: AsyncMock,
    payload: bytes | None,
) -> None:
    message = _message(payload)

    await consumer.process_message(message)

    use_case.execute.assert_not_awaited()
    consumer._send_to_dlq_async.assert_awaited_once()


async def test_process_message_routes_unrecorded_application_failure_to_dlq(
    consumer: PortfolioTimeseriesConsumer,
    use_case: AsyncMock,
    event: PortfolioAggregationRequiredEvent,
) -> None:
    failure = RuntimeError("failure status could not be persisted")
    use_case.execute.side_effect = failure
    message = _message(event.model_dump_json().encode("utf-8"))

    await consumer.process_message(message)

    consumer._send_to_dlq_async.assert_awaited_once_with(message, failure)


async def test_event_mapper_falls_back_to_source_event_correlation() -> None:
    source_event = PortfolioAggregationRequiredEvent(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        aggregation_date=date(2026, 4, 10),
        correlation_id="source-correlation",
    )

    command = portfolio_aggregation_event_mapper.map_portfolio_aggregation_event(
        source_event,
        correlation_id=None,
    )

    assert command.correlation_id == "source-correlation"
