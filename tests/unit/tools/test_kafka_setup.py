"""Verify governed Kafka topic provisioning and drift rejection."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from confluent_kafka import KafkaError, KafkaException
from portfolio_common.config import KAFKA_TOPIC_PARTITION_COUNTS
from portfolio_common.runtime_settings import RuntimeConfigurationError

from tools import kafka_setup as kafka_setup_module
from tools.kafka_setup import (
    KafkaTopicProvisioningError,
    build_topic_admin_client,
    create_topics,
)


def test_topic_admin_client_uses_shared_local_transport_policy(monkeypatch) -> None:
    admin_client = MagicMock()
    monkeypatch.setattr(kafka_setup_module, "AdminClient", admin_client)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:39092")
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS_HOST", raising=False)

    build_topic_admin_client()

    admin_client.assert_called_once_with(
        {
            "bootstrap.servers": "localhost:39092",
            "security.protocol": "PLAINTEXT",
        }
    )


def test_topic_admin_client_resolves_environment_after_module_import(monkeypatch) -> None:
    admin_client = MagicMock()
    monkeypatch.setattr(kafka_setup_module, "AdminClient", admin_client)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:39093")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS_HOST", "localhost:39094")

    build_topic_admin_client()

    assert admin_client.call_args.args[0]["bootstrap.servers"] == "localhost:39094"


def test_topic_admin_client_accepts_explicit_runtime_authority(monkeypatch) -> None:
    admin_client = MagicMock()
    monkeypatch.setattr(kafka_setup_module, "AdminClient", admin_client)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "stale-broker:9093")

    build_topic_admin_client("runtime-broker:19092")

    assert admin_client.call_args.args[0]["bootstrap.servers"] == "runtime-broker:19092"


def test_topic_admin_client_rejects_plaintext_production_before_construction(monkeypatch) -> None:
    admin_client = MagicMock()
    monkeypatch.setattr(kafka_setup_module, "AdminClient", admin_client)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")

    with pytest.raises(RuntimeConfigurationError, match="plaintext Kafka transport"):
        build_topic_admin_client()

    admin_client.assert_not_called()


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
        match="'expected': 12, 'actual': 1",
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
