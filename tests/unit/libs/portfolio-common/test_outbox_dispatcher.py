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
    monkeypatch.delenv("OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_RETRY_INITIAL_DELAY_SECONDS", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_RETRY_MAX_DELAY_SECONDS", raising=False)
    monkeypatch.delenv("OUTBOX_DISPATCHER_RETRY_JITTER_SECONDS", raising=False)

    import portfolio_common.outbox_settings as module

    settings = module.get_outbox_runtime_settings()

    assert settings.poll_interval_seconds == 5
    assert settings.batch_size == 50
    assert settings.claim_lease_seconds == 130
    assert settings.termination_grace_seconds == 150
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
    monkeypatch.setenv("OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS", "175")
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
    assert settings.termination_grace_seconds == 175
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
    monkeypatch.setenv("OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS", "0")
    monkeypatch.setenv("OUTBOX_DISPATCHER_MAX_RETRIES", "-4")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_MAX_ELAPSED_SECONDS", "-10")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_INITIAL_DELAY_SECONDS", "0")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_MAX_DELAY_SECONDS", "1")
    monkeypatch.setenv("OUTBOX_DISPATCHER_RETRY_JITTER_SECONDS", "-1")

    import portfolio_common.outbox_settings as module

    settings = module.get_outbox_runtime_settings()

    assert settings.poll_interval_seconds == 5
    assert settings.batch_size == 50
    assert settings.claim_lease_seconds == 130
    assert settings.termination_grace_seconds == 150
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
    monkeypatch.setenv("OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS", "160")
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
        claim_lease_seconds=15,
        termination_grace_seconds=25,
        retry_max_elapsed_seconds=120,
        retry_initial_delay_seconds=7,
        retry_max_delay_seconds=70,
        retry_jitter_seconds=0,
    )

    assert dispatcher._poll_interval == 2
    assert dispatcher._batch_size == 4
    assert dispatcher._max_retries == 2
    assert dispatcher._claim_lease_seconds == 15
    assert dispatcher._termination_grace_seconds == 25
    assert dispatcher.shutdown_timeout_seconds == 15
    assert dispatcher._retry_max_elapsed_seconds == 120
    assert dispatcher._retry_initial_delay_seconds == 7
    assert dispatcher._retry_max_delay_seconds == 70
    assert dispatcher._retry_jitter_seconds == 0


def test_dispatcher_constructor_uses_runtime_defaults(monkeypatch):
    monkeypatch.setenv("OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS", "17")
    monkeypatch.setenv("OUTBOX_DISPATCHER_BATCH_SIZE", "91")
    monkeypatch.setenv("OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS", "31")
    monkeypatch.setenv("OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS", "45")
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
    assert dispatcher._termination_grace_seconds == 45
    assert dispatcher.shutdown_timeout_seconds == 15
    assert dispatcher._retry_max_elapsed_seconds == 720
    assert dispatcher._retry_initial_delay_seconds == 19
    assert dispatcher._retry_max_delay_seconds == 190
    assert dispatcher._retry_jitter_seconds == 5


def test_dispatcher_rejects_claim_lease_shorter_than_delivery_fence() -> None:
    import portfolio_common.outbox_dispatcher as module

    producer = MagicMock()
    producer.producer_policy = SimpleNamespace(delivery_timeout_ms=120_000)

    with pytest.raises(
        OutboxRuntimeConfigurationError,
        match="OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS: expected at least 126 seconds",
    ):
        module.OutboxDispatcher(
            kafka_producer=producer,
            claim_lease_seconds=125,
        )


def test_dispatcher_rejects_termination_grace_shorter_than_supervision_fence() -> None:
    import portfolio_common.outbox_dispatcher as module

    producer = MagicMock()
    producer.producer_policy = SimpleNamespace(delivery_timeout_ms=120_000)

    with pytest.raises(
        OutboxRuntimeConfigurationError,
        match="OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS: expected at least 136 seconds",
    ):
        module.OutboxDispatcher(
            kafka_producer=producer,
            claim_lease_seconds=130,
            termination_grace_seconds=135,
        )


def test_dispatcher_flush_waits_until_kafka_delivery_is_fenced() -> None:
    import portfolio_common.outbox_dispatcher as module

    producer = MagicMock()
    producer.producer_policy = SimpleNamespace(delivery_timeout_ms=120_000)
    producer.flush.return_value = 0
    dispatcher = module.OutboxDispatcher(
        kafka_producer=producer,
        claim_lease_seconds=130,
        termination_grace_seconds=150,
    )

    assert dispatcher.shutdown_timeout_seconds == 126
    dispatcher._flush_delivery_results([], {}, {})

    producer.flush.assert_called_once_with(timeout=121)


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


def test_dispatcher_retry_delay_adds_bounded_jitter_before_delay_cap() -> None:
    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(
        kafka_producer=MagicMock(spec=KafkaProducer),
        retry_initial_delay_seconds=10,
        retry_max_delay_seconds=45,
        retry_jitter_seconds=5,
    )
    dispatcher._retry_random = MagicMock()
    dispatcher._retry_random.uniform.return_value = 3

    assert dispatcher._retry_delay_seconds(2) == 23.0
    dispatcher._retry_random.uniform.assert_called_once_with(0, 5)


def test_dispatcher_flush_marks_only_callbackless_events_failed() -> None:
    import portfolio_common.outbox_dispatcher as module

    producer = MagicMock(spec=KafkaProducer)
    producer.flush.return_value = 1
    dispatcher = module.OutboxDispatcher(kafka_producer=producer)
    now = module.datetime.now(module.timezone.utc)
    events = [
        module._ClaimedOutboxEvent(
            id=event_id,
            aggregate_type="OutboxFlush",
            aggregate_id=f"agg-{event_id}",
            partition_key=f"PORT_001|SEC_{event_id}",
            event_type="TestEvent",
            payload={},
            topic="flush.topic",
            correlation_id=None,
            traceparent=None,
            retry_count=0,
            created_at=now,
            claim_token=f"claim-{event_id}",
            claim_expires_at=now + timedelta(seconds=30),
        )
        for event_id in (101, 102)
    ]
    delivery_ack = {102: True}
    delivery_errs: dict[int, str] = {}

    dispatcher._flush_delivery_results(events, delivery_ack, delivery_errs)

    producer.flush.assert_called_once_with(timeout=10)
    producer.reset_after_flush_failure.assert_called_once_with()
    assert delivery_ack == {101: False, 102: True}
    assert delivery_errs == {101: "Kafka flush timed out before delivery callback."}


def test_dispatcher_resets_ambiguous_producer_before_retrying_flush_exception() -> None:
    import portfolio_common.outbox_dispatcher as module

    producer = MagicMock(spec=KafkaProducer)
    producer.flush.side_effect = RuntimeError("flush failed")
    dispatcher = module.OutboxDispatcher(kafka_producer=producer)
    now = module.datetime.now(module.timezone.utc)
    event = module._ClaimedOutboxEvent(
        id=101,
        aggregate_type="OutboxFlush",
        aggregate_id="agg-101",
        partition_key="PORT_001|SEC_A",
        event_type="TestEvent",
        payload={},
        topic="flush.topic",
        correlation_id=None,
        traceparent=None,
        retry_count=0,
        created_at=now,
        claim_token="claim-101",
        claim_expires_at=now + timedelta(seconds=30),
    )
    delivery_ack: dict[int, bool] = {}
    delivery_errs: dict[int, str] = {}

    dispatcher._flush_delivery_results([event], delivery_ack, delivery_errs)

    producer.reset_after_flush_failure.assert_called_once_with()
    assert delivery_ack == {101: False}
    assert delivery_errs == {101: "flush failed"}


def test_dispatcher_retains_claim_when_ambiguous_producer_reset_fails(
    monkeypatch,
) -> None:
    import portfolio_common.outbox_dispatcher as module

    producer = MagicMock(spec=KafkaProducer)
    producer.flush.side_effect = RuntimeError("flush failed")
    producer.reset_after_flush_failure.side_effect = RuntimeError("purge failed")
    dispatcher = module.OutboxDispatcher(kafka_producer=producer)
    event = MagicMock()
    monkeypatch.setattr(dispatcher, "_read_pending_gauge", MagicMock())
    monkeypatch.setattr(dispatcher, "_claim_pending_events", MagicMock(return_value=[event]))
    monkeypatch.setattr(dispatcher, "_renew_claims_for_delivery", MagicMock(return_value=True))
    monkeypatch.setattr(dispatcher, "_publish_events", MagicMock())
    persist_results = MagicMock()
    monkeypatch.setattr(dispatcher, "_persist_delivery_results", persist_results)

    with pytest.raises(RuntimeError, match="purge failed"):
        dispatcher._process_batch_sync()

    persist_results.assert_not_called()


def test_dispatcher_retains_claim_when_timed_out_producer_reset_fails(
    monkeypatch,
) -> None:
    import portfolio_common.outbox_dispatcher as module

    producer = MagicMock(spec=KafkaProducer)
    producer.flush.return_value = 1
    producer.reset_after_flush_failure.side_effect = RuntimeError("purge failed")
    dispatcher = module.OutboxDispatcher(kafka_producer=producer)
    event = MagicMock()
    monkeypatch.setattr(dispatcher, "_read_pending_gauge", MagicMock())
    monkeypatch.setattr(dispatcher, "_claim_pending_events", MagicMock(return_value=[event]))
    monkeypatch.setattr(dispatcher, "_renew_claims_for_delivery", MagicMock(return_value=True))
    monkeypatch.setattr(dispatcher, "_publish_events", MagicMock())
    persist_results = MagicMock()
    monkeypatch.setattr(dispatcher, "_persist_delivery_results", persist_results)

    with pytest.raises(RuntimeError, match="purge failed"):
        dispatcher._process_batch_sync()

    producer.reset_after_flush_failure.assert_called_once_with()
    persist_results.assert_not_called()


def test_dispatcher_refreshes_claim_around_publish_pipeline(monkeypatch) -> None:
    import portfolio_common.outbox_dispatcher as module

    producer = MagicMock(spec=KafkaProducer)
    session = MagicMock()
    session_factory = MagicMock(return_value=session)
    dispatcher = module.OutboxDispatcher(
        kafka_producer=producer,
        db_session_factory=session_factory,
    )
    event = MagicMock(spec=module._ClaimedOutboxEvent)
    monkeypatch.setattr(dispatcher, "_read_pending_gauge", MagicMock())
    monkeypatch.setattr(dispatcher, "_claim_pending_events", MagicMock(return_value=[event]))
    renew_claims = MagicMock(side_effect=[True, True])
    monkeypatch.setattr(dispatcher, "_renew_claims_for_delivery", renew_claims)
    monkeypatch.setattr(dispatcher, "_publish_events", MagicMock())
    monkeypatch.setattr(dispatcher, "_flush_delivery_results", MagicMock())
    monkeypatch.setattr(dispatcher, "_persist_delivery_results", MagicMock())

    assert dispatcher._process_batch_sync() == 1

    assert renew_claims.call_args_list == [
        (([event],), {}),
        (([event],), {}),
    ]


def test_dispatcher_fences_publish_when_claim_refresh_is_incomplete(monkeypatch) -> None:
    import portfolio_common.outbox_dispatcher as module

    producer = MagicMock(spec=KafkaProducer)
    dispatcher = module.OutboxDispatcher(kafka_producer=producer)
    event = MagicMock(spec=module._ClaimedOutboxEvent)
    monkeypatch.setattr(dispatcher, "_read_pending_gauge", MagicMock())
    monkeypatch.setattr(dispatcher, "_claim_pending_events", MagicMock(return_value=[event]))
    monkeypatch.setattr(dispatcher, "_renew_claims_for_delivery", MagicMock(return_value=False))
    publish_events = MagicMock()
    monkeypatch.setattr(dispatcher, "_publish_events", publish_events)

    assert dispatcher._process_batch_sync() == 0
    publish_events.assert_not_called()


def test_dispatcher_aborts_queued_publish_when_post_publish_refresh_is_incomplete(
    monkeypatch,
) -> None:
    import portfolio_common.outbox_dispatcher as module

    producer = MagicMock(spec=KafkaProducer)
    session = MagicMock()
    session_factory = MagicMock(return_value=session)
    dispatcher = module.OutboxDispatcher(
        kafka_producer=producer,
        db_session_factory=session_factory,
    )
    event = MagicMock(spec=module._ClaimedOutboxEvent)
    monkeypatch.setattr(dispatcher, "_read_pending_gauge", MagicMock())
    monkeypatch.setattr(dispatcher, "_claim_pending_events", MagicMock(return_value=[event]))
    monkeypatch.setattr(
        dispatcher,
        "_renew_claims_for_delivery",
        MagicMock(side_effect=[True, False]),
    )
    monkeypatch.setattr(dispatcher, "_publish_events", MagicMock())
    flush_results = MagicMock()
    monkeypatch.setattr(dispatcher, "_flush_delivery_results", flush_results)

    assert dispatcher._process_batch_sync() == 0

    producer.reset_after_flush_failure.assert_called_once_with()
    flush_results.assert_not_called()


def test_dispatcher_refreshes_claim_between_published_events(monkeypatch) -> None:
    import portfolio_common.outbox_dispatcher as module

    producer = MagicMock(spec=KafkaProducer)
    dispatcher = module.OutboxDispatcher(kafka_producer=producer)
    now = module.datetime.now(module.timezone.utc)
    events = [
        module._ClaimedOutboxEvent(
            id=event_id,
            aggregate_type="PublishLoop",
            aggregate_id=f"agg-{event_id}",
            partition_key=f"PORT_001|SEC_{event_id}",
            event_type="TestEvent",
            payload={},
            topic="publish-loop.topic",
            correlation_id=None,
            traceparent=None,
            retry_count=0,
            created_at=now,
            claim_token=f"claim-{event_id}",
            claim_expires_at=now + timedelta(seconds=30),
        )
        for event_id in (201, 202)
    ]
    renew_claims = MagicMock(return_value=False)
    monkeypatch.setattr(dispatcher, "_renew_claims_for_delivery", renew_claims)

    assert dispatcher._publish_events(events, {}, {}) is False

    assert producer.publish_message.call_count == 1
    producer.reset_after_flush_failure.assert_called_once_with()
    assert renew_claims.call_args_list == [((events,), {})]


def test_dispatcher_revalidates_claim_after_each_publish_call(monkeypatch) -> None:
    import portfolio_common.outbox_dispatcher as module

    producer = MagicMock(spec=KafkaProducer)
    dispatcher = module.OutboxDispatcher(kafka_producer=producer)
    now = module.datetime.now(module.timezone.utc)
    event = module._ClaimedOutboxEvent(
        id=203,
        aggregate_type="PublishCallBoundary",
        aggregate_id="agg-203",
        partition_key="PORT_001|SEC_203",
        event_type="TestEvent",
        payload={},
        topic="publish-call.topic",
        correlation_id=None,
        traceparent=None,
        retry_count=0,
        created_at=now,
        claim_token="claim-203",
        claim_expires_at=now + timedelta(seconds=30),
    )
    renew_claims = MagicMock(return_value=False)
    monkeypatch.setattr(dispatcher, "_renew_claims_for_delivery", renew_claims)

    assert dispatcher._publish_events([event], {}, {}) is False

    producer.publish_message.assert_called_once()
    producer.reset_after_flush_failure.assert_called_once_with()
    renew_claims.assert_called_once_with([event])


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
        partition_key="PORT_001|SEC_A",
        event_type="TestEvent",
        payload={},
        topic="elapsed.topic",
        correlation_id=None,
        traceparent=None,
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


def test_process_batch_reports_zero_when_no_stream_head_is_claimable(monkeypatch) -> None:
    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(kafka_producer=MagicMock(spec=KafkaProducer))
    monkeypatch.setattr(dispatcher, "_read_pending_gauge", MagicMock())
    monkeypatch.setattr(dispatcher, "_claim_pending_events", MagicMock(return_value=[]))

    assert dispatcher._process_batch_sync() == 0


@pytest.mark.asyncio
async def test_dispatcher_immediately_drains_after_a_productive_batch(monkeypatch) -> None:
    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(
        kafka_producer=MagicMock(spec=KafkaProducer),
        poll_interval=60,
    )
    process_batch = MagicMock()

    def _process_one_batch() -> int:
        process_batch()
        dispatcher.stop()
        return 1

    monkeypatch.setattr(dispatcher, "_process_batch_sync", _process_one_batch)
    poll_wait = MagicMock(side_effect=AssertionError("productive batches must not poll-wait"))
    monkeypatch.setattr(module.asyncio, "wait_for", poll_wait)

    await dispatcher.run()

    process_batch.assert_called_once_with()
    poll_wait.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_logs_batch_failure_and_honors_concurrent_stop(
    monkeypatch,
    caplog,
) -> None:
    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(
        kafka_producer=MagicMock(spec=KafkaProducer),
        poll_interval=60,
    )

    def _fail_batch() -> int:
        dispatcher.stop()
        raise RuntimeError("deterministic batch failure")

    monkeypatch.setattr(dispatcher, "_process_batch_sync", _fail_batch)

    with caplog.at_level(logging.ERROR):
        await dispatcher.run()

    assert "Outbox dispatcher batch processing failed." in caplog.text


@pytest.mark.asyncio
async def test_dispatcher_continues_after_idle_poll_timeout(monkeypatch) -> None:
    import portfolio_common.outbox_dispatcher as module

    dispatcher = module.OutboxDispatcher(
        kafka_producer=MagicMock(spec=KafkaProducer),
        poll_interval=1,
    )
    batch_count = 0

    def _process_batch_sync() -> int:
        nonlocal batch_count
        batch_count += 1
        if batch_count == 2:
            dispatcher.stop()
        return 0

    monkeypatch.setattr(dispatcher, "_process_batch_sync", _process_batch_sync)

    await dispatcher.run()

    assert batch_count == 2


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
