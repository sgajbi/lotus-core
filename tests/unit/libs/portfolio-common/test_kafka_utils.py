# tests/unit/libs/portfolio-common/test_kafka_utils.py
from unittest.mock import ANY, MagicMock, patch

# The module we are testing
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer, reset_kafka_producer


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
    assert config["retries"] == 5


@patch("portfolio_common.kafka_utils.Producer")
def test_publish_message_calls_produce(MockProducer):
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
    err = None  # Error is None on success

    # ACT & ASSERT
    with patch("portfolio_common.kafka_utils.logger") as mock_logger:
        callback(err, mock_msg)
        mock_logger.info.assert_called_with("Message delivered with key 'k'", extra=ANY)


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
    # A KafkaException object is passed on failure
    err = MagicMock()
    err.__str__.return_value = "Mock Kafka Error"

    # ACT & ASSERT
    with patch("portfolio_common.kafka_utils.logger") as mock_logger:
        callback(err, mock_msg)
        mock_logger.error.assert_called_with(
            "Message delivery failed for topic t key b'k': Mock Kafka Error"
        )


@patch("portfolio_common.kafka_utils.Producer")
def test_reset_kafka_producer_clears_singleton(MockProducer):
    mock_confluent_producer = MagicMock()
    MockProducer.return_value = mock_confluent_producer

    producer = get_kafka_producer()
    assert producer is get_kafka_producer()

    reset_kafka_producer(timeout=0)

    mock_confluent_producer.flush.assert_called()
    assert get_kafka_producer() is not producer
