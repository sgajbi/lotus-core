import asyncio
import logging
from unittest.mock import MagicMock

import pytest
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


def test_get_outbox_runtime_settings_falls_back_on_invalid_env(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS", "nope")
    monkeypatch.setenv("OUTBOX_DISPATCHER_BATCH_SIZE", "0")
    monkeypatch.setenv("OUTBOX_DISPATCHER_MAX_RETRIES", "-4")

    import portfolio_common.outbox_settings as module

    settings = module.get_outbox_runtime_settings()

    assert settings.poll_interval_seconds == 5
    assert settings.batch_size == 50
    assert settings.max_retries == 3
    assert "falling back to default" in caplog.text


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


@pytest.mark.asyncio
async def test_dispatcher_stop_interrupts_poll_sleep(monkeypatch):
    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(
        kafka_producer=MagicMock(spec=KafkaProducer),
        poll_interval=60,
    )
    batch_started = asyncio.Event()

    def _process_batch_sync():
        batch_started.set()

    monkeypatch.setattr(dispatcher, "_process_batch_sync", _process_batch_sync)

    task = asyncio.create_task(dispatcher.run())
    await batch_started.wait()
    await asyncio.sleep(0)

    dispatcher.stop()

    await asyncio.wait_for(task, timeout=0.2)
