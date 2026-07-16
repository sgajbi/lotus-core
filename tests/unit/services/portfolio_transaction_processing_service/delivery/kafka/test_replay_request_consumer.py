"""Tests for booked-transaction replay request Kafka delivery."""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile

from src.services.portfolio_transaction_processing_service.app.application import (
    BookedTransactionReplayDependencyUnavailable,
    BookedTransactionReplayInvariantViolation,
    BookedTransactionReplayStatus,
    ReplayBookedTransactionResult,
)
from src.services.portfolio_transaction_processing_service.app.delivery.kafka import (
    BookedTransactionReplayRequestConsumer,
    BookedTransactionReplayRequestPayloadError,
)

pytestmark = pytest.mark.asyncio


def _message(
    payload: object = None,
    *,
    key: str = "PB-REPLAY-01",
    partition: int = 1,
    offset: int = 7,
) -> MagicMock:
    value = (
        {"transaction_id": " TXN-REPLAY-01 ", "correlation_id": "payload-corr"}
        if payload is None
        else payload
    )
    message = MagicMock()
    message.error.return_value = None
    message.value.return_value = json.dumps(value).encode("utf-8")
    message.key.return_value = key.encode("utf-8")
    message.headers.return_value = [("correlation_id", b"header-corr")]
    message.topic.return_value = "transactions.reprocessing.requested"
    message.partition.return_value = partition
    message.offset.return_value = offset
    return message


def _consumer(use_case: AsyncMock) -> BookedTransactionReplayRequestConsumer:
    return BookedTransactionReplayRequestConsumer(
        bootstrap_servers="mock_server",
        topic="transactions.reprocessing.requested",
        group_id="portfolio_transaction_replay_request_group",
        use_case=use_case,
    )


async def test_consumer_maps_request_and_prefers_header_correlation() -> None:
    use_case = AsyncMock()
    use_case.execute.return_value = ReplayBookedTransactionResult(
        transaction_id="TXN-REPLAY-01",
        status=BookedTransactionReplayStatus.REPLAYED,
    )

    await _consumer(use_case).process_message(_message())

    command = use_case.execute.await_args.args[0]
    assert command.transaction_id == "TXN-REPLAY-01"
    assert command.correlation_id == "header-corr"
    use_case.execute.assert_awaited_once()


async def test_consumer_accepts_enriched_portfolio_ordering_identity() -> None:
    use_case = AsyncMock()
    use_case.execute.return_value = ReplayBookedTransactionResult(
        transaction_id="TXN-REPLAY-01",
        status=BookedTransactionReplayStatus.REPLAYED,
    )

    await _consumer(use_case).process_message(
        _message(
            {
                "transaction_id": "TXN-REPLAY-01",
                "portfolio_id": "PB-REPLAY-01",
            },
            key="PB-REPLAY-01",
        )
    )

    use_case.execute.assert_awaited_once()


async def test_consumer_rejects_portfolio_key_payload_mismatch() -> None:
    use_case = AsyncMock()

    with pytest.raises(
        BookedTransactionReplayRequestPayloadError,
        match="portfolio_id must match the Kafka key",
    ):
        await _consumer(use_case).process_message(
            _message(
                {
                    "transaction_id": "TXN-REPLAY-01",
                    "portfolio_id": "PB-REPLAY-02",
                },
                key="PB-REPLAY-01",
            )
        )

    use_case.execute.assert_not_awaited()


async def test_consumer_uses_payload_correlation_when_header_is_absent() -> None:
    use_case = AsyncMock()
    use_case.execute.return_value = ReplayBookedTransactionResult(
        transaction_id="TXN-REPLAY-01",
        status=BookedTransactionReplayStatus.REPLAYED,
    )
    message = _message()
    message.headers.return_value = []

    await _consumer(use_case).process_message(message)

    assert use_case.execute.await_args.args[0].correlation_id == "payload-corr"


async def test_consumer_acknowledges_missing_transaction_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    use_case = AsyncMock()
    caplog.set_level(logging.WARNING)

    await _consumer(use_case).process_message(_message({"transaction_id": "  "}))

    use_case.execute.assert_not_awaited()
    assert "has no transaction_id; acknowledging" in caplog.text


async def test_consumer_acknowledges_transaction_not_found(
    caplog: pytest.LogCaptureFixture,
) -> None:
    use_case = AsyncMock()
    use_case.execute.return_value = ReplayBookedTransactionResult(
        transaction_id="TXN-REPLAY-01",
        status=BookedTransactionReplayStatus.NOT_FOUND,
    )
    caplog.set_level(logging.WARNING)

    await _consumer(use_case).process_message(_message())

    use_case.execute.assert_awaited_once()
    assert "replay source was not found; acknowledging" in caplog.text


async def test_consumer_maps_dependency_failure_to_shared_retry_policy() -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = BookedTransactionReplayDependencyUnavailable(
        "publisher unavailable"
    )

    with pytest.raises(RetryableConsumerError, match="replay dependency unavailable"):
        await _consumer(use_case).process_message(_message())


async def test_run_loop_preserves_replay_partition_order_and_reports_backlog() -> None:
    use_case = AsyncMock()
    first_message = _message(
        {"transaction_id": "TXN-REPLAY-01"},
        offset=7,
    )
    second_message = _message(
        {"transaction_id": "TXN-REPLAY-02"},
        offset=8,
    )
    polled_messages = [first_message, second_message]
    kafka_consumer = MagicMock()
    kafka_consumer.poll.side_effect = lambda _timeout: (
        polled_messages.pop(0) if polled_messages else None
    )
    first_started = asyncio.Event()
    backlog_reported = asyncio.Event()
    release_first = asyncio.Event()
    backlog_reasons: list[str] = []
    replayed_ids: list[str] = []
    consumer = BookedTransactionReplayRequestConsumer(
        bootstrap_servers="mock_server",
        topic="transactions.reprocessing.requested",
        group_id="portfolio_transaction_replay_request_group",
        use_case=use_case,
        execution_profile=KafkaConsumerExecutionProfile(
            poll_timeout_seconds=0.01,
            max_in_flight_messages=2,
        ),
    )

    async def execute(command):
        replayed_ids.append(command.transaction_id)
        if command.transaction_id == "TXN-REPLAY-01":
            first_started.set()
            await release_first.wait()
        else:
            consumer.shutdown()
        return ReplayBookedTransactionResult(
            transaction_id=command.transaction_id,
            status=BookedTransactionReplayStatus.REPLAYED,
        )

    use_case.execute.side_effect = execute

    def observe_backlog(**kwargs) -> None:
        backlog_reasons.append(kwargs["reason"])
        backlog_reported.set()

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=kafka_consumer),
        patch(
            "portfolio_common.kafka_consumer.observe_kafka_consumer_backlog_pressure",
            side_effect=observe_backlog,
        ),
        patch("portfolio_common.kafka_consumer.set_kafka_consumer_in_flight"),
    ):
        run_task = asyncio.create_task(consumer.run())
        await asyncio.wait_for(first_started.wait(), timeout=1)
        await asyncio.wait_for(backlog_reported.wait(), timeout=1)

        assert replayed_ids == ["TXN-REPLAY-01"]
        assert "ordering_key_busy" in backlog_reasons
        kafka_consumer.commit.assert_not_called()

        release_first.set()
        await asyncio.wait_for(run_task, timeout=1)

    assert replayed_ids == ["TXN-REPLAY-01", "TXN-REPLAY-02"]
    assert [item.kwargs["message"] for item in kafka_consumer.commit.call_args_list] == [
        first_message,
        second_message,
    ]
    kafka_consumer.close.assert_called_once_with()


async def test_run_loop_drains_active_replay_before_closing_kafka() -> None:
    use_case = AsyncMock()
    message = _message()
    kafka_consumer = MagicMock()
    kafka_consumer.poll.return_value = message
    replay_started = asyncio.Event()
    release_replay = asyncio.Event()
    consumer = BookedTransactionReplayRequestConsumer(
        bootstrap_servers="mock_server",
        topic="transactions.reprocessing.requested",
        group_id="portfolio_transaction_replay_request_group",
        use_case=use_case,
        execution_profile=KafkaConsumerExecutionProfile(max_in_flight_messages=1),
    )

    async def execute(command):
        replay_started.set()
        await release_replay.wait()
        return ReplayBookedTransactionResult(
            transaction_id=command.transaction_id,
            status=BookedTransactionReplayStatus.REPLAYED,
        )

    use_case.execute.side_effect = execute

    with patch("portfolio_common.kafka_consumer.Consumer", return_value=kafka_consumer):
        run_task = asyncio.create_task(consumer.run())
        await asyncio.wait_for(replay_started.wait(), timeout=1)

        consumer.shutdown()

        kafka_consumer.close.assert_not_called()
        kafka_consumer.commit.assert_not_called()

        release_replay.set()
        await asyncio.wait_for(run_task, timeout=1)

    kafka_consumer.commit.assert_called_once_with(message=message, asynchronous=False)
    kafka_consumer.close.assert_called_once_with()


async def test_consumer_propagates_replay_invariant_violation_as_terminal() -> None:
    use_case = AsyncMock()
    invariant_error = BookedTransactionReplayInvariantViolation("duplicate canonical rows")
    use_case.execute.side_effect = invariant_error

    with pytest.raises(BookedTransactionReplayInvariantViolation) as exc_info:
        await _consumer(use_case).process_message(_message())

    assert exc_info.value is invariant_error


@pytest.mark.parametrize(
    "message_value",
    [
        b"not-json",
        json.dumps(["TXN-REPLAY-01"]).encode("utf-8"),
        json.dumps({"transaction_id": ["TXN-REPLAY-01"]}).encode("utf-8"),
        json.dumps({"transaction_id": True}).encode("utf-8"),
        json.dumps(
            {"transaction_id": "TXN-REPLAY-01", "correlation_id": {"unsafe": "shape"}}
        ).encode("utf-8"),
        json.dumps({"transaction_id": "TXN-REPLAY-01", "portfolio_id": {"unsafe": "shape"}}).encode(
            "utf-8"
        ),
        None,
    ],
)
async def test_consumer_rejects_malformed_payload_before_use_case(
    message_value: bytes | None,
) -> None:
    use_case = AsyncMock()
    message = _message()
    message.value.return_value = message_value

    with pytest.raises(BookedTransactionReplayRequestPayloadError):
        await _consumer(use_case).process_message(message)

    use_case.execute.assert_not_awaited()
