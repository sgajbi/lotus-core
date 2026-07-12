from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.exceptions import RetryableConsumerError
from sqlalchemy.exc import IntegrityError

from src.services.portfolio_transaction_processing_service.app.application import (
    ProcessTransactionResult,
    TransactionProcessingError,
    TransactionProcessingIntent,
    TransactionProcessingRejected,
    TransactionProcessingStatus,
)
from src.services.portfolio_transaction_processing_service.app.delivery.kafka import (
    TransactionProcessingConsumer,
)

pytestmark = pytest.mark.asyncio


def _message() -> MagicMock:
    event = {
        "transaction_id": "TX-001",
        "portfolio_id": "PB-001",
        "instrument_id": "INST-001",
        "security_id": "SEC-001",
        "transaction_date": datetime(2026, 4, 10, 9, 30).isoformat(),
        "transaction_type": "BUY",
        "quantity": str(Decimal("10")),
        "price": str(Decimal("25.50")),
        "gross_transaction_amount": str(Decimal("255.00")),
        "trade_currency": "SGD",
        "currency": "SGD",
        "correlation_id": "payload-corr-001",
    }
    message = MagicMock()
    message.value.return_value = json_bytes(event)
    message.topic.return_value = "transactions.persisted"
    message.partition.return_value = 3
    message.offset.return_value = 42
    message.headers.return_value = [
        ("correlation_id", b"header-corr-001"),
        ("traceparent", b"00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"),
    ]
    return message


def json_bytes(payload: dict[str, str]) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _consumer(use_case: AsyncMock) -> TransactionProcessingConsumer:
    return TransactionProcessingConsumer(
        bootstrap_servers="mock_server",
        topic="transactions.persisted",
        group_id="portfolio_transaction_processing_group",
        use_case=use_case,
    )


async def test_consumer_maps_source_lineage_and_invokes_combined_use_case_once() -> None:
    use_case = AsyncMock()
    use_case.execute.return_value = ProcessTransactionResult(
        status=TransactionProcessingStatus.PROCESSED,
        input_transaction_id="TX-001",
        cashflow_record_count=1,
        position_record_count=1,
    )
    consumer = _consumer(use_case)

    await consumer.process_message(_message())

    command = use_case.execute.await_args.args[0]
    assert command.transaction.transaction_id == "TX-001"
    assert command.metadata.event_id == "transactions.persisted-3-42"
    assert command.metadata.correlation_id == "header-corr-001"
    assert command.metadata.traceparent == (
        "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    )
    assert command.metadata.processing_intent is TransactionProcessingIntent.STANDARD
    use_case.execute.assert_awaited_once()


async def test_consumer_maps_canonical_repair_header_to_application_intent() -> None:
    use_case = AsyncMock()
    use_case.execute.return_value = ProcessTransactionResult(
        status=TransactionProcessingStatus.PROCESSED,
        input_transaction_id="TX-001",
    )
    message = _message()
    message.headers.return_value.append(("lotus-transaction-processing-intent", b"repair"))

    await _consumer(use_case).process_message(message)

    command = use_case.execute.await_args.args[0]
    assert command.metadata.processing_intent is TransactionProcessingIntent.REPAIR


async def test_consumer_rejects_unknown_processing_intent_header() -> None:
    use_case = AsyncMock()
    message = _message()
    message.headers.return_value.append(("lotus-transaction-processing-intent", b"force"))

    with pytest.raises(ValueError, match="processing intent"):
        await _consumer(use_case).process_message(message)

    use_case.execute.assert_not_awaited()


async def test_consumer_converts_retryable_application_error() -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = TransactionProcessingError(
        reason_code="cost_dependency_unavailable",
        detail={"transaction_id": "TX-001"},
        retryable=True,
    )

    with pytest.raises(RetryableConsumerError, match="cost_dependency_unavailable"):
        await _consumer(use_case).process_message(_message())


async def test_consumer_converts_database_failure_to_retryable_delivery_error() -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = IntegrityError("INSERT", {}, RuntimeError("db unavailable"))

    with pytest.raises(RetryableConsumerError, match="database dependency unavailable"):
        await _consumer(use_case).process_message(_message())


async def test_consumer_acknowledges_stale_epoch_after_atomic_rollback() -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = TransactionProcessingRejected(
        reason_code="cashflow_epoch_rejected",
        detail={"transaction_id": "TX-001"},
        retryable=False,
    )

    await _consumer(use_case).process_message(_message())

    use_case.execute.assert_awaited_once()


async def test_consumer_propagates_terminal_application_error_for_dlq_mapping() -> None:
    use_case = AsyncMock()
    terminal_error = TransactionProcessingError(
        reason_code="cashflow_rule_missing",
        detail={"transaction_id": "TX-001"},
        retryable=False,
    )
    use_case.execute.side_effect = terminal_error

    with pytest.raises(TransactionProcessingError) as exc_info:
        await _consumer(use_case).process_message(_message())

    assert exc_info.value is terminal_error


async def test_consumer_rejects_malformed_payload_before_use_case() -> None:
    use_case = AsyncMock()
    message = _message()
    message.value.return_value = b"not-json"

    with pytest.raises(ValueError):
        await _consumer(use_case).process_message(message)

    use_case.execute.assert_not_awaited()
