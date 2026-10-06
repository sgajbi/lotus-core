"""Native manager/consumer registration with explicit network substitutes."""

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common import kafka_consumer
from portfolio_common.command_authorization import CommandAuthorizationRejected
from portfolio_common.config import KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC
from portfolio_common.exceptions import RetryableConsumerError
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from src.services.persistence_service.app import consumer_manager
from src.services.persistence_service.app.consumers import base_consumer
from src.services.persistence_service.app.consumers.transaction_source_correction_consumer import (
    TransactionSourceCorrectionConsumer,
)
from tests.unit.services.persistence_service.application.test_transaction_source_correction import (
    case,
)


def _consumer():
    return TransactionSourceCorrectionConsumer(
        bootstrap_servers="explicit-broker-substitute:9092",
        topic="transactions.source_correction.commands",
        group_id="persistence_group_source_corrections",
        dlq_topic=None,
    )


def _message(command):
    message = MagicMock()
    message.value.return_value = json.dumps(command).encode()
    message.headers.return_value = []
    message.topic.return_value = "transactions.source_correction.commands"
    message.partition.return_value = 0
    message.offset.return_value = 1
    message.key.return_value = b"transaction"
    return message


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["unknown", "version", "metadata"])
async def test_native_consumer_refuses_closed_wire_before_database(monkeypatch, fault, caplog):
    _, _, command, *_ = case()
    payload = command.model_dump(mode="json", exclude_unset=True)
    if fault == "unknown":
        payload["secret_payload_value"] = "must-not-be-logged"
    elif fault == "version":
        payload["schema_version"] = "2.0.0"
    else:
        del payload["idempotency_key"]
    database_provider = MagicMock(side_effect=AssertionError("DB must not open"))
    monkeypatch.setattr(base_consumer, "get_async_db_session", database_provider)
    with pytest.raises(ValidationError):
        await _consumer().process_message(_message(payload))
    database_provider.assert_not_called()
    assert "must-not-be-logged" not in caplog.text


@pytest.mark.asyncio
async def test_native_signature_refusal_precedes_semantic_claim_and_source_lookup(monkeypatch):
    _, _, command, _, _, policy = case()
    payload = command.model_dump(mode="json", exclude_unset=True)
    payload["authorization"]["signature"] = "0" * 64
    from src.services.persistence_service.app.consumers import (
        transaction_source_correction_consumer as owning,
    )

    monkeypatch.setattr(owning, "load_command_authorization_policy", lambda: policy)
    db = MagicMock()

    @asynccontextmanager
    async def begin():
        yield

    db.begin = begin

    async def sessions():
        yield db

    monkeypatch.setattr(base_consumer, "get_async_db_session", sessions)
    idempotency = MagicMock()
    monkeypatch.setattr(base_consumer, "IdempotencyRepository", idempotency)
    with pytest.raises(CommandAuthorizationRejected, match="SIGNATURE_INVALID"):
        await _consumer().process_message(_message(payload))
    idempotency.assert_not_called()
    db.execute.assert_not_called()
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_native_database_error_remains_retryable_not_terminal_dlq(monkeypatch):
    _, _, command, *_ = case()

    async def sessions():
        raise OperationalError("controlled DB admission", {}, Exception("controlled transient"))
        yield  # Async-generator provider shape, intentionally unreachable.

    monkeypatch.setattr(base_consumer, "get_async_db_session", sessions)
    with pytest.raises(RetryableConsumerError):
        await _consumer().process_message(
            _message(command.model_dump(mode="json", exclude_unset=True))
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("published", [False, True])
async def test_native_terminal_wire_error_commits_only_after_dlq_publication(
    monkeypatch, published
):
    _, _, command, *_ = case()
    payload = command.model_dump(mode="json", exclude_unset=True) | {"schema_version": "2.0.0"}
    consumer = _consumer()
    dlq_transport = AsyncMock(return_value=published)
    offset_commit = MagicMock(return_value=True)
    monkeypatch.setattr(consumer, "_send_to_dlq_async", dlq_transport)
    monkeypatch.setattr(consumer, "_commit_after_dlq_publication", offset_commit)
    monkeypatch.setattr(consumer, "_handle_dlq_publication_failed", MagicMock())
    consumer._running = False  # One bounded attempt; no broker/retry loop is started.
    message = _message(payload)
    await consumer._process_polled_message(message, asyncio.get_running_loop())
    dlq_transport.assert_awaited_once()
    assert isinstance(dlq_transport.await_args.args[1], ValidationError)
    assert offset_commit.call_count == int(published)


def test_manager_registers_one_native_source_command_consumer_without_booking_alias(monkeypatch):
    for name in (
        "PortfolioConsumer",
        "TransactionPersistenceConsumer",
        "InstrumentConsumer",
        "MarketPriceConsumer",
        "FxRateConsumer",
        "BusinessDateConsumer",
    ):
        monkeypatch.setattr(consumer_manager, name, MagicMock())
    monkeypatch.setattr(consumer_manager, "setup_metrics", lambda: {})
    monkeypatch.setattr(consumer_manager, "create_kafka_producer", MagicMock())
    monkeypatch.setattr(consumer_manager, "OutboxDispatcher", MagicMock())
    broker_substitute = MagicMock()
    monkeypatch.setattr(kafka_consumer, "get_kafka_producer", lambda: broker_substitute)
    manager = consumer_manager.ConsumerManager()
    source_consumers = [
        consumer
        for consumer in manager.consumers
        if isinstance(consumer, TransactionSourceCorrectionConsumer)
    ]
    assert len(source_consumers) == 1
    consumer = source_consumers[0]
    assert consumer.topic == "transactions.source_correction.commands"
    assert consumer.group_id == "persistence_group_source_corrections"
    assert consumer.dlq_topic == KAFKA_PERSISTENCE_SERVICE_DLQ_TOPIC
    assert consumer.tenant_scoped_idempotency
    assert consumer.get_outbox_event(object()) is None
    assert consumer._consumer is None and consumer._producer is broker_substitute
