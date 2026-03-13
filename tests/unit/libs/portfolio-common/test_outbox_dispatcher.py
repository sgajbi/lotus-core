from unittest.mock import MagicMock

from portfolio_common.kafka_utils import KafkaProducer


def test_get_outbox_runtime_settings_uses_default(monkeypatch):
    monkeypatch.delenv("OUTBOX_DISPATCHER_MAX_RETRIES", raising=False)

    import portfolio_common.outbox_dispatcher as module

    settings = module.get_outbox_runtime_settings()

    assert settings.max_retries == 3


def test_get_outbox_runtime_settings_uses_env_override(monkeypatch):
    monkeypatch.setenv("OUTBOX_DISPATCHER_MAX_RETRIES", "7")

    import portfolio_common.outbox_dispatcher as module

    settings = module.get_outbox_runtime_settings()

    assert settings.max_retries == 7


def test_dispatcher_constructor_allows_explicit_max_retries(monkeypatch):
    monkeypatch.setenv("OUTBOX_DISPATCHER_MAX_RETRIES", "9")

    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(
        kafka_producer=MagicMock(spec=KafkaProducer),
        max_retries=2,
    )

    assert dispatcher._max_retries == 2
