from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.exceptions import RetryableConsumerError

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


def _message(payload: object = None) -> MagicMock:
    value = (
        {"transaction_id": " TXN-REPLAY-01 ", "correlation_id": "payload-corr"}
        if payload is None
        else payload
    )
    message = MagicMock()
    message.value.return_value = json.dumps(value).encode("utf-8")
    message.headers.return_value = [("correlation_id", b"header-corr")]
    message.topic.return_value = "transactions.reprocessing.requested"
    message.partition.return_value = 1
    message.offset.return_value = 7
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
