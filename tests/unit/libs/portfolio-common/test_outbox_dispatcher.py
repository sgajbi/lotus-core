import asyncio
import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.outbox_settings import OutboxRuntimeConfigurationError


def test_get_outbox_runtime_settings_uses_default(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_MAX_RETRIES", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_RETRY_MAX_ELAPSED_SECONDS", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_BATCH_SIZE", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_RETRY_INITIAL_DELAY_SECONDS", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_RETRY_MAX_DELAY_SECONDS", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_RETRY_JITTER_SECONDS", raising=False)

    import portfolio_common.outbox_settings as module

    settings = module.get_outbox_runtime_settings()

    assert settings.poll_interval_seconds == 5
    assert settings.batch_size == 50
    assert settings.claim_lease_seconds == 60
    assert settings.max_retries == 3
    assert settings.retry_max_elapsed_seconds == 0
    assert settings.retry_initial_delay_seconds == 5
    assert settings.retry_max_delay_seconds == 300
    assert settings.retry_jitter_seconds == 0


def test_get_outbox_runtime_settings_uses_env_override(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS", "11")
    monkeypatch.setenv("OUTBOX_DISPATCHER_BATCH_SIZE", "77")
    monkeypatch.setenv("OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS", "45")
    monkeypatch.setenv("OUTBOX_DISPATCHER_MAX_RETRIES", "7")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_MAX_ELAPSED_SECONDS", "900")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_INITIAL_DELAY_SECONDS", "13")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_MAX_DELAY_SECONDS", "144")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_JITTER_SECONDS", "3")

    import portfolio_common.outbox_settings as module

    settings = module.get_outbox_runtime_settings()

    assert settings.poll_interval_seconds == 11
    assert settings.batch_size == 77
    assert settings.claim_lease_seconds == 45
    assert settings.max_retries == 7
    assert settings.retry_max_elapsed_seconds == 900
    assert settings.retry_initial_delay_seconds == 13
    assert settings.retry_max_delay_seconds == 144
    assert settings.retry_jitter_seconds == 3


def test_get_outbox_runtime_settings_falls_back_on_invalid_env(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS", "nope")
    monkeypatch.setenv("OUTBOX_DISPATCHER_BATCH_SIZE", "0")
    monkeypatch.setenv("OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS", "0")
    monkeypatch.setenv("OUTBOX_DISPATCHER_MAX_RETRIES", "-4")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_MAX_ELAPSED_SECONDS", "-10")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_INITIAL_DELAY_SECONDS", "0")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_MAX_DELAY_SECONDS", "1")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_JITTER_SECONDS", "-1")

    import portfolio_common.outbox_settings as module

    settings = module.get_outbox_runtime_settings()

    assert settings.poll_interval_seconds == 5
    assert settings.batch_size == 50
    assert settings.claim_lease_seconds == 60
    assert settings.max_retries == 3
    assert settings.retry_max_elapsed_seconds == 0
    assert settings.retry_initial_delay_seconds == 5
    assert settings.retry_max_delay_seconds == 5
    assert settings.retry_jitter_seconds == 0
    assert "falling back to default" in caplog.text


def test_get_outbox_runtime_settings_strict_rejects_invalid_env(monkeypatch):
    monkeypatch.setenv("LOTUS_CORE_STRICT_CONFIG_VALIDATION", "true")
    monkeypatch.setenv("OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS", "0")

    import portfolio_common.outbox_settings as module

    with pytest.raises(OutboxRuntimeConfigurationError, match="OUTBOX_DISPATCHER_POLL_INTERVAL"):
        module.get_outbox_runtime_settings()


def test_dispatcher_constructor_allows_explicit_max_retries(monkeypatch):
    monkeypatch.setenv("OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS", "13")
    monkeypatch.setenv("OUTBOX_DISPATCHER_BATCH_SIZE", "88")
    monkeypatch.setenv("OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS", "44")
    monkeypatch.setenv("OUTBOX_DISPATCHER_MAX_RETRIES", "9")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_MAX_ELAPSED_SECONDS", "810")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_INITIAL_DELAY_SECONDS", "21")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_MAX_DELAY_SECONDS", "210")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_JITTER_SECONDS", "4")

    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(
        kafka_producer=MagicMock(spec=KafkaProducer),
        poll_interval=2,
        batch_size=4,
        max_retries=2,
        claim_lease_seconds=12,
        retry_max_elapsed_seconds=120,
        retry_initial_delay_seconds=7,
        retry_max_delay_seconds=70,
        retry_jitter_seconds=0,
    )

    assert dispatcher._poll_interval == 2
    assert dispatcher._batch_size == 4
    assert dispatcher._max_retries == 2
    assert dispatcher._claim_lease_seconds == 12
    assert dispatcher._retry_max_elapsed_seconds == 120
    assert dispatcher._retry_initial_delay_seconds == 7
    assert dispatcher._retry_max_delay_seconds == 70
    assert dispatcher._retry_jitter_seconds == 0


def test_dispatcher_constructor_uses_runtime_defaults(monkeypatch):
    monkeypatch.setenv("OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS", "17")
    monkeypatch.setenv("OUTBOX_DISPATCHER_BATCH_SIZE", "91")
    monkeypatch.setenv("OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS", "31")
    monkeypatch.setenv("OUTBOX_DISPATCHER_MAX_RETRIES", "6")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_MAX_ELAPSED_SECONDS", "720")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_INITIAL_DELAY_SECONDS", "19")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_MAX_DELAY_SECONDS", "190")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_JITTER_SECONDS", "5")

    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(kafka_producer=MagicMock(spec=KafkaProducer))

    assert dispatcher._poll_interval == 17
    assert dispatcher._batch_size == 91
    assert dispatcher._max_retries == 6
    assert dispatcher._claim_lease_seconds == 31
    assert dispatcher._retry_max_elapsed_seconds == 720
    assert dispatcher._retry_initial_delay_seconds == 19
    assert dispatcher._retry_max_delay_seconds == 190
    assert dispatcher._retry_jitter_seconds == 5


def test_dispatcher_retry_delay_uses_bounded_exponential_backoff() -> None:
    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(
        kafka_producer=MagicMock(spec=KafkaProducer),
        retry_initial_delay_seconds=10,
        retry_max_delay_seconds=45,
        retry_jitter_seconds=0,
    )

    assert dispatcher._retry_delay_seconds(1) == 10.0
    assert dispatcher._retry_delay_seconds(2) == 20.0
    assert dispatcher._retry_delay_seconds(3) == 40.0
    assert dispatcher._retry_delay_seconds(4) == 45.0


def test_dispatcher_elapsed_retry_budget_moves_failure_to_terminal() -> None:
    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(
        kafka_producer=MagicMock(spec=KafkaProducer),
        max_retries=5,
        retry_max_elapsed_seconds=60,
    )
    event = module._ClaimedOutboxEvent(
        id=101,
        aggregate_type="OutboxElapsedBudget",
        aggregate_id="agg-elapsed",
        event_type="TestEvent",
        payload={},
        topic="elapsed.topic",
        correlation_id=None,
        retry_count=0,
        created_at=module.datetime.now(module.timezone.utc) - timedelta(minutes=5),
        claim_token="elapsed-claim",
        claim_expires_at=module.datetime.now(module.timezone.utc) + timedelta(seconds=30),
    )

    success_ids, retryable_failure_ids, terminal_failure_ids = (
        dispatcher._classify_delivery_results(
            [event],
            {101: False},
        )
    )

    assert success_ids == []
    assert retryable_failure_ids == []
    assert terminal_failure_ids == [101]


def test_outbox_failure_metadata_is_source_safe_and_bounded() -> None:
    import portfolio_common.outbox_dispatcher as module

    message = "publish failed password=super-secret; token=abc; " + ("x" * 700)

    metadata = module._failure_metadata(message, failed_at=module.datetime.now(module.timezone.utc))

    assert metadata["last_failure_reason_code"] == "kafka_publish_failed"
    assert metadata["last_failure_category"] == "event_publish_delivery"
    failure_message = metadata["last_failure_message"]
    assert "super-secret" not in failure_message
    assert "abc" not in failure_message
    assert "password=***REDACTED***" in failure_message
    assert len(failure_message) == module.MAX_FAILURE_MESSAGE_LENGTH


def test_terminal_failure_update_persists_structured_failure_metadata() -> None:
    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(kafka_producer=MagicMock(spec=KafkaProducer))
    db = MagicMock()
    event = SimpleNamespace(
        id=42,
        aggregate_type="OutboxUnit",
        topic="unit.topic",
        claim_token="claim-unit",
    )

    dispatcher._mark_terminal_failures(
        db,
        [event],
        [42],
        {42: "flush failed authorization=Bearer secret-token"},
    )

    statement = db.execute.call_args.args[0]
    compiled_params = statement.compile().params
    assert compiled_params["status"] == module.TERMINAL_FAILURE_STATUS
    assert compiled_params["last_failure_reason_code"] == "kafka_flush_failed"
    assert compiled_params["last_failure_category"] == "event_publish_delivery"
    assert "secret-token" not in compiled_params["last_failure_message"]
    assert "authorization=***REDACTED***" in compiled_params["last_failure_message"]
    assert compiled_params["last_failure_at"] is not None


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
