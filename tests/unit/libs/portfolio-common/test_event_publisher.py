from __future__ import annotations

from unittest.mock import MagicMock

from portfolio_common.event_publisher import (
    EventPublishRequest,
    EventPublishStatus,
    KafkaEventPublisher,
)
from portfolio_common.infrastructure_errors import (
    KafkaPublishBackPressure,
    KafkaPublishFailed,
    KafkaPublishUncertain,
)
from portfolio_common.kafka_utils import KafkaProducer


def test_kafka_event_publisher_returns_success_and_preserves_contract() -> None:
    producer = MagicMock(spec=KafkaProducer)
    publisher = KafkaEventPublisher(producer)

    result = publisher.publish(
        EventPublishRequest(
            topic="transactions.raw.received",
            key="PB-001",
            value={"transaction_id": "TXN-001"},
            headers=[("correlation_id", b"corr-001")],
        )
    )

    assert result.status == EventPublishStatus.SUCCESS
    producer.publish_message.assert_called_once_with(
        topic="transactions.raw.received",
        key="PB-001",
        value={"transaction_id": "TXN-001"},
        headers=[("correlation_id", b"corr-001")],
    )


def test_kafka_event_publisher_maps_buffer_error_to_retryable_failure() -> None:
    producer = MagicMock(spec=KafkaProducer)
    producer.publish_message.side_effect = BufferError("local queue full")
    publisher = KafkaEventPublisher(producer)

    result = publisher.publish(EventPublishRequest(topic="topic", key="key", value={"id": "1"}))

    assert result.status == EventPublishStatus.RETRYABLE_FAILURE
    assert result.error_message == "local queue full"
    assert isinstance(result.infrastructure_error, KafkaPublishBackPressure)
    assert result.infrastructure_error.safe_diagnostics() == {
        "reason_code": "kafka_publish_back_pressure",
        "dependency": "kafka",
        "retryable": True,
        "message": "Kafka producer local queue is saturated.",
        "context": {"topic": "topic", "key_present": "True"},
    }


def test_kafka_event_publisher_maps_unexpected_publish_error_to_terminal_failure() -> None:
    producer = MagicMock(spec=KafkaProducer)
    producer.publish_message.side_effect = RuntimeError("serialization failed")
    publisher = KafkaEventPublisher(producer)

    result = publisher.publish(EventPublishRequest(topic="topic", key="key", value={"id": "1"}))

    assert result.status == EventPublishStatus.TERMINAL_FAILURE
    assert result.error_message == "serialization failed"
    assert isinstance(result.infrastructure_error, KafkaPublishFailed)
    assert result.infrastructure_error.reason_code == "kafka_publish_failed"
    assert result.infrastructure_error.safe_context == {"topic": "topic", "key_present": "True"}


def test_kafka_event_publisher_maps_flush_timeout_to_uncertain_publish() -> None:
    producer = MagicMock(spec=KafkaProducer)
    producer.flush.return_value = 2
    publisher = KafkaEventPublisher(producer)

    result = publisher.confirm_delivery(timeout_seconds=5)

    assert result.status == EventPublishStatus.UNCERTAIN
    assert result.undelivered_count == 2
    assert isinstance(result.infrastructure_error, KafkaPublishUncertain)
    assert result.infrastructure_error.reason_code == "kafka_publish_uncertain"
    assert result.infrastructure_error.safe_context == {
        "timeout_seconds": "5",
        "undelivered_count": "2",
    }
    producer.flush.assert_called_once_with(timeout=5)
