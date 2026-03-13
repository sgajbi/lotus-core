from unittest.mock import MagicMock

from portfolio_common.kafka_utils import KafkaProducer


def test_get_outbox_runtime_settings_uses_default(monkeypatch):
    monkeypatch.delenv("OUTBOX_DISPATCHER_MAX_RETRIES", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_BATCH_SIZE", raising=False)

    import portfolio_common.outbox_settings as module

    settings = module.get_outbox_runtime_settings()

    assert settings.poll_interval_seconds == 5
    assert settings.batch_size == 50
    assert settings.max_retries == 3


def test_get_outbox_runtime_settings_uses_env_override(monkeypatch):
    monkeypatch.setenv("OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS", "11")
    monkeypatch.setenv("OUTBOX_DISPATCHER_BATCH_SIZE", "77")
    monkeypatch.setenv("OUTBOX_DISPATCHER_MAX_RETRIES", "7")

    import portfolio_common.outbox_settings as module

    settings = module.get_outbox_runtime_settings()

    assert settings.poll_interval_seconds == 11
    assert settings.batch_size == 77
    assert settings.max_retries == 7


def test_dispatcher_constructor_allows_explicit_max_retries(monkeypatch):
    monkeypatch.setenv("OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS", "13")
    monkeypatch.setenv("OUTBOX_DISPATCHER_BATCH_SIZE", "88")
    monkeypatch.setenv("OUTBOX_DISPATCHER_MAX_RETRIES", "9")

    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(
        kafka_producer=MagicMock(spec=KafkaProducer),
        poll_interval=2,
        batch_size=4,
        max_retries=2,
    )

    assert dispatcher._poll_interval == 2
    assert dispatcher._batch_size == 4
    assert dispatcher._max_retries == 2


def test_dispatcher_constructor_uses_runtime_defaults(monkeypatch):
    monkeypatch.setenv("OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS", "17")
    monkeypatch.setenv("OUTBOX_DISPATCHER_BATCH_SIZE", "91")
    monkeypatch.setenv("OUTBOX_DISPATCHER_MAX_RETRIES", "6")

    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(kafka_producer=MagicMock(spec=KafkaProducer))

    assert dispatcher._poll_interval == 17
    assert dispatcher._batch_size == 91
    assert dispatcher._max_retries == 6
