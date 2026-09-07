"""Tests for canonical booked-transaction Kafka delivery."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.exceptions import RetryableConsumerError
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile
from sqlalchemy.exc import DBAPIError, IntegrityError

from src.services.portfolio_transaction_processing_service.app.application import (
    CorporateActionArrivalDisposition,
    CorporateActionArrivalResult,
    ProcessTransactionResult,
    TransactionProcessingError,
    TransactionProcessingIntent,
    TransactionProcessingRejected,
    TransactionProcessingStatus,
    transaction_tenant_authority,
)
from src.services.portfolio_transaction_processing_service.app.delivery.kafka import (
    TransactionProcessingConsumer,
)

pytestmark = pytest.mark.asyncio


def _message() -> MagicMock:
    event = {
        "transaction_id": "TX-001",
        "portfolio_id": "PB-001",
        "tenant_id": "tenant-test",
        "instrument_id": "INST-001",
        "security_id": "SEC-001",
        "transaction_date": datetime(2026, 4, 10, 9, 30, tzinfo=UTC).isoformat(),
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


def _ordinary_arrival() -> AsyncMock:
    route = AsyncMock()
    route.execute.return_value = CorporateActionArrivalResult(
        CorporateActionArrivalDisposition.ORDINARY
    )
    return route


def _consumer(
    use_case: AsyncMock,
    *,
    route_corporate_action_child: AsyncMock | None = None,
    tenant_authority: AsyncMock | None = None,
) -> TransactionProcessingConsumer:
    authority = tenant_authority or AsyncMock()
    authority.resolve.return_value = "tenant-test"
    return TransactionProcessingConsumer(
        bootstrap_servers="mock_server",
        topic="transactions.persisted",
        group_id="portfolio_transaction_processing_group",
        use_case=use_case,
        route_corporate_action_child=route_corporate_action_child or _ordinary_arrival(),
        tenant_authority=authority,
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
    assert command.transaction.tenant_id == "tenant-test"
    assert command.metadata.event_id == "transactions.persisted-3-42"
    assert command.metadata.correlation_id == "header-corr-001"
    assert command.metadata.traceparent == (
        "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    )
    assert command.metadata.processing_intent is TransactionProcessingIntent.STANDARD
    use_case.execute.assert_awaited_once()


async def test_consumer_resolves_legacy_v1_event_tenant_from_portfolio_authority() -> None:
    use_case = AsyncMock()
    use_case.execute.return_value = ProcessTransactionResult(
        status=TransactionProcessingStatus.PROCESSED,
        input_transaction_id="TX-001",
    )
    authority = AsyncMock()
    authority.resolve.return_value = "tenant-test"
    message = _message()
    payload = json.loads(message.value.return_value.decode("utf-8"))
    payload.pop("tenant_id")
    message.value.return_value = json_bytes(payload)

    await _consumer(use_case, tenant_authority=authority).process_message(message)

    authority.resolve.assert_awaited_once_with(
        portfolio_id="PB-001",
        asserted_tenant_id=None,
    )
    assert use_case.execute.await_args.args[0].transaction.tenant_id == "tenant-test"


async def test_consumer_rejects_tenant_that_conflicts_with_portfolio_authority() -> None:
    use_case = AsyncMock()
    route = _ordinary_arrival()
    authority = AsyncMock()
    authority.resolve.side_effect = transaction_tenant_authority.TransactionTenantAuthorityMismatch(
        "scope mismatch"
    )

    with pytest.raises(
        transaction_tenant_authority.TransactionTenantAuthorityMismatch,
        match="scope mismatch",
    ):
        await _consumer(
            use_case,
            route_corporate_action_child=route,
            tenant_authority=authority,
        ).process_message(_message())

    route.execute.assert_not_awaited()
    use_case.execute.assert_not_awaited()


async def test_consumer_retries_tenant_authority_database_failure_before_processing() -> None:
    use_case = AsyncMock()
    route = _ordinary_arrival()
    authority = AsyncMock()
    authority.resolve.side_effect = DBAPIError(
        "SELECT portfolios.tenant_id",
        {},
        RuntimeError("database unavailable"),
        False,
    )

    with pytest.raises(
        RetryableConsumerError,
        match="tenant authority database dependency unavailable",
    ):
        await _consumer(
            use_case,
            route_corporate_action_child=route,
            tenant_authority=authority,
        ).process_message(_message())

    authority.resolve.assert_awaited_once_with(
        portfolio_id="PB-001",
        asserted_tenant_id="tenant-test",
    )
    route.execute.assert_not_awaited()
    use_case.execute.assert_not_awaited()


async def test_consumer_acknowledges_parked_child_without_financial_mutation() -> None:
    use_case = AsyncMock()
    route = AsyncMock()
    route.execute.return_value = CorporateActionArrivalResult(
        CorporateActionArrivalDisposition.PARKED
    )

    await _consumer(use_case, route_corporate_action_child=route).process_message(_message())

    route.execute.assert_awaited_once()
    use_case.execute.assert_not_awaited()


async def test_consumer_maps_canonical_repair_header_to_application_intent() -> None:
    use_case = AsyncMock()
    use_case.execute.return_value = ProcessTransactionResult(
        status=TransactionProcessingStatus.PROCESSED,
        input_transaction_id="TX-001",
    )
    message = _message()
    message.headers.return_value.append(("lotus-transaction-processing-intent", b"repair"))
    message.headers.return_value.append(
        ("lotus-transaction-repair-delivery-id", b" repair-command-001 ")
    )

    await _consumer(use_case).process_message(message)

    command = use_case.execute.await_args.args[0]
    assert command.metadata.processing_intent is TransactionProcessingIntent.REPAIR
    assert command.metadata.repair_delivery_id == "repair-command-001"


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        (
            [("lotus-transaction-repair-delivery-id", b"repair-command-001")],
            "repair delivery id header is invalid",
        ),
        (
            [
                ("lotus-transaction-processing-intent", b"repair"),
                ("lotus-transaction-repair-delivery-id", b"repair-command-001"),
                ("lotus-transaction-repair-delivery-id", b"repair-command-001"),
            ],
            "repair delivery id header is invalid",
        ),
        (
            [
                ("lotus-transaction-processing-intent", b"repair"),
                ("lotus-transaction-repair-delivery-id", b"  "),
            ],
            "repair delivery id header must be nonblank",
        ),
        (
            [
                ("lotus-transaction-processing-intent", b"repair"),
                ("lotus-transaction-repair-delivery-id", b"\xff"),
            ],
            "repair delivery id header is not UTF-8",
        ),
    ],
)
async def test_consumer_fails_closed_on_invalid_repair_delivery_identity(
    headers: list[tuple[str, bytes]],
    message: str,
) -> None:
    use_case = AsyncMock()
    kafka_message = _message()
    kafka_message.headers.return_value.extend(headers)

    with pytest.raises(ValueError, match=message):
        await _consumer(use_case).process_message(kafka_message)

    use_case.execute.assert_not_awaited()


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
        detail={
            "transaction_id": "TX-001",
            "dependency_error": "InstrumentReferenceUnavailableError",
        },
        retryable=True,
    )

    with pytest.raises(
        RetryableConsumerError,
        match="cost_dependency_unavailable:InstrumentReferenceUnavailableError",
    ):
        await _consumer(use_case).process_message(_message())


async def test_consumer_exhausts_owned_dependency_budget_without_runtime_restart() -> None:
    use_case = AsyncMock()
    use_case.execute.side_effect = TransactionProcessingError(
        reason_code="cost_dependency_unavailable",
        detail={"dependency_error": "InstrumentReferenceUnavailableError"},
        retryable=True,
    )
    tenant_authority = AsyncMock()
    tenant_authority.resolve.return_value = "tenant-test"
    consumer = TransactionProcessingConsumer(
        bootstrap_servers="mock_server",
        topic="transactions.persisted",
        group_id="portfolio_transaction_processing_group",
        dlq_topic="dlq.persistence_service",
        use_case=use_case,
        route_corporate_action_child=_ordinary_arrival(),
        tenant_authority=tenant_authority,
        execution_profile=KafkaConsumerExecutionProfile(retryable_failure_backoff_seconds=0.001),
        retryable_failure_max_attempts=2,
    )
    consumer._consumer = MagicMock()
    consumer._send_to_dlq_async = AsyncMock(return_value=True)
    message = _message()

    await consumer._process_polled_message(message, asyncio.get_running_loop())

    assert use_case.execute.await_count == 2
    consumer._send_to_dlq_async.assert_awaited_once()
    consumer._consumer.commit.assert_called_once_with(message=message, asynchronous=False)
    assert consumer._running is True


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


async def test_consumer_propagates_settlement_rejection_for_dlq_mapping() -> None:
    use_case = AsyncMock()
    settlement_rejection = TransactionProcessingRejected(
        reason_code="SELL_010_NON_POSITIVE_NET_SETTLEMENT",
        detail={"transaction_id": "TX-001", "net_settlement_amount": "-1"},
        retryable=False,
    )
    use_case.execute.side_effect = settlement_rejection

    with pytest.raises(TransactionProcessingRejected) as raised:
        await _consumer(use_case).process_message(_message())

    assert raised.value is settlement_rejection


@pytest.mark.parametrize("message_value", [b"not-json", None])
async def test_consumer_rejects_malformed_or_missing_payload_before_use_case(
    message_value: bytes | None,
) -> None:
    use_case = AsyncMock()
    message = _message()
    message.value.return_value = message_value

    with pytest.raises(ValueError):
        await _consumer(use_case).process_message(message)

    use_case.execute.assert_not_awaited()
