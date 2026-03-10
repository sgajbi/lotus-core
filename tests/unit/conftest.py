from unittest.mock import MagicMock

import pytest
from portfolio_common.kafka_utils import reset_kafka_producer


@pytest.fixture(autouse=True)
def _reset_kafka_producer_singleton(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("portfolio_common.kafka_utils.Producer", MagicMock())
    reset_kafka_producer(timeout=0)
    yield
    reset_kafka_producer(timeout=0)
