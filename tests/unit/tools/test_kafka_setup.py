"""Verify governed Kafka topic provisioning and drift rejection."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from confluent_kafka import KafkaError, KafkaException
from portfolio_common.config import KAFKA_TOPIC_PARTITION_COUNTS

from tools.kafka_setup import KafkaTopicProvisioningError, create_topics


def test_create_topics_uses_each_source_owned_partition_count() -> None:
    admin_client = MagicMock()
    admin_client.list_topics.return_value.topics = {}
    admin_client.create_topics.return_value = {
        topic: MagicMock() for topic in KAFKA_TOPIC_PARTITION_COUNTS
    }

    create_topics(admin_client)

    created_topics = admin_client.create_topics.call_args.args[0]
    created_partition_counts = {topic.topic: topic.num_partitions for topic in created_topics}
    assert created_partition_counts == KAFKA_TOPIC_PARTITION_COUNTS


def test_create_topics_rejects_existing_partition_count_mismatch() -> None:
    admin_client = MagicMock()
    admin_client.list_topics.return_value.topics = {
        "transactions.persisted": SimpleNamespace(partitions={0: object()}),
    }

    with pytest.raises(
        KafkaTopicProvisioningError,
        match="'expected': 8, 'actual': 1",
    ):
        create_topics(admin_client)

    admin_client.create_topics.assert_not_called()


def test_create_topics_fails_closed_when_broker_rejects_creation() -> None:
    admin_client = MagicMock()
    admin_client.list_topics.return_value.topics = {}
    creation_futures = {topic: MagicMock() for topic in KAFKA_TOPIC_PARTITION_COUNTS}
    rejected_topic = "transactions.persisted"
    creation_futures[rejected_topic].result.side_effect = KafkaException(
        KafkaError(KafkaError.INVALID_PARTITIONS)
    )
    admin_client.create_topics.return_value = creation_futures

    with pytest.raises(
        KafkaTopicProvisioningError,
        match="Kafka topic creation failed",
    ):
        create_topics(admin_client)
