# tests/unit/libs/portfolio-common/test_kafka_consumer.py
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.kafka_consumer import (
    BaseConsumer,
    RetryableConsumerError,
    classify_dlq_reason_code,
)
from portfolio_common.logging_utils import correlation_id_var

pytestmark = pytest.mark.asyncio


# A concrete implementation of the abstract BaseConsumer for testing
class ConcreteTestConsumer(BaseConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mock the abstract method so we can control its behavior in tests
        self.process_message_mock = AsyncMock()

    async def process_message(self, msg):
        await self.process_message_mock(msg)


@pytest.fixture
def mock_confluent_consumer() -> MagicMock:
    """Provides a mock of the underlying confluent_kafka.Consumer."""
    return MagicMock()


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock of the KafkaProducer used for the DLQ."""
    return MagicMock()


@pytest.fixture
def test_consumer(mock_confluent_consumer, mock_kafka_producer) -> ConcreteTestConsumer:
    """Provides a fully mocked instance of our ConcreteTestConsumer."""
    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=mock_confluent_consumer),
        patch(
            "portfolio_common.kafka_consumer.get_kafka_producer", return_value=mock_kafka_producer
        ),
    ):
        consumer = ConcreteTestConsumer(
            bootstrap_servers="mock_bs",
            topic="test-topic",
            group_id="test-group",
            dlq_topic="test.dlq",
        )
        yield consumer


def create_mock_message(key, value, topic="test-topic", error=None, headers=None):
    """Helper function to create a mock Kafka message."""
    mock_msg = MagicMock()
    mock_msg.error.return_value = error
    mock_msg.topic.return_value = topic
    mock_msg.key.return_value = key.encode("utf-8") if key else None
    mock_msg.value.return_value = json.dumps(value).encode("utf-8")
    mock_msg.headers.return_value = headers or []
    return mock_msg


async def test_run_loop_success_path(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    """Tests the happy path: a message is polled, processed, and committed."""
    # ARRANGE
    mock_msg = create_mock_message("key1", {"data": "value1"})
    mock_confluent_consumer.poll.return_value = mock_msg

    async def stop_loop_after_processing(*args, **kwargs):
        test_consumer.shutdown()

    test_consumer.process_message_mock.side_effect = stop_loop_after_processing

    # ACT
    await test_consumer.run()

    # ASSERT
    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    mock_confluent_consumer.commit.assert_called_once_with(message=mock_msg, asynchronous=False)


async def test_run_loop_failure_sends_to_dlq_and_commits(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    """Tests the failure path: a processing error triggers a DLQ publish and then commits the offset."""  # noqa: E501
    # ARRANGE
    mock_msg = create_mock_message("key2", {"data": "value2"})
    mock_confluent_consumer.poll.return_value = mock_msg

    async def fail_and_stop(*args, **kwargs):
        test_consumer.shutdown()
        raise ValueError("Processing failed!")

    test_consumer.process_message_mock.side_effect = fail_and_stop
    test_consumer._send_to_dlq_async = AsyncMock()

    # ACT
    await test_consumer.run()

    # ASSERT
    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    mock_confluent_consumer.commit.assert_called_once_with(message=mock_msg, asynchronous=False)
    test_consumer._send_to_dlq_async.assert_awaited_once()


async def test_run_loop_retryable_error_does_not_commit(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    """Tests the retryable path: a RetryableConsumerError prevents the offset from being committed."""  # noqa: E501
    # ARRANGE
    mock_msg = create_mock_message("key_retry", {"data": "value_retry"})
    mock_confluent_consumer.poll.return_value = mock_msg

    async def fail_and_stop(*args, **kwargs):
        test_consumer.shutdown()
        raise RetryableConsumerError("DB connection dropped!")

    test_consumer.process_message_mock.side_effect = fail_and_stop
    test_consumer._send_to_dlq_async = AsyncMock()

    # ACT
    await test_consumer.run()

    # ASSERT
    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    mock_confluent_consumer.commit.assert_not_called()
    test_consumer._send_to_dlq_async.assert_not_called()


async def test_dlq_payload_is_correct(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    """Tests that the DLQ payload is formatted correctly."""
    # ARRANGE
    mock_msg = create_mock_message(
        "key3", {"data": "value3"}, headers=[("correlation_id", b"corr-123")]
    )
    error = ValueError("Test Error")
    correlation_id = "corr-123"
    test_consumer._record_consumer_dlq_event = AsyncMock()

    # ACT
    # Set the context variable to simulate the state within the consumer's run loop
    token = correlation_id_var.set(correlation_id)
    try:
        # Simulate the try/except block that the run loop provides
        try:
            raise error
        except ValueError as e:
            await test_consumer._send_to_dlq_async(mock_msg, e)
    finally:
        correlation_id_var.reset(token)

    # ASSERT
    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs

    assert call_args["topic"] == "test.dlq"
    assert call_args["key"] == "key3"

    payload = call_args["value"]
    assert payload["original_topic"] == "test-topic"
    assert payload["original_key"] == "key3"
    assert payload["original_value"] == '{"data": "value3"}'
    assert payload["error_reason_code"] == "VALIDATION_ERROR"
    assert "Test Error" in payload["error_reason"]
    assert "Traceback" in payload["error_traceback"]

    headers_dict = dict(call_args["headers"])
    assert headers_dict["correlation_id"] == correlation_id.encode("utf-8")
    test_consumer._record_consumer_dlq_event.assert_awaited_once()


async def test_classify_dlq_reason_code_deserialization():
    assert (
        classify_dlq_reason_code(ValueError("JSON decode failed at position 13"))
        == "DESERIALIZATION_ERROR"
    )


async def test_classify_dlq_reason_code_timeout():
    assert (
        classify_dlq_reason_code(RuntimeError("downstream timeout while reading response"))
        == "DOWNSTREAM_TIMEOUT"
    )


async def test_consumer_applies_runtime_overrides(monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON",
        '{"max.poll.interval.ms": 180000, "fetch.min.bytes": 1}',
    )
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON",
        '{"test-group": {"fetch.min.bytes": 4096, "max.partition.fetch.bytes": 1048576}}',
    )

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=MagicMock()),
        patch("portfolio_common.kafka_consumer.get_kafka_producer", return_value=MagicMock()),
    ):
        consumer = ConcreteTestConsumer(
            bootstrap_servers="mock_bs",
            topic="test-topic",
            group_id="test-group",
            dlq_topic="test.dlq",
        )

    assert consumer._consumer_config["max.poll.interval.ms"] == 180000
    assert consumer._consumer_config["fetch.min.bytes"] == 4096
    assert consumer._consumer_config["max.partition.fetch.bytes"] == 1048576


async def test_consumer_ignores_invalid_runtime_overrides(monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON",
        '{"unsupported.key": 1, "enable.auto.commit": "false"}',
    )
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON",
        '{"test-group": {"session.timeout.ms": "45000"}}',
    )

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=MagicMock()),
        patch("portfolio_common.kafka_consumer.get_kafka_producer", return_value=MagicMock()),
    ):
        consumer = ConcreteTestConsumer(
            bootstrap_servers="mock_bs",
            topic="test-topic",
            group_id="test-group",
            dlq_topic="test.dlq",
        )

    assert "unsupported.key" not in consumer._consumer_config
    assert consumer._consumer_config["enable.auto.commit"] is False
    assert consumer._consumer_config["session.timeout.ms"] == 45000
