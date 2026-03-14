from unittest.mock import MagicMock, patch

import pytest
from confluent_kafka import KafkaException
from portfolio_common.kafka_admin import (
    KafkaTopicVerificationError,
    ensure_topics_exist,
)


@patch("portfolio_common.kafka_admin.AdminClient")
def test_ensure_topics_exist_passes_when_all_topics_exist(mock_admin_client_cls):
    mock_admin_client = MagicMock()
    mock_admin_client.list_topics.return_value.topics.keys.return_value = {
        "topic-a",
        "topic-b",
    }
    mock_admin_client_cls.return_value = mock_admin_client

    ensure_topics_exist.__wrapped__(["topic-a", "topic-b"])

    mock_admin_client.list_topics.assert_called_once_with(timeout=5)


@patch("portfolio_common.kafka_admin.AdminClient")
def test_ensure_topics_exist_raises_kafka_exception_for_missing_topics(mock_admin_client_cls):
    mock_admin_client = MagicMock()
    mock_admin_client.list_topics.return_value.topics.keys.return_value = {"topic-a"}
    mock_admin_client_cls.return_value = mock_admin_client

    with pytest.raises(KafkaException):
        ensure_topics_exist.__wrapped__(["topic-a", "topic-b"])


@patch("portfolio_common.kafka_admin.AdminClient")
def test_ensure_topics_exist_raises_typed_error_for_unexpected_failures(mock_admin_client_cls):
    mock_admin_client = MagicMock()
    mock_admin_client.list_topics.side_effect = RuntimeError("metadata call failed")
    mock_admin_client_cls.return_value = mock_admin_client

    with pytest.raises(KafkaTopicVerificationError) as exc_info:
        ensure_topics_exist.__wrapped__(["topic-a"])

    assert "Unexpected error while verifying Kafka topics." in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RuntimeError)
