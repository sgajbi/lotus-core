# tests/unit/libs/portfolio-common/test_kafka_utils.py
from unittest.mock import ANY, MagicMock, patch

import pytest

# The module we are testing
from portfolio_common.kafka_producer_policy import load_kafka_producer_policy
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer, reset_kafka_producer
from portfolio_common.runtime_settings import RuntimeConfigurationError


@patch("portfolio_common.kafka_utils.Producer")
def test_kafka_producer_initialization(MockProducer):
    """
    Tests that the KafkaProducer is initialized with the correct, production-safe configuration.
    """
    # ACT
    KafkaProducer(bootstrap_servers="mock:9092")

    # ASSERT
    MockProducer.assert_called_once()
    config = MockProducer.call_args[0][0]

    assert config["bootstrap.servers"] == "mock:9092"
    assert config["enable.idempotence"] is True
    assert config["acks"] == "all"
    assert config["max.in.flight.requests.per.connection"] == 5
    assert config["client.id"] == "portfolio-analytics-producer"
    assert config["retries"] == 5
    assert config["linger.ms"] == 5
    assert config["batch.num.messages"] == 1000
    assert config["compression.type"] == "zstd"
    assert config["delivery.timeout.ms"] == 120000
    assert config["request.timeout.ms"] == 30000
    assert config["queue.buffering.max.messages"] == 100000
    assert config["queue.buffering.max.kbytes"] == 1048576


def test_kafka_producer_policy_uses_service_specific_identity_by_default(monkeypatch):
    monkeypatch.delenv("LOTUS_CORE_KAFKA_PRODUCER_CLIENT_ID", raising=False)
    policy = load_kafka_producer_policy(service_name="valuation_orchestrator_service")

    assert policy.service_name == "valuation_orchestrator_service"
    assert policy.client_id == "valuation_orchestrator_service-producer"


@patch("portfolio_common.kafka_utils.Producer")
def test_kafka_producer_applies_service_specific_overrides(MockProducer, monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_PRODUCER_DEFAULTS_JSON",
        '{"linger.ms": 11, "batch.num.messages": 2222}',
    )
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_PRODUCER_SERVICE_OVERRIDES_JSON",
        (
            '{"ingestion_service": {"client.id": "ingestion-writer", '
            '"request.timeout.ms": 12000, "delivery.timeout.ms": 45000, '
            '"queue.buffering.max.messages": 5000, '
            '"queue.buffering.max.kbytes": 32768}}'
        ),
    )

    KafkaProducer(bootstrap_servers="mock:9092", service_name="ingestion_service")

    config = MockProducer.call_args[0][0]
    assert config["client.id"] == "ingestion-writer"
    assert config["linger.ms"] == 11
    assert config["batch.num.messages"] == 2222
    assert config["request.timeout.ms"] == 12000
    assert config["delivery.timeout.ms"] == 45000
    assert config["queue.buffering.max.messages"] == 5000
    assert config["queue.buffering.max.kbytes"] == 32768
    assert config["enable.idempotence"] is True
    assert config["acks"] == "all"
    assert config["max.in.flight.requests.per.connection"] == 5


def test_kafka_producer_policy_rejects_invalid_timeout_relationship(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_KAFKA_PRODUCER_REQUEST_TIMEOUT_MS", "30000")
    monkeypatch.setenv("LOTUS_CORE_KAFKA_PRODUCER_DELIVERY_TIMEOUT_MS", "30000")

    with pytest.raises(RuntimeConfigurationError, match="delivery.timeout.ms"):
        load_kafka_producer_policy()


def test_kafka_producer_policy_strictly_rejects_invalid_batch_size(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("LOTUS_CORE_KAFKA_PRODUCER_BATCH_NUM_MESSAGES", "0")

    with pytest.raises(RuntimeConfigurationError, match="BATCH_NUM_MESSAGES"):
        load_kafka_producer_policy()


def test_kafka_producer_policy_rejects_unsupported_override_key(monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_PRODUCER_DEFAULTS_JSON",
        '{"enable.idempotence": false}',
    )

    with pytest.raises(RuntimeConfigurationError, match="unsupported key"):
        load_kafka_producer_policy()


@patch("portfolio_common.kafka_utils.observe_kafka_producer_event")
@patch("portfolio_common.kafka_utils.Producer")
def test_publish_message_calls_produce(MockProducer, mock_observe_producer_event):
    """
    Tests that the publish_message method correctly calls the underlying client's produce method.
    """
    # ARRANGE
    mock_confluent_producer = MagicMock()
    MockProducer.return_value = mock_confluent_producer

    producer = KafkaProducer()

    # ACT
    producer.publish_message(
        topic="test-topic", key="test-key", value={"data": "value"}, headers=[("corr_id", b"123")]
    )

    # ASSERT
    mock_confluent_producer.produce.assert_called_once_with(
        "test-topic",
        key=b"test-key",
        value=b'{"data": "value"}',
        headers=[("corr_id", b"123")],
        callback=ANY,  # The callback is an inner function, so we just check it exists
    )
    mock_confluent_producer.poll.assert_called_with(0)
    mock_observe_producer_event.assert_called_once_with(
        service="portfolio_common",
        topic="test-topic",
        outcome="accepted",
        reason="produce_queued",
    )


@patch("portfolio_common.kafka_utils.observe_kafka_producer_event")
@patch("portfolio_common.kafka_utils.Producer")
def test_publish_message_handles_queue_full_as_back_pressure(
    MockProducer, mock_observe_producer_event
):
    mock_confluent_producer = MagicMock()
    mock_confluent_producer.produce.side_effect = BufferError("queue full")
    MockProducer.return_value = mock_confluent_producer
    producer = KafkaProducer(service_name="valuation_orchestrator_service")

    with patch("portfolio_common.kafka_utils.logger.warning") as mock_warning:
        with pytest.raises(BufferError, match="queue full"):
            producer.publish_message(topic="valuation.job.requested", key="k", value={"id": "1"})

    mock_observe_producer_event.assert_called_once_with(
        service="valuation_orchestrator_service",
        topic="valuation.job.requested",
        outcome="back_pressure",
        reason="queue_full",
    )
    mock_warning.assert_called_once()
    extra = mock_warning.call_args.kwargs["extra"]
    assert extra["event_name"] == "kafka.producer.back_pressure"
    assert extra["reason_code"] == "queue_full"
    assert extra["topic"] == "valuation.job.requested"


@patch("portfolio_common.kafka_utils.observe_kafka_producer_event")
@patch("portfolio_common.kafka_utils.Producer")
def test_publish_message_observes_generic_publish_failure(
    MockProducer, mock_observe_producer_event
):
    mock_confluent_producer = MagicMock()
    mock_confluent_producer.produce.side_effect = RuntimeError("broker unavailable")
    MockProducer.return_value = mock_confluent_producer
    producer = KafkaProducer()

    with pytest.raises(RuntimeError, match="broker unavailable"):
        producer.publish_message(topic="transactions.raw.received", key="k", value={"id": "1"})

    mock_observe_producer_event.assert_called_once_with(
        service="portfolio_common",
        topic="transactions.raw.received",
        outcome="failed",
        reason="producer_publish_error",
    )


@patch("portfolio_common.kafka_utils.Producer")
def test_delivery_report_handles_success(MockProducer):
    """
    Tests that the internal delivery_report callback correctly handles a successful delivery.
    """
    # ARRANGE
    mock_confluent_producer = MagicMock()
    MockProducer.return_value = mock_confluent_producer
    producer = KafkaProducer()

    # Capture the callback function by calling the method that sets it
    producer.publish_message(topic="t", key="k", value={})
    callback = mock_confluent_producer.produce.call_args.kwargs["callback"]

    mock_msg = MagicMock()
    mock_msg.topic.return_value = "t"
    mock_msg.key.return_value = b"k"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 12
    err = None  # Error is None on success

    # ACT & ASSERT
    with patch("portfolio_common.kafka_utils.logger") as mock_logger:
        callback(err, mock_msg)
        mock_logger.info.assert_called_with("Kafka message delivered.", extra=ANY)
        extra = mock_logger.info.call_args.kwargs["extra"]
        assert extra["event_name"] == "kafka.producer.delivery_succeeded"
        assert extra["reason_code"] == "delivery_acknowledged"
        assert extra["topic"] == "t"
        assert extra["partition"] == 0
        assert extra["offset"] == 12


@patch("portfolio_common.kafka_utils.Producer")
def test_delivery_report_handles_failure(MockProducer):
    """
    Tests that the internal delivery_report callback correctly handles a failed delivery.
    """
    # ARRANGE
    mock_confluent_producer = MagicMock()
    MockProducer.return_value = mock_confluent_producer
    producer = KafkaProducer()

    producer.publish_message(topic="t", key="k", value={})
    callback = mock_confluent_producer.produce.call_args.kwargs["callback"]

    mock_msg = MagicMock()
    mock_msg.topic.return_value = "t"
    mock_msg.key.return_value = b"k"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 12
    # A KafkaException object is passed on failure
    err = MagicMock()
    err.__str__.return_value = "Mock Kafka Error"

    # ACT & ASSERT
    with patch("portfolio_common.kafka_utils.logger") as mock_logger:
        callback(err, mock_msg)
        mock_logger.error.assert_called_with("Kafka message delivery failed.", extra=ANY)
        extra = mock_logger.error.call_args.kwargs["extra"]
        assert extra["event_name"] == "kafka.producer.delivery_failed"
        assert extra["reason_code"] == "delivery_error"
        assert extra["topic"] == "t"
        assert extra["partition"] == 0
        assert extra["offset"] == 12
        assert extra["error_type"] == "MagicMock"


@patch("portfolio_common.kafka_utils.Producer")
def test_reset_kafka_producer_clears_singleton(MockProducer):
    mock_confluent_producer = MagicMock()
    MockProducer.return_value = mock_confluent_producer

    producer = get_kafka_producer()
    assert producer is get_kafka_producer()
    service_producer = get_kafka_producer(service_name="valuation_orchestrator_service")
    assert service_producer is not producer

    reset_kafka_producer(timeout=0)

    assert mock_confluent_producer.flush.call_count == 2
    assert get_kafka_producer() is not producer


@patch("portfolio_common.kafka_utils.Producer")
def test_kafka_producer_close_logs_undelivered_messages(MockProducer):
    mock_confluent_producer = MagicMock()
    mock_confluent_producer.flush.return_value = 2
    MockProducer.return_value = mock_confluent_producer

    producer = KafkaProducer()

    with patch("portfolio_common.kafka_utils.logger.error") as mock_log_error:
        producer.close(timeout=7)

    mock_confluent_producer.flush.assert_called_once_with(7)
    assert producer.producer is None
    assert "Kafka producer close left undelivered messages." == mock_log_error.call_args.args[0]
    assert mock_log_error.call_args.kwargs["extra"]["undelivered_count"] == 2


@patch("portfolio_common.kafka_utils.Producer")
def test_kafka_producer_close_logs_flush_exception_and_clears_producer(MockProducer):
    mock_confluent_producer = MagicMock()
    mock_confluent_producer.flush.side_effect = RuntimeError("flush failed")
    MockProducer.return_value = mock_confluent_producer

    producer = KafkaProducer()

    with patch("portfolio_common.kafka_utils.logger.error") as mock_log_error:
        producer.close(timeout=3)

    mock_confluent_producer.flush.assert_called_once_with(3)
    assert producer.producer is None
    assert "Kafka producer close flush failed." == mock_log_error.call_args.args[0]
