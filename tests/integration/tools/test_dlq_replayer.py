# libs/portfolio-common/tests/integration/test_dlq_replayer.py
import asyncio
import json
import os
import uuid
import warnings
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio  # <-- IMPORT PYTEST-ASYNCIO
from confluent_kafka.admin import AdminClient, NewTopic
from portfolio_common.kafka_utils import KafkaProducer

from tools.dlq_replayer import DLQReplayConsumer

pytestmark = pytest.mark.asyncio


def _kafka_bootstrap_host() -> str:
    return os.environ["KAFKA_BOOTSTRAP_SERVERS"]


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock of the KafkaProducer for the replayer to use."""
    mock = MagicMock()
    mock.publish_message = MagicMock()
    mock.flush = MagicMock(return_value=0)
    return mock


# FIX: Use the correct decorator for an async fixture
@pytest_asyncio.fixture
async def unique_dlq_topic(docker_services) -> str:
    """
    Creates a unique, temporary Kafka topic for the test and yields its name.
    Deletes the topic after the test is complete.
    """
    topic_name = f"test-dlq-{uuid.uuid4()}"
    kafka_bootstrap_host = _kafka_bootstrap_host()
    admin_client = AdminClient({"bootstrap.servers": kafka_bootstrap_host})

    # Create the topic
    admin_client.create_topics([NewTopic(topic_name, num_partitions=1, replication_factor=1)])

    # Wait for the topic to be fully created
    start_time = asyncio.get_event_loop().time()
    while True:
        if topic_name in admin_client.list_topics(timeout=5).topics:
            break
        if asyncio.get_event_loop().time() - start_time > 10:
            raise TimeoutError(f"Topic '{topic_name}' not created within 10 seconds.")
        await asyncio.sleep(0.5)

    yield topic_name

    # Cleanup: delete the topic
    fs = admin_client.delete_topics([topic_name])
    for topic, f in fs.items():
        try:
            f.result()  # The result itself is None on success
        except Exception as e:
            warnings.warn(
                f"Failed to delete topic {topic}: {e}",
                stacklevel=2,
            )


async def test_dlq_replayer_consumes_and_republishes(
    docker_services, mock_kafka_producer, unique_dlq_topic
):
    """
    GIVEN a message in a unique DLQ topic
    WHEN the DLQReplayConsumer runs
    THEN it should parse the message and republish it to the original topic.
    """
    # ARRANGE
    kafka_bootstrap_host = _kafka_bootstrap_host()
    dlq_topic = unique_dlq_topic  # Use the isolated topic for this test

    original_topic = "transactions.raw.received"
    original_key = f"txn-{uuid.uuid4()}"
    original_value = {"transaction_id": original_key, "amount": 1000}
    correlation_id = f"corr-{uuid.uuid4()}"

    dlq_payload = {
        "original_topic": original_topic,
        "original_key": original_key,
        "original_value": json.dumps(original_value),
        "error_reason": "Test-induced failure",
        "correlation_id": correlation_id,
    }

    setup_producer = KafkaProducer(bootstrap_servers=kafka_bootstrap_host)
    setup_producer.publish_message(
        topic=dlq_topic,
        key="dlq_test_key",
        value=dlq_payload,
        headers=[("correlation_id", correlation_id.encode("utf-8"))],
    )
    setup_producer.flush()
    await asyncio.sleep(2)

    # ACT
    with patch("tools.dlq_replayer.get_kafka_producer", return_value=mock_kafka_producer):
        consumer = DLQReplayConsumer(
            bootstrap_servers=kafka_bootstrap_host,
            topic=dlq_topic,
            group_id=f"test-replayer-group-{uuid.uuid4()}",
            limit=1,
        )
        await consumer.run()

    # ASSERT
    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs

    assert call_args["topic"] == original_topic
    assert call_args["key"] == original_key
    assert call_args["value"] == original_value
    assert ("correlation_id", correlation_id.encode("utf-8")) in call_args["headers"]


async def test_dlq_replayer_skips_malformed_message(
    docker_services, mock_kafka_producer, unique_dlq_topic
):
    """
    GIVEN a malformed (non-JSON) message and a valid message in a unique DLQ
    WHEN the DLQReplayConsumer runs
    THEN it should skip the malformed message and successfully republish the valid one.
    """
    # ARRANGE
    kafka_bootstrap_host = _kafka_bootstrap_host()
    dlq_topic = unique_dlq_topic  # Use the isolated topic for this test

    # 1. Publish a malformed message (not valid JSON)
    setup_producer = KafkaProducer(bootstrap_servers=kafka_bootstrap_host)
    setup_producer.producer.produce(
        topic=dlq_topic, key=b"malformed-key", value=b"this is not json"
    )

    # 2. Publish a valid DLQ message
    valid_dlq_payload = {
        "original_topic": "portfolios.raw.received",
        "original_key": "valid-key-01",
        "original_value": json.dumps({"portfolioId": "P01"}),
        "error_reason": "Test failure",
        "correlation_id": "corr-abc",
    }
    setup_producer.publish_message(
        topic=dlq_topic,
        key="valid-dlq-key",
        value=valid_dlq_payload,
    )
    setup_producer.flush()
    await asyncio.sleep(2)

    # ACT
    with patch("tools.dlq_replayer.get_kafka_producer", return_value=mock_kafka_producer):
        consumer = DLQReplayConsumer(
            bootstrap_servers=kafka_bootstrap_host,
            topic=dlq_topic,
            group_id=f"test-replayer-group-{uuid.uuid4()}",
            limit=2,  # Attempt to process both messages
        )
        await consumer.run()

    # ASSERT
    # The replayer should have skipped the malformed message and only published the valid one.
    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs

    assert call_args["topic"] == "portfolios.raw.received"
    assert call_args["key"] == "valid-key-01"
    assert call_args["value"] == {"portfolioId": "P01"}


async def test_dlq_replayer_does_not_commit_when_replay_flush_times_out(
    docker_services, mock_kafka_producer, unique_dlq_topic
):
    kafka_bootstrap_host = _kafka_bootstrap_host()
    dlq_topic = unique_dlq_topic

    original_topic = "transactions.raw.received"
    original_key = f"txn-{uuid.uuid4()}"
    original_value = {"transaction_id": original_key, "amount": 1000}

    dlq_payload = {
        "original_topic": original_topic,
        "original_key": original_key,
        "original_value": json.dumps(original_value),
        "error_reason": "Test-induced failure",
        "correlation_id": f"corr-{uuid.uuid4()}",
    }

    setup_producer = KafkaProducer(bootstrap_servers=kafka_bootstrap_host)
    setup_producer.publish_message(
        topic=dlq_topic,
        key="dlq_timeout_key",
        value=dlq_payload,
    )
    setup_producer.flush()
    await asyncio.sleep(2)

    mock_kafka_producer.flush.return_value = 1

    replay_group_id = f"test-replayer-group-{uuid.uuid4()}"

    with patch("tools.dlq_replayer.get_kafka_producer", return_value=mock_kafka_producer):
        consumer = DLQReplayConsumer(
            bootstrap_servers=kafka_bootstrap_host,
            topic=dlq_topic,
            group_id=replay_group_id,
            limit=1,
        )
        await consumer.run()

    mock_kafka_producer.publish_message.assert_called_once()
    assert any(
        call.kwargs == {"timeout": 5} for call in mock_kafka_producer.flush.call_args_list
    )

    mock_kafka_producer.publish_message.reset_mock()
    mock_kafka_producer.flush.reset_mock()
    mock_kafka_producer.flush.return_value = 0

    with patch("tools.dlq_replayer.get_kafka_producer", return_value=mock_kafka_producer):
        consumer = DLQReplayConsumer(
            bootstrap_servers=kafka_bootstrap_host,
            topic=dlq_topic,
            group_id=replay_group_id,
            limit=1,
        )
        await consumer.run()

    mock_kafka_producer.publish_message.assert_called_once()
    assert any(
        call.kwargs == {"timeout": 5} for call in mock_kafka_producer.flush.call_args_list
    )
