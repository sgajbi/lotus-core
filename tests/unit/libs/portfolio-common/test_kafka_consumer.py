# tests/unit/libs/portfolio-common/test_kafka_consumer.py
import asyncio
import io
import json
import logging
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest
from confluent_kafka import TopicPartition
from portfolio_common import consumer_dlq_tenant
from portfolio_common.consumer_error_evidence import redacted_payload_text
from portfolio_common.events import TransactionEvent
from portfolio_common.exceptions import TransactionSemanticConflictError
from portfolio_common.ingestion_lineage import ingestion_job_id_var
from portfolio_common.kafka_consumer import (
    BaseConsumer,
    ConsumerDlqTenantAttributionError,
    DlqPublicationBudgetExhausted,
    RetryableConsumerError,
    classify_dlq_reason_code,
)
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile
from portfolio_common.logging_utils import (
    RedactingJsonFormatter,
    correlation_id_var,
    redact_sensitive_text,
    traceparent_var,
)
from portfolio_common.runtime_settings import RuntimeConfigurationError
from pydantic import ValidationError

pytestmark = pytest.mark.asyncio
TRACEPARENT = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"


async def test_malformed_payload_redaction_bounds_scanned_evidence() -> None:
    raw_value = '{"password":"TOP SYNTHETIC_BOUNDED_PAYLOAD_6R","safe":"' + ("x" * 1_000_000)

    with patch(
        "portfolio_common.consumer_error_evidence.redact_sensitive_text",
        wraps=redact_sensitive_text,
    ) as redact:
        result = redacted_payload_text(raw_value)

    assert len(redact.call_args.args[0]) == 16_384
    assert "SYNTHETIC_BOUNDED_PAYLOAD_6R" not in result
    assert result.endswith("<payload-truncated>")


async def test_malformed_payload_redaction_masks_url_cut_before_at_sign() -> None:
    userinfo = "user:SYNTHETIC_TRUNCATED_URL_SECRET_7P"
    url_prefix = f"postgresql://{userinfo}"
    raw_value = ("x" * (16_384 - len(url_prefix))) + url_prefix + "@host/database"

    result = redacted_payload_text(raw_value)

    assert "SYNTHETIC_TRUNCATED_URL_SECRET_7P" not in result
    assert result.endswith("postgresql://***REDACTED***<payload-truncated>")


async def test_malformed_payload_redaction_masks_multiline_scalar() -> None:
    marker = "SYNTHETIC_MULTILINE_SCALAR_4N"

    result = redacted_payload_text(f'{{"password": TOP\n{marker}, "safe": visible}}')

    assert marker not in result
    assert result == '{"password": ***REDACTED***, "safe": visible}'


async def test_malformed_payload_redaction_masks_complete_python_tuple() -> None:
    marker = "SYNTHETIC_TUPLE_PAYLOAD_SECRET_6V"

    result = redacted_payload_text(f"{{'password': ('FIRST', '{marker}'), 'safe': 'visible'}}")

    assert marker not in result
    assert result == "{'password': ***REDACTED***, 'safe': 'visible'}"


async def test_malformed_payload_redaction_masks_unmatched_parenthesis_scalar() -> None:
    marker = "SYNTHETIC_PAREN_PAYLOAD_SECRET_2J"

    result = redacted_payload_text(f"{{'password': TOP){marker}, 'safe': 'visible'}}")

    assert marker not in result
    assert result == "{'password': ***REDACTED***, 'safe': 'visible'}"


async def test_malformed_payload_redaction_masks_triple_quoted_secret() -> None:
    marker = "SYNTHETIC_TRIPLE_QUOTED_PAYLOAD_SECRET_8H"
    raw_value = f"{{'password': '''FIRST\n{marker}''', 'safe': 'visible'}}"

    result = redacted_payload_text(raw_value)

    assert marker not in result
    assert result == "{'password': '''***REDACTED***''', 'safe': 'visible'}"


@pytest.mark.parametrize(
    ("resolved_tenant", "expected_error"),
    [("tenant-a", None), (None, "unknown ingestion job owner")],
)
async def test_dlq_tenant_authority_comes_only_from_durable_job(
    monkeypatch, resolved_tenant, expected_error
) -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = resolved_tenant
    session.execute.return_value = result

    async def sessions():
        yield session

    monkeypatch.setattr(consumer_dlq_tenant, "get_async_db_session", sessions)
    if expected_error:
        with pytest.raises(ConsumerDlqTenantAttributionError, match=expected_error):
            await consumer_dlq_tenant.resolve_consumer_dlq_tenant_id("job-a")
    else:
        assert await consumer_dlq_tenant.resolve_consumer_dlq_tenant_id("job-a") == "tenant-a"
    session.execute.assert_awaited_once()


async def test_dlq_without_job_cannot_query_or_invent_tenant(monkeypatch) -> None:
    session_factory = MagicMock()
    monkeypatch.setattr(consumer_dlq_tenant, "get_async_db_session", session_factory)
    with pytest.raises(ConsumerDlqTenantAttributionError, match="no durable ingestion job"):
        await consumer_dlq_tenant.resolve_consumer_dlq_tenant_id(None)
    session_factory.assert_not_called()


# A concrete implementation of the abstract BaseConsumer for testing
class ConcreteTestConsumer(BaseConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Mock the abstract method so we can control its behavior in tests
        self.process_message_mock = AsyncMock()

    async def process_message(self, msg):
        await self.process_message_mock(msg)


async def test_dlq_producer_uses_consumers_explicit_alternate_bootstrap():
    from portfolio_common.kafka_utils import KAFKA_BOOTSTRAP_SERVERS

    bootstrap = "alternate-consumer-broker:29092"
    assert bootstrap != KAFKA_BOOTSTRAP_SERVERS
    with patch("portfolio_common.kafka_consumer.get_kafka_producer") as producer_factory:
        consumer = ConcreteTestConsumer(
            bootstrap_servers=bootstrap,
            topic="input-topic",
            group_id="alternate-bootstrap-consumer",
            dlq_topic="input-topic.dlq",
        )
        try:
            producer_factory.assert_called_once_with(bootstrap_servers=bootstrap)
            assert consumer._consumer_config["bootstrap.servers"] == bootstrap
            assert consumer._producer is producer_factory.return_value
        finally:
            consumer._native_operations.finish()


async def test_consumer_fails_before_client_construction_for_plaintext_production(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")

    with pytest.raises(RuntimeConfigurationError, match="plaintext Kafka transport"):
        ConcreteTestConsumer(
            bootstrap_servers="mock_bs",
            topic="test-topic",
            group_id="test-group",
        )


@pytest.fixture
def mock_confluent_consumer() -> MagicMock:
    """Provides a mock of the underlying confluent_kafka.Consumer."""
    consumer = MagicMock()
    consumer.commit.side_effect = lambda *, message, asynchronous: [
        TopicPartition(message.topic(), message.partition(), message.offset() + 1)
    ]
    return consumer


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock of the KafkaProducer used for the DLQ."""
    mock = MagicMock()
    mock.flush.return_value = 0
    return mock


@pytest.fixture
def test_consumer(mock_confluent_consumer, mock_kafka_producer) -> ConcreteTestConsumer:
    """Provides a fully mocked instance of our ConcreteTestConsumer."""
    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=mock_confluent_consumer),
        patch(
            "portfolio_common.kafka_consumer.get_kafka_producer", return_value=mock_kafka_producer
        ),
    ):
        consumer = ConcreteTestConsumer(
            bootstrap_servers="mock_bs",
            topic="test-topic",
            group_id="test-group",
            dlq_topic="test.dlq",
        )
        consumer._resolve_consumer_dlq_tenant_id = AsyncMock(return_value="tenant-test")
        yield consumer


def create_mock_message(
    key,
    value,
    topic="test-topic",
    error=None,
    headers=None,
    partition=0,
    offset=42,
):
    """Helper function to create a mock Kafka message."""
    mock_msg = MagicMock()
    mock_msg.error.return_value = error
    mock_msg.topic.return_value = topic
    if isinstance(key, bytes):
        mock_msg.key.return_value = key
    else:
        mock_msg.key.return_value = key.encode("utf-8") if key else None
    mock_msg.value.return_value = json.dumps(value).encode("utf-8")
    mock_msg.headers.return_value = headers or []
    mock_msg.partition.return_value = partition
    mock_msg.offset.return_value = offset
    return mock_msg


def _transaction_event_payload(**overrides):
    payload = {
        "transaction_id": "TXN-DRIFT-001",
        "portfolio_id": "P1",
        "instrument_id": "INS1",
        "security_id": "SEC1",
        "transaction_date": "2026-01-10T08:00:00Z",
        "transaction_type": "BUY",
        "quantity": "1",
        "price": "10",
        "gross_transaction_amount": "10",
        "trade_currency": "USD",
        "currency": "USD",
    }
    payload.update(overrides)
    return payload


def _transaction_validation_error(payload: dict) -> Exception:
    with pytest.raises(ValidationError) as exc_info:
        TransactionEvent.model_validate(payload)
    return exc_info.value


def _consumer_event_outcomes(metric_mock: MagicMock) -> list[tuple[str, str]]:
    return [(call.kwargs["outcome"], call.kwargs["reason"]) for call in metric_mock.call_args_list]


def _assert_standard_metric_labels(metric_mock: MagicMock) -> None:
    for metric_call in metric_mock.call_args_list:
        assert metric_call.kwargs["service"] == "SVC"
        assert metric_call.kwargs["topic"] == "test-topic"
        assert metric_call.kwargs["group_id"] == "test-group"


async def test_run_loop_success_path(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    """Tests the happy path: a message is polled, processed, and committed."""
    # ARRANGE
    mock_msg = create_mock_message("key1", {"data": "value1"})
    mock_confluent_consumer.poll.return_value = mock_msg

    async def stop_loop_after_processing(*args, **kwargs):
        test_consumer.shutdown()

    test_consumer.process_message_mock.side_effect = stop_loop_after_processing

    # ACT
    await test_consumer.run()

    # ASSERT
    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    mock_confluent_consumer.commit.assert_called_once_with(message=mock_msg, asynchronous=False)


async def test_run_loop_terminal_validation_log_uses_bounded_evidence(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
) -> None:
    marker = "SYNTHETIC_OUTER_VALIDATION_6R"
    invalid_payload = _transaction_event_payload(authorization=f"Bearer {marker}")
    validation_error = _transaction_validation_error(invalid_payload)
    mock_msg = create_mock_message("key-terminal-validation", invalid_payload)
    mock_confluent_consumer.poll.return_value = mock_msg
    test_consumer.process_message_mock.side_effect = validation_error

    async def publish_and_stop(*_args, **_kwargs) -> bool:
        test_consumer.shutdown()
        return True

    test_consumer._send_to_dlq_async = AsyncMock(side_effect=publish_and_stop)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingJsonFormatter())
    consumer_logger = logging.getLogger("portfolio_common.kafka_consumer")

    with (
        patch.object(consumer_logger, "handlers", [handler]),
        patch.object(consumer_logger, "propagate", False),
        patch.object(consumer_logger, "level", logging.ERROR),
    ):
        await test_consumer.run()

    emitted = stream.getvalue()
    assert marker not in emitted
    terminal_records = [
        json.loads(line)
        for line in emitted.splitlines()
        if json.loads(line).get("event_name") == "kafka.consumer.processing_terminal"
    ]
    assert len(terminal_records) == 1
    terminal_record = terminal_records[0]
    assert terminal_record["operation"] == "kafka.consume"
    assert terminal_record["topic"] == "test-topic"
    assert terminal_record["consumer_group"] == "test-group"
    assert terminal_record["reason_code"] == "validation_error"
    assert terminal_record["error_type"] == "ValidationError"
    assert terminal_record["validation_error_count"] == 1
    assert terminal_record["validation_error_locations"] == ["<dynamic>"]
    assert terminal_record["validation_error_types"] == ["extra_forbidden"]
    assert "exc_info" not in terminal_record
    assert "error_traceback" not in terminal_record
    test_consumer._send_to_dlq_async.assert_awaited_once_with(mock_msg, validation_error)


async def test_run_loop_uses_configured_poll_timeout(
    mock_confluent_consumer: MagicMock,
    mock_kafka_producer: MagicMock,
):
    timeouts = []
    mock_msg = create_mock_message("key-poll-timeout", {"data": "value"})

    def poll(timeout):
        timeouts.append(timeout)
        return None if len(timeouts) == 1 else mock_msg

    mock_confluent_consumer.poll.side_effect = poll

    consumer = ConcreteTestConsumer(
        bootstrap_servers="mock_bs",
        topic="test-topic",
        group_id="test-group",
        execution_profile=KafkaConsumerExecutionProfile(poll_timeout_seconds=0.25),
    )

    async def stop_loop_after_processing(*args, **kwargs):
        consumer.shutdown()

    consumer.process_message_mock.side_effect = stop_loop_after_processing

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=mock_confluent_consumer),
        patch(
            "portfolio_common.kafka_consumer.get_kafka_producer", return_value=mock_kafka_producer
        ),
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_poll_idle_duration"),
    ):
        await consumer.run()

    assert timeouts == [0.25, 0.25]
    mock_confluent_consumer.commit.assert_called_once_with(message=mock_msg, asynchronous=False)


async def test_shutdown_drains_active_message_before_closing_consumer(
    mock_confluent_consumer: MagicMock,
    mock_kafka_producer: MagicMock,
):
    mock_msg = create_mock_message("key-shutdown-drain", {"data": "value"})
    mock_confluent_consumer.poll.return_value = mock_msg
    processing_started = asyncio.Event()
    release_processing = asyncio.Event()

    consumer = ConcreteTestConsumer(
        bootstrap_servers="mock_bs",
        topic="test-topic",
        group_id="test-group",
    )

    async def process_message(_msg):
        processing_started.set()
        await release_processing.wait()

    consumer.process_message_mock.side_effect = process_message

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=mock_confluent_consumer),
        patch(
            "portfolio_common.kafka_consumer.get_kafka_producer",
            return_value=mock_kafka_producer,
        ),
    ):
        run_task = asyncio.create_task(consumer.run())
        await asyncio.wait_for(processing_started.wait(), timeout=1)

        consumer.shutdown()

        mock_confluent_consumer.close.assert_not_called()
        mock_confluent_consumer.commit.assert_not_called()

        release_processing.set()
        await asyncio.wait_for(run_task, timeout=1)

    mock_confluent_consumer.commit.assert_called_once_with(message=mock_msg, asynchronous=False)
    mock_confluent_consumer.close.assert_called_once_with()


async def test_concurrent_profile_does_not_commit_before_processing_completion(
    mock_confluent_consumer: MagicMock,
    mock_kafka_producer: MagicMock,
):
    msg_partition_0 = create_mock_message(
        "key-concurrent-0",
        {"data": "value-0"},
        partition=0,
        offset=1,
    )
    msg_partition_1 = create_mock_message(
        "key-concurrent-1",
        {"data": "value-1"},
        partition=1,
        offset=2,
    )
    mock_confluent_consumer.poll.side_effect = [msg_partition_0, msg_partition_1]
    both_started = asyncio.Event()
    release_processing = asyncio.Event()
    started_partitions = []
    completed_partitions = []

    consumer = ConcreteTestConsumer(
        bootstrap_servers="mock_bs",
        topic="test-topic",
        group_id="test-group",
        execution_profile=KafkaConsumerExecutionProfile(max_in_flight_messages=2),
    )

    async def process_message(msg):
        started_partitions.append(msg.partition())
        if len(started_partitions) == 2:
            both_started.set()
        await release_processing.wait()
        completed_partitions.append(msg.partition())
        if len(completed_partitions) == 2:
            consumer.shutdown()

    consumer.process_message_mock.side_effect = process_message

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=mock_confluent_consumer),
        patch(
            "portfolio_common.kafka_consumer.get_kafka_producer", return_value=mock_kafka_producer
        ),
        patch("portfolio_common.kafka_consumer.set_kafka_consumer_in_flight"),
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_backlog_pressure"),
    ):
        run_task = asyncio.create_task(consumer.run())
        await asyncio.wait_for(both_started.wait(), timeout=1)
        mock_confluent_consumer.commit.assert_not_called()
        release_processing.set()
        await run_task

    assert sorted(started_partitions) == [0, 1]
    assert sorted(completed_partitions) == [0, 1]
    assert mock_confluent_consumer.commit.call_count == 2


async def test_concurrent_profile_preserves_partition_order(
    mock_confluent_consumer: MagicMock,
    mock_kafka_producer: MagicMock,
):
    first_msg = create_mock_message(
        "key-same-partition-1",
        {"data": "value-1"},
        partition=0,
        offset=1,
    )
    second_msg = create_mock_message(
        "key-same-partition-2",
        {"data": "value-2"},
        partition=0,
        offset=2,
    )
    polled_messages = [first_msg, second_msg]
    poll_timeouts = []

    def poll(timeout):
        poll_timeouts.append(timeout)
        return polled_messages.pop(0) if polled_messages else None

    mock_confluent_consumer.poll.side_effect = poll
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release_first = asyncio.Event()
    processed_offsets = []

    consumer = ConcreteTestConsumer(
        bootstrap_servers="mock_bs",
        topic="test-topic",
        group_id="test-group",
        execution_profile=KafkaConsumerExecutionProfile(
            max_in_flight_messages=2,
            poll_timeout_seconds=1.0,
        ),
    )

    async def process_message(msg):
        if msg.offset() == 1:
            first_started.set()
            await release_first.wait()
        else:
            second_started.set()
            consumer.shutdown()
        processed_offsets.append(msg.offset())

    consumer.process_message_mock.side_effect = process_message

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=mock_confluent_consumer),
        patch(
            "portfolio_common.kafka_consumer.get_kafka_producer", return_value=mock_kafka_producer
        ),
        patch("portfolio_common.kafka_consumer.set_kafka_consumer_in_flight"),
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_backlog_pressure"),
    ):
        run_task = asyncio.create_task(consumer.run())
        await asyncio.wait_for(first_started.wait(), timeout=1)
        await asyncio.sleep(0)
        assert not second_started.is_set()
        mock_confluent_consumer.commit.assert_not_called()
        release_first.set()
        await asyncio.wait_for(second_started.wait(), timeout=1)
        await run_task

    assert processed_offsets == [1, 2]
    assert poll_timeouts[:2] == [1.0, 0.0]
    committed_messages = [
        call.kwargs["message"] for call in mock_confluent_consumer.commit.call_args_list
    ]
    assert committed_messages == [first_msg, second_msg]


async def test_busy_partition_does_not_starve_an_idle_partition(
    mock_confluent_consumer: MagicMock,
    mock_kafka_producer: MagicMock,
):
    first_busy_message = create_mock_message(
        "key-busy-1",
        {"data": "busy-1"},
        partition=0,
        offset=1,
    )
    second_busy_message = create_mock_message(
        "key-busy-2",
        {"data": "busy-2"},
        partition=0,
        offset=2,
    )
    idle_partition_message = create_mock_message(
        "key-idle-1",
        {"data": "idle-1"},
        partition=1,
        offset=1,
    )
    polled_messages = [
        first_busy_message,
        second_busy_message,
        idle_partition_message,
    ]

    def poll(_timeout):
        return polled_messages.pop(0) if polled_messages else None

    mock_confluent_consumer.poll.side_effect = poll
    first_busy_started = asyncio.Event()
    release_first_busy = asyncio.Event()
    second_busy_started = asyncio.Event()
    idle_partition_started = asyncio.Event()

    consumer = ConcreteTestConsumer(
        bootstrap_servers="mock_bs",
        topic="test-topic",
        group_id="test-group",
        execution_profile=KafkaConsumerExecutionProfile(
            max_in_flight_messages=2,
            poll_timeout_seconds=0.01,
        ),
    )

    async def process_message(msg):
        if msg is first_busy_message:
            first_busy_started.set()
            await release_first_busy.wait()
            return
        if msg is second_busy_message:
            second_busy_started.set()
            consumer.shutdown()
            return
        idle_partition_started.set()

    consumer.process_message_mock.side_effect = process_message

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=mock_confluent_consumer),
        patch(
            "portfolio_common.kafka_consumer.get_kafka_producer",
            return_value=mock_kafka_producer,
        ),
        patch("portfolio_common.kafka_consumer.set_kafka_consumer_in_flight"),
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_backlog_pressure"),
    ):
        run_task = asyncio.create_task(consumer.run())
        await asyncio.wait_for(first_busy_started.wait(), timeout=1)
        await asyncio.wait_for(idle_partition_started.wait(), timeout=1)
        assert not second_busy_started.is_set()

        release_first_busy.set()
        await asyncio.wait_for(second_busy_started.wait(), timeout=1)
        await asyncio.wait_for(run_task, timeout=1)

    assert mock_confluent_consumer.commit.call_count == 3
    mock_confluent_consumer.pause.assert_called_once()
    mock_confluent_consumer.resume.assert_called_once()


async def test_run_loop_failure_sends_to_dlq_and_commits(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    """Tests the failure path: a processing error triggers a DLQ publish and then commits the offset."""  # noqa: E501
    # ARRANGE
    mock_msg = create_mock_message("key2", {"data": "value2"})
    mock_confluent_consumer.poll.return_value = mock_msg

    async def fail_and_stop(*args, **kwargs):
        test_consumer.shutdown()
        raise ValueError("Processing failed!")

    test_consumer.process_message_mock.side_effect = fail_and_stop
    test_consumer._send_to_dlq_async = AsyncMock(return_value=True)

    # ACT
    await test_consumer.run()

    # ASSERT
    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    mock_confluent_consumer.commit.assert_called_once_with(message=mock_msg, asynchronous=False)
    test_consumer._send_to_dlq_async.assert_awaited_once()


async def test_run_loop_success_emits_standard_consumer_metrics(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_msg = create_mock_message("key-standard-success", {"data": "value-success"})
    mock_confluent_consumer.poll.return_value = mock_msg

    async def stop_loop_after_processing(*args, **kwargs):
        test_consumer.shutdown()

    test_consumer.process_message_mock.side_effect = stop_loop_after_processing

    with (
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric,
        patch(
            "portfolio_common.kafka_consumer.observe_kafka_consumer_processing_duration"
        ) as duration_metric,
    ):
        await test_consumer.run()

    assert ("processing_attempt", "message_polled") in _consumer_event_outcomes(event_metric)
    assert ("success", "processed") in _consumer_event_outcomes(event_metric)
    _assert_standard_metric_labels(event_metric)
    duration_metric.assert_called_once()
    assert duration_metric.call_args.kwargs == {
        "service": "SVC",
        "topic": "test-topic",
        "group_id": "test-group",
        "duration_seconds": ANY,
    }


async def test_successful_commit_observes_cached_partition_lag(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
):
    mock_msg = create_mock_message(
        "key-lag",
        {"data": "value"},
        partition=3,
        offset=4,
    )
    mock_confluent_consumer.poll.return_value = mock_msg
    mock_confluent_consumer.get_watermark_offsets.return_value = (0, 10)

    async def stop_loop_after_processing(*args, **kwargs):
        test_consumer.shutdown()

    test_consumer.process_message_mock.side_effect = stop_loop_after_processing

    with patch("portfolio_common.kafka_consumer.set_kafka_consumer_partition_lag") as lag_metric:
        await test_consumer.run()

    topic_partition = mock_confluent_consumer.get_watermark_offsets.call_args.args[0]
    assert topic_partition.topic == "test-topic"
    assert topic_partition.partition == 3
    assert mock_confluent_consumer.get_watermark_offsets.call_args.kwargs == {"cached": True}
    lag_metric.assert_called_once_with(
        service="SVC",
        topic="test-topic",
        group_id="test-group",
        partition="3",
        lag_messages=5,
    )


async def test_partition_lag_observation_failure_does_not_change_commit_outcome(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
):
    mock_msg = create_mock_message("key-lag-failure", {"data": "value"})
    mock_confluent_consumer.poll.return_value = mock_msg
    mock_confluent_consumer.get_watermark_offsets.return_value = (0, 10)

    async def stop_loop_after_processing(*args, **kwargs):
        test_consumer.shutdown()

    test_consumer.process_message_mock.side_effect = stop_loop_after_processing

    with patch(
        "portfolio_common.kafka_consumer.set_kafka_consumer_partition_lag",
        side_effect=RuntimeError("metrics unavailable"),
    ):
        await test_consumer.run()

    mock_confluent_consumer.commit.assert_called_once_with(message=mock_msg, asynchronous=False)


async def test_run_loop_failure_does_not_commit_when_dlq_send_fails(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_msg = create_mock_message("key2b", {"data": "value2b"})
    mock_confluent_consumer.poll.return_value = mock_msg

    async def fail_and_stop(*args, **kwargs):
        test_consumer.shutdown()
        raise ValueError("Processing failed!")

    test_consumer.process_message_mock.side_effect = fail_and_stop
    test_consumer._send_to_dlq_async = AsyncMock(return_value=False)

    with patch("portfolio_common.kafka_consumer.logger.warning") as mock_warning:
        await test_consumer.run()

    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    mock_confluent_consumer.commit.assert_not_called()
    test_consumer._send_to_dlq_async.assert_awaited_once()
    assert "DLQ publication failed" in mock_warning.call_args.args[0]
    assert (
        test_consumer._dlq_failure_attempts[
            "topic=test-topic|group=test-group|partition=0|offset=42|key=key2b"
        ]
        == 1
    )


async def test_run_loop_retries_dlq_publication_without_reprocessing_message(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
):
    mock_msg = create_mock_message("key-dlq-retry", {"data": "invalid"})
    mock_confluent_consumer.poll.return_value = mock_msg
    test_consumer.execution_profile = KafkaConsumerExecutionProfile(
        retryable_failure_backoff_seconds=0.001
    )
    test_consumer._dlq_failure_max_attempts = 2
    dlq_attempts = 0

    async def terminal_failure(*args, **kwargs):
        raise ValueError("invalid payload")

    async def publish_after_transient_failure(*args, **kwargs):
        nonlocal dlq_attempts
        dlq_attempts += 1
        if dlq_attempts == 1:
            return False
        test_consumer.shutdown()
        return True

    test_consumer.process_message_mock.side_effect = terminal_failure
    test_consumer._send_to_dlq_async = AsyncMock(side_effect=publish_after_transient_failure)

    await test_consumer.run()

    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    assert test_consumer._send_to_dlq_async.await_count == 2
    mock_confluent_consumer.commit.assert_called_once_with(
        message=mock_msg,
        asynchronous=False,
    )
    assert test_consumer._dlq_failure_attempts == {}


async def test_run_loop_retries_post_dlq_commit_without_republishing(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
):
    mock_msg = create_mock_message("key-dlq-commit-retry", {"data": "invalid"})
    mock_confluent_consumer.poll.return_value = mock_msg
    test_consumer.execution_profile = KafkaConsumerExecutionProfile(
        retryable_failure_backoff_seconds=0.001
    )
    test_consumer._dlq_failure_max_attempts = 2
    commit_attempts = 0

    async def terminal_failure(*args, **kwargs):
        raise ValueError("invalid payload")

    def commit_after_transient_failure(*args, **kwargs):
        nonlocal commit_attempts
        commit_attempts += 1
        if commit_attempts == 1:
            raise RuntimeError("coordinator unavailable")
        test_consumer.shutdown()
        message = kwargs["message"]
        return [TopicPartition(message.topic(), message.partition(), message.offset() + 1)]

    test_consumer.process_message_mock.side_effect = terminal_failure
    test_consumer._send_to_dlq_async = AsyncMock(return_value=True)
    mock_confluent_consumer.commit.side_effect = commit_after_transient_failure

    await test_consumer.run()

    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    test_consumer._send_to_dlq_async.assert_awaited_once_with(mock_msg, ANY)
    assert mock_confluent_consumer.commit.call_count == 2
    assert test_consumer._dlq_failure_attempts == {}


async def test_run_loop_disabled_dlq_budget_stops_after_one_publication_failure(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
) -> None:
    mock_msg = create_mock_message("key-dlq-disabled", {"data": "invalid"})
    mock_confluent_consumer.poll.return_value = mock_msg
    test_consumer._dlq_failure_max_attempts = 0
    test_consumer.process_message_mock.side_effect = ValueError("invalid payload")
    test_consumer._send_to_dlq_async = AsyncMock(return_value=False)

    with patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric:
        await asyncio.wait_for(test_consumer.run(), timeout=0.5)

    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    test_consumer._send_to_dlq_async.assert_awaited_once_with(mock_msg, ANY)
    mock_confluent_consumer.commit.assert_not_called()
    assert test_consumer._running is False
    assert (
        "dlq_recovery_stopped",
        "dlq_publish_error",
    ) in _consumer_event_outcomes(event_metric)


async def test_run_loop_disabled_dlq_budget_stops_after_one_offset_commit_failure(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
) -> None:
    mock_msg = create_mock_message("key-dlq-commit-disabled", {"data": "invalid"})
    mock_confluent_consumer.poll.return_value = mock_msg
    test_consumer._dlq_failure_max_attempts = 0
    test_consumer.process_message_mock.side_effect = ValueError("invalid payload")
    test_consumer._send_to_dlq_async = AsyncMock(return_value=True)
    mock_confluent_consumer.commit.side_effect = RuntimeError("coordinator unavailable")

    with patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric:
        await asyncio.wait_for(test_consumer.run(), timeout=0.5)

    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    test_consumer._send_to_dlq_async.assert_awaited_once_with(mock_msg, ANY)
    mock_confluent_consumer.commit.assert_called_once_with(
        message=mock_msg,
        asynchronous=False,
    )
    assert test_consumer._running is False
    assert (
        "dlq_recovery_stopped",
        "dlq_offset_commit_error",
    ) in _consumer_event_outcomes(event_metric)


async def test_run_loop_commits_confirmed_dlq_when_database_evidence_indexing_fails(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
    mock_kafka_producer: MagicMock,
) -> None:
    mock_msg = create_mock_message("key-evidence-failure", {"data": "invalid"})
    mock_confluent_consumer.poll.return_value = mock_msg

    async def fail_and_stop(*args, **kwargs):
        test_consumer.shutdown()
        raise ValueError("Processing failed!")

    test_consumer.process_message_mock.side_effect = fail_and_stop
    test_consumer._record_consumer_dlq_event = AsyncMock(
        side_effect=RuntimeError("support evidence unavailable")
    )

    with patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric:
        await test_consumer.run()

    mock_kafka_producer.publish_message.assert_called_once()
    mock_kafka_producer.flush.assert_any_call(timeout=5)
    test_consumer._record_consumer_dlq_event.assert_awaited_once()
    published_payload = mock_kafka_producer.publish_message.call_args.kwargs["value"]
    assert (
        test_consumer._record_consumer_dlq_event.await_args.kwargs["redacted_payload_text"]
        == published_payload["original_value"]
    )
    mock_confluent_consumer.commit.assert_called_once_with(
        message=mock_msg,
        asynchronous=False,
    )
    assert (
        "dlq_published",
        "database_evidence_indexing_failed",
    ) in _consumer_event_outcomes(event_metric)


async def test_run_loop_dlq_failure_budget_exhaustion_fails_fast_without_commit(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_msg = create_mock_message("key2c", {"data": "value2c"})
    mock_confluent_consumer.poll.return_value = mock_msg
    test_consumer._dlq_failure_max_attempts = 1

    async def fail_processing(*args, **kwargs):
        raise ValueError("Processing failed!")

    test_consumer.process_message_mock.side_effect = fail_processing
    test_consumer._send_to_dlq_async = AsyncMock(return_value=False)

    with (
        pytest.raises(DlqPublicationBudgetExhausted),
        patch("portfolio_common.kafka_consumer.logger.error") as mock_error,
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric,
    ):
        await test_consumer.run()

    mock_confluent_consumer.commit.assert_not_called()
    assert test_consumer._running is False
    assert (
        "dlq_failure_budget_exhausted",
        "dlq_publish_error",
    ) in _consumer_event_outcomes(event_metric)
    budget_log = [
        call
        for call in mock_error.call_args_list
        if call.kwargs["extra"]["event_name"] == "kafka.consumer.dlq_failure_budget_exhausted"
    ]
    assert len(budget_log) == 1
    log_extra = budget_log[0].kwargs["extra"]
    assert log_extra["reason_code"] == "dlq_publish_error_budget_exhausted"
    assert log_extra["failure_attempts"] == 1
    assert log_extra["max_failure_attempts"] == 1
    assert log_extra["original_topic"] == "test-topic"
    assert log_extra["original_partition"] == "0"
    assert log_extra["original_offset"] == "42"


async def test_run_loop_dlq_failure_budget_allows_transient_failure_before_exhaustion(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_msg = create_mock_message("key2d", {"data": "value2d"})
    mock_confluent_consumer.poll.return_value = mock_msg
    test_consumer._dlq_failure_max_attempts = 2

    async def fail_and_stop(*args, **kwargs):
        test_consumer.shutdown()
        raise ValueError("Processing failed!")

    test_consumer.process_message_mock.side_effect = fail_and_stop
    test_consumer._send_to_dlq_async = AsyncMock(return_value=False)

    await test_consumer.run()

    mock_confluent_consumer.commit.assert_not_called()
    assert (
        test_consumer._dlq_failure_attempts[
            "topic=test-topic|group=test-group|partition=0|offset=42|key=key2d"
        ]
        == 1
    )


async def test_run_loop_dlq_success_clears_prior_failure_attempts(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_msg = create_mock_message("key2e", {"data": "value2e"})
    mock_confluent_consumer.poll.return_value = mock_msg
    test_consumer._dlq_failure_attempts[
        "topic=test-topic|group=test-group|partition=0|offset=42|key=key2e"
    ] = 1

    async def fail_and_stop(*args, **kwargs):
        test_consumer.shutdown()
        raise ValueError("Processing failed!")

    test_consumer.process_message_mock.side_effect = fail_and_stop
    test_consumer._send_to_dlq_async = AsyncMock(return_value=True)

    await test_consumer.run()

    mock_confluent_consumer.commit.assert_called_once_with(message=mock_msg, asynchronous=False)
    assert test_consumer._dlq_failure_attempts == {}


async def test_run_loop_dlq_commit_failure_does_not_crash_or_re_dlq(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_msg = create_mock_message("key-dlq-commit", {"data": "value-dlq-commit"})
    mock_confluent_consumer.poll.return_value = mock_msg
    mock_confluent_consumer.commit.side_effect = RuntimeError("commit failed after dlq")

    async def fail_and_stop(*args, **kwargs):
        test_consumer.shutdown()
        raise ValueError("Processing failed!")

    test_consumer.process_message_mock.side_effect = fail_and_stop
    test_consumer._send_to_dlq_async = AsyncMock(return_value=True)

    with patch("portfolio_common.kafka_consumer.logger.warning") as mock_warning:
        await test_consumer.run()

    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    test_consumer._send_to_dlq_async.assert_awaited_once_with(mock_msg, ANY)
    mock_confluent_consumer.commit.assert_called_once_with(message=mock_msg, asynchronous=False)
    assert mock_warning.call_args.args[0] == "Kafka offset commit failed after DLQ publication."
    assert mock_warning.call_args.kwargs["extra"]["event_name"] == "kafka.consumer.commit_failed"
    assert mock_warning.call_args.kwargs["extra"]["reason_code"] == "dlq_publication"


async def test_run_loop_retryable_error_does_not_commit(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    """Tests the retryable path: a RetryableConsumerError prevents the offset from being committed."""  # noqa: E501
    # ARRANGE
    mock_msg = create_mock_message("key_retry", {"data": "value_retry"})
    mock_confluent_consumer.poll.return_value = mock_msg

    async def fail_and_stop(*args, **kwargs):
        test_consumer.shutdown()
        raise RetryableConsumerError("DB connection dropped!")

    test_consumer.process_message_mock.side_effect = fail_and_stop
    test_consumer._send_to_dlq_async = AsyncMock()

    # ACT
    await test_consumer.run()

    # ASSERT
    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    mock_confluent_consumer.commit.assert_not_called()
    test_consumer._send_to_dlq_async.assert_not_called()
    assert (
        test_consumer._retryable_failure_attempts[
            "topic=test-topic|group=test-group|partition=0|offset=42|key=key_retry"
        ][0]
        == 1
    )


async def test_default_disabled_retry_budget_returns_for_kafka_redelivery(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
):
    mock_msg = create_mock_message("key-retry-redelivery", {"data": "value-retry-redelivery"})
    test_consumer._running = True
    test_consumer.process_message_mock.side_effect = RetryableConsumerError(
        "dependency unavailable"
    )
    test_consumer._send_to_dlq_async = AsyncMock()

    with (
        patch("portfolio_common.kafka_consumer.asyncio.sleep", new_callable=AsyncMock) as sleep,
        patch("portfolio_common.kafka_consumer.logger.warning") as warning_log,
    ):
        await test_consumer._process_polled_message(mock_msg, asyncio.get_running_loop())

    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    sleep.assert_not_awaited()
    test_consumer._send_to_dlq_async.assert_not_awaited()
    mock_confluent_consumer.commit.assert_not_called()
    retry_log = next(
        call
        for call in warning_log.call_args_list
        if call.kwargs["extra"]["event_name"] == "kafka.consumer.processing_retryable"
    )
    assert retry_log.kwargs["extra"]["retry_disposition"] == (
        "kafka_redelivery_after_restart_or_rebalance"
    )
    assert retry_log.kwargs["extra"]["consumer_action"] == ("stop_before_polling_later_offsets")
    assert test_consumer._running is False
    assert (
        test_consumer._retryable_failure_attempts[
            "topic=test-topic|group=test-group|partition=0|offset=42|key=key-retry-redelivery"
        ][0]
        == 1
    )


async def test_default_disabled_retry_budget_stops_serial_loop_before_later_offset(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
):
    failed_msg = create_mock_message(
        "key-retry-serial-failed",
        {"data": "failed"},
        partition=0,
        offset=41,
    )
    later_msg = create_mock_message(
        "key-retry-serial-later",
        {"data": "later"},
        partition=0,
        offset=42,
    )
    polled_messages = [failed_msg, later_msg]

    def poll(_timeout):
        return polled_messages.pop(0) if polled_messages else None

    mock_confluent_consumer.poll.side_effect = poll

    async def fail_first_then_stop(msg):
        if msg is failed_msg:
            raise RetryableConsumerError("dependency unavailable")
        test_consumer.shutdown()

    test_consumer.process_message_mock.side_effect = fail_first_then_stop
    test_consumer._send_to_dlq_async = AsyncMock()

    await asyncio.wait_for(test_consumer.run(), timeout=1)

    assert test_consumer.process_message_mock.await_args_list == [call(failed_msg)]
    assert mock_confluent_consumer.poll.call_count == 1
    mock_confluent_consumer.commit.assert_not_called()
    test_consumer._send_to_dlq_async.assert_not_awaited()
    mock_confluent_consumer.close.assert_called_once_with()


async def test_default_disabled_retry_budget_discards_queued_same_partition_offset(
    mock_confluent_consumer: MagicMock,
    mock_kafka_producer: MagicMock,
):
    failed_msg = create_mock_message(
        "key-retry-concurrent-failed",
        {"data": "failed"},
        partition=0,
        offset=41,
    )
    later_msg = create_mock_message(
        "key-retry-concurrent-later",
        {"data": "later"},
        partition=0,
        offset=42,
    )
    polled_messages = [failed_msg, later_msg]
    later_message_queued = asyncio.Event()

    def poll(_timeout):
        if not polled_messages:
            return None
        msg = polled_messages.pop(0)
        return msg

    mock_confluent_consumer.poll.side_effect = poll
    consumer = ConcreteTestConsumer(
        bootstrap_servers="mock_bs",
        topic="test-topic",
        group_id="test-group",
        execution_profile=KafkaConsumerExecutionProfile(
            max_in_flight_messages=2,
            poll_timeout_seconds=0.01,
        ),
    )

    dispatch_or_queue = consumer._dispatch_or_queue_message

    async def queue_then_signal(msg, loop):
        await dispatch_or_queue(msg, loop)
        if msg is later_msg:
            later_message_queued.set()

    async def fail_first_then_stop(msg):
        if msg is failed_msg:
            await later_message_queued.wait()
            raise RetryableConsumerError("dependency unavailable")
        consumer.shutdown()

    consumer._dispatch_or_queue_message = AsyncMock(side_effect=queue_then_signal)
    consumer.process_message_mock.side_effect = fail_first_then_stop
    consumer._send_to_dlq_async = AsyncMock()

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=mock_confluent_consumer),
        patch(
            "portfolio_common.kafka_consumer.get_kafka_producer",
            return_value=mock_kafka_producer,
        ),
        patch("portfolio_common.kafka_consumer.set_kafka_consumer_in_flight"),
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_backlog_pressure"),
    ):
        await asyncio.wait_for(consumer.run(), timeout=1)

    assert consumer.process_message_mock.await_args_list == [call(failed_msg)]
    mock_confluent_consumer.commit.assert_not_called()
    consumer._send_to_dlq_async.assert_not_awaited()
    mock_confluent_consumer.pause.assert_called_once()
    mock_confluent_consumer.resume.assert_called_once()
    assert consumer._pending_message_count == 0
    assert consumer._pending_messages_by_key == {}


async def test_run_loop_retries_transient_failure_in_process_then_commits(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
):
    mock_msg = create_mock_message("key-retry-success", {"data": "value-retry-success"})
    mock_confluent_consumer.poll.return_value = mock_msg
    test_consumer.execution_profile = KafkaConsumerExecutionProfile(
        retryable_failure_backoff_seconds=0.001
    )
    test_consumer._retryable_failure_max_attempts = 3
    processing_attempts = 0

    async def fail_once_then_succeed(*args, **kwargs):
        nonlocal processing_attempts
        processing_attempts += 1
        if processing_attempts == 1:
            raise RetryableConsumerError("cost_dependency_unavailable")
        test_consumer.shutdown()

    test_consumer.process_message_mock.side_effect = fail_once_then_succeed

    with patch("portfolio_common.kafka_consumer.logger.warning") as warning_log:
        await test_consumer.run()

    assert processing_attempts == 2
    assert test_consumer.process_message_mock.await_args_list == [call(mock_msg), call(mock_msg)]
    mock_confluent_consumer.commit.assert_called_once_with(
        message=mock_msg,
        asynchronous=False,
    )
    assert test_consumer._retryable_failure_attempts == {}
    retry_log = next(
        call
        for call in warning_log.call_args_list
        if call.kwargs["extra"]["event_name"] == "kafka.consumer.processing_retryable"
    )
    assert retry_log.kwargs["extra"]["retryable_error_reason"] == ("cost_dependency_unavailable")
    assert retry_log.kwargs["extra"]["failure_attempts"] == 1
    assert retry_log.kwargs["extra"]["retry_backoff_seconds"] == 0.001


async def test_concurrent_profile_retries_before_next_partition_message(
    mock_confluent_consumer: MagicMock,
    mock_kafka_producer: MagicMock,
):
    first_msg = create_mock_message(
        "key-retry-ordered-1",
        {"data": "value-1"},
        partition=0,
        offset=1,
    )
    second_msg = create_mock_message(
        "key-retry-ordered-2",
        {"data": "value-2"},
        partition=0,
        offset=2,
    )
    polled_messages = [first_msg, second_msg]

    def poll(_timeout):
        return polled_messages.pop(0) if polled_messages else None

    mock_confluent_consumer.poll.side_effect = poll
    processing_attempts = []
    first_message_attempts = 0

    consumer = ConcreteTestConsumer(
        bootstrap_servers="mock_bs",
        topic="test-topic",
        group_id="test-group",
        execution_profile=KafkaConsumerExecutionProfile(
            max_in_flight_messages=2,
            poll_timeout_seconds=0.01,
            retryable_failure_backoff_seconds=0.01,
        ),
    )
    consumer._retryable_failure_max_attempts = 3

    async def process_message(msg):
        nonlocal first_message_attempts
        processing_attempts.append(msg.offset())
        if msg is first_msg:
            first_message_attempts += 1
            if first_message_attempts == 1:
                raise RetryableConsumerError("dependency race")
            return
        consumer.shutdown()

    consumer.process_message_mock.side_effect = process_message

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=mock_confluent_consumer),
        patch(
            "portfolio_common.kafka_consumer.get_kafka_producer",
            return_value=mock_kafka_producer,
        ),
        patch("portfolio_common.kafka_consumer.set_kafka_consumer_in_flight"),
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_backlog_pressure"),
    ):
        await asyncio.wait_for(consumer.run(), timeout=1)

    assert processing_attempts == [1, 1, 2]
    committed_messages = [
        call.kwargs["message"] for call in mock_confluent_consumer.commit.call_args_list
    ]
    assert committed_messages == [first_msg, second_msg]
    mock_confluent_consumer.pause.assert_called_once()
    mock_confluent_consumer.resume.assert_called_once()


async def test_run_loop_retryable_max_attempts_exhaustion_sends_to_dlq_and_commits(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_msg = create_mock_message("key-retry-exhausted", {"data": "value-retry-exhausted"})
    mock_confluent_consumer.poll.return_value = mock_msg
    test_consumer._retryable_failure_max_attempts = 1

    async def retryable_failure(*args, **kwargs):
        test_consumer.shutdown()
        raise RetryableConsumerError("DB connection dropped!")

    test_consumer.process_message_mock.side_effect = retryable_failure
    test_consumer._send_to_dlq_async = AsyncMock(return_value=True)

    with (
        patch("portfolio_common.kafka_consumer.logger.error") as mock_error,
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric,
    ):
        await test_consumer.run()

    test_consumer._send_to_dlq_async.assert_awaited_once_with(mock_msg, ANY)
    mock_confluent_consumer.commit.assert_called_once_with(message=mock_msg, asynchronous=False)
    assert test_consumer._retryable_failure_attempts == {}
    assert (
        "retryable_exhausted",
        "retryable_budget_exhausted",
    ) in _consumer_event_outcomes(event_metric)
    exhausted_logs = [
        call
        for call in mock_error.call_args_list
        if call.kwargs["extra"]["event_name"] == "kafka.consumer.retryable_failure_budget_exhausted"
    ]
    assert len(exhausted_logs) == 1
    log_extra = exhausted_logs[0].kwargs["extra"]
    assert log_extra["reason_code"] == "retryable_budget_exhausted"
    assert log_extra["failure_attempts"] == 1
    assert log_extra["max_failure_attempts"] == 1


async def test_run_loop_retryable_elapsed_budget_exhaustion_sends_to_dlq(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_msg = create_mock_message("key-retry-elapsed", {"data": "value-retry-elapsed"})
    mock_confluent_consumer.poll.return_value = mock_msg
    test_consumer._retryable_failure_max_elapsed_seconds = 5
    test_consumer._retryable_failure_attempts[
        "topic=test-topic|group=test-group|partition=0|offset=42|key=key-retry-elapsed"
    ] = (2, 0.0)

    async def retryable_failure(*args, **kwargs):
        test_consumer.shutdown()
        raise RetryableConsumerError("dependency still unavailable")

    test_consumer.process_message_mock.side_effect = retryable_failure
    test_consumer._send_to_dlq_async = AsyncMock(return_value=True)

    await test_consumer.run()

    test_consumer._send_to_dlq_async.assert_awaited_once_with(mock_msg, ANY)
    mock_confluent_consumer.commit.assert_called_once_with(message=mock_msg, asynchronous=False)


async def test_consumer_accepts_explicit_service_owned_retryable_failure_budget() -> None:
    consumer = ConcreteTestConsumer(
        bootstrap_servers="mock_bs",
        topic="test-topic",
        group_id="test-group",
        retryable_failure_max_attempts=7,
        retryable_failure_max_elapsed_seconds=30,
    )

    assert consumer._retryable_failure_max_attempts == 7
    assert consumer._retryable_failure_max_elapsed_seconds == 30


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("retryable_failure_max_attempts", {"retryable_failure_max_attempts": -1}),
        (
            "retryable_failure_max_elapsed_seconds",
            {"retryable_failure_max_elapsed_seconds": -1},
        ),
    ],
)
async def test_consumer_rejects_negative_service_owned_retryable_failure_budget(
    field_name: str,
    kwargs: dict[str, int],
) -> None:
    with pytest.raises(ValueError, match=field_name):
        ConcreteTestConsumer(
            bootstrap_servers="mock_bs",
            topic="test-topic",
            group_id="test-group",
            **kwargs,
        )


async def test_run_loop_retryable_error_emits_standard_consumer_metrics(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_msg = create_mock_message("key-retry-metrics", {"data": "value-retry-metrics"})
    mock_confluent_consumer.poll.return_value = mock_msg

    async def fail_and_stop(*args, **kwargs):
        test_consumer.shutdown()
        raise RetryableConsumerError("DB connection dropped!")

    test_consumer.process_message_mock.side_effect = fail_and_stop

    with (
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric,
        patch(
            "portfolio_common.kafka_consumer.observe_kafka_consumer_processing_duration"
        ) as duration_metric,
    ):
        await test_consumer.run()

    assert ("processing_attempt", "message_polled") in _consumer_event_outcomes(event_metric)
    assert ("retryable_failure", "retryable_consumer_error") in _consumer_event_outcomes(
        event_metric
    )
    _assert_standard_metric_labels(event_metric)
    duration_metric.assert_called_once()


async def test_run_loop_commit_failure_does_not_send_to_dlq(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_msg = create_mock_message("key-commit", {"data": "value-commit"})
    mock_confluent_consumer.poll.return_value = mock_msg
    mock_confluent_consumer.commit.side_effect = RuntimeError("commit failed")
    test_consumer._send_to_dlq_async = AsyncMock()

    async def process_and_stop(*args, **kwargs):
        test_consumer.shutdown()

    test_consumer.process_message_mock.side_effect = process_and_stop

    with patch("portfolio_common.kafka_consumer.logger.warning") as mock_warning:
        await test_consumer.run()

    test_consumer.process_message_mock.assert_awaited_once_with(mock_msg)
    mock_confluent_consumer.commit.assert_called_once_with(message=mock_msg, asynchronous=False)
    test_consumer._send_to_dlq_async.assert_not_awaited()
    assert mock_warning.call_args.args[0] == (
        "Kafka offset commit failed after successful processing."
    )
    assert mock_warning.call_args.kwargs["extra"]["event_name"] == "kafka.consumer.commit_failed"
    assert mock_warning.call_args.kwargs["extra"]["reason_code"] == "successful_processing"


async def test_run_loop_commit_failure_emits_standard_consumer_metric(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_msg = create_mock_message("key-commit-metrics", {"data": "value-commit-metrics"})
    mock_confluent_consumer.poll.return_value = mock_msg
    mock_confluent_consumer.commit.side_effect = RuntimeError("commit failed")

    async def process_and_stop(*args, **kwargs):
        test_consumer.shutdown()

    test_consumer.process_message_mock.side_effect = process_and_stop

    with (
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric,
        patch("portfolio_common.kafka_consumer.logger.warning"),
    ):
        await test_consumer.run()

    assert ("commit_failed", "successful_processing") in _consumer_event_outcomes(event_metric)
    assert ("commit_failed", "redelivery_required") in _consumer_event_outcomes(event_metric)
    _assert_standard_metric_labels(event_metric)


async def test_run_loop_fatal_consumer_error_stops_without_processing(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_error = MagicMock()
    mock_error.fatal.return_value = True
    mock_msg = create_mock_message("key-fatal", {"data": "value-fatal"}, error=mock_error)
    mock_confluent_consumer.poll.return_value = mock_msg

    with patch("portfolio_common.kafka_consumer.logger.error") as mock_log_error:
        await test_consumer.run()

    test_consumer.process_message_mock.assert_not_awaited()
    mock_confluent_consumer.commit.assert_not_called()
    assert mock_log_error.call_args.args[0] == (
        "Kafka consumer poll error was fatal; shutting down."
    )
    assert mock_log_error.call_args.kwargs["extra"]["event_name"] == "kafka.consumer.poll_error"
    assert mock_log_error.call_args.kwargs["extra"]["reason_code"] == "fatal_poll_error"


async def test_run_loop_nonfatal_consumer_error_skips_message(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    mock_error = MagicMock()
    mock_error.fatal.return_value = False
    error_msg = create_mock_message("key-warning", {"data": "value-warning"}, error=mock_error)
    valid_msg = create_mock_message("key-after-warning", {"data": "value-after-warning"})
    mock_confluent_consumer.poll.side_effect = [error_msg, valid_msg]

    async def stop_loop_after_processing(*args, **kwargs):
        test_consumer.shutdown()

    test_consumer.process_message_mock.side_effect = stop_loop_after_processing

    with patch("portfolio_common.kafka_consumer.logger.warning") as mock_warning:
        await test_consumer.run()

    test_consumer.process_message_mock.assert_awaited_once_with(valid_msg)
    mock_confluent_consumer.commit.assert_called_once_with(message=valid_msg, asynchronous=False)
    warning_events = [call.kwargs["extra"]["event_name"] for call in mock_warning.call_args_list]
    assert "kafka.consumer.poll_error" in warning_events


async def test_run_loop_poll_errors_emit_standard_consumer_metrics(
    test_consumer: ConcreteTestConsumer, mock_confluent_consumer: MagicMock
):
    fatal_error = MagicMock()
    fatal_error.fatal.return_value = True
    fatal_msg = create_mock_message("key-fatal-metric", {"data": "value"}, error=fatal_error)
    mock_confluent_consumer.poll.return_value = fatal_msg

    with (
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric,
        patch("portfolio_common.kafka_consumer.logger.error"),
    ):
        await test_consumer.run()

    assert ("poll_error", "fatal") in _consumer_event_outcomes(event_metric)
    _assert_standard_metric_labels(event_metric)


async def test_dlq_payload_is_correct(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    """Tests that the DLQ payload is formatted correctly."""
    # ARRANGE
    mock_msg = create_mock_message(
        "key3", {"data": "value3"}, headers=[("correlation_id", b"corr-123")]
    )
    error = ValueError("Test Error")
    correlation_id = "corr-123"
    test_consumer._record_consumer_dlq_event = AsyncMock()

    # ACT
    # Set the context variable to simulate the state within the consumer's run loop
    token = correlation_id_var.set(correlation_id)
    try:
        # Simulate the try/except block that the run loop provides
        try:
            raise error
        except ValueError as e:
            result = await test_consumer._send_to_dlq_async(mock_msg, e)
    finally:
        correlation_id_var.reset(token)

    # ASSERT
    assert result is True
    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs

    assert call_args["topic"] == "test.dlq"
    assert call_args["key"] == "key3"

    payload = call_args["value"]
    assert payload["original_topic"] == "test-topic"
    assert payload["original_key"] == "key3"
    assert payload["original_value"] == '{"data": "value3"}'
    assert payload["error_reason_code"] == "VALIDATION_ERROR"
    assert "Test Error" in payload["error_reason"]
    assert "Traceback" in payload["error_traceback"]

    headers_dict = dict(call_args["headers"])
    assert headers_dict["correlation_id"] == correlation_id.encode("utf-8")
    test_consumer._record_consumer_dlq_event.assert_awaited_once()


async def test_dlq_unknown_ingestion_owner_preserves_publish_success_without_republication(
    test_consumer: ConcreteTestConsumer,
    mock_kafka_producer: MagicMock,
) -> None:
    mock_msg = create_mock_message(
        "key-unknown-owner",
        {"data": "value"},
        headers=[("ingestion_job_id", b"job-stale")],
    )
    test_consumer._record_consumer_dlq_event = AsyncMock()
    test_consumer._resolve_consumer_dlq_tenant_id = AsyncMock(
        side_effect=ConsumerDlqTenantAttributionError("unknown owner")
    )

    token = ingestion_job_id_var.set("job-stale")
    try:
        with (
            patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric,
            patch("portfolio_common.kafka_consumer.logger.warning") as warning_log,
        ):
            published = await test_consumer._send_to_dlq_async(
                mock_msg,
                ValueError("invalid payload"),
            )
    finally:
        ingestion_job_id_var.reset(token)

    assert published is True
    payload = mock_kafka_producer.publish_message.call_args.kwargs["value"]
    headers = dict(mock_kafka_producer.publish_message.call_args.kwargs["headers"])
    assert payload["ingestion_job_id"] == "job-stale"
    assert headers["ingestion_job_id"] == b"job-stale"
    mock_kafka_producer.publish_message.assert_called_once()
    test_consumer._record_consumer_dlq_event.assert_not_awaited()
    assert (
        "dlq_published",
        "database_evidence_tenant_unavailable",
    ) in _consumer_event_outcomes(event_metric)
    assert warning_log.call_args.kwargs["extra"]["status"] == "degraded"
    assert (
        warning_log.call_args.kwargs["extra"]["reason_code"]
        == "database_evidence_tenant_unavailable"
    )


async def test_dlq_database_indexing_failure_preserves_publish_success_without_republication(
    test_consumer: ConcreteTestConsumer,
    mock_kafka_producer: MagicMock,
) -> None:
    mock_msg = create_mock_message("key-indexing-failure", {"data": "value"})
    test_consumer._record_consumer_dlq_event = AsyncMock(
        side_effect=RuntimeError("database unavailable")
    )

    with (
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric,
        patch("portfolio_common.kafka_consumer.logger.error") as error_log,
    ):
        published = await test_consumer._send_to_dlq_async(
            mock_msg,
            ValueError("invalid payload"),
        )

    assert published is True
    mock_kafka_producer.publish_message.assert_called_once()
    test_consumer._record_consumer_dlq_event.assert_awaited_once()
    assert (
        "dlq_published",
        "database_evidence_indexing_failed",
    ) in _consumer_event_outcomes(event_metric)
    assert error_log.call_args.kwargs["extra"]["status"] == "degraded"
    assert error_log.call_args.kwargs["extra"]["reason_code"] == "database_evidence_indexing_failed"


async def test_dlq_payload_preserves_bounded_application_reason_code(
    test_consumer: ConcreteTestConsumer,
    mock_kafka_producer: MagicMock,
) -> None:
    error = ValueError("settlement cash rejected")
    error.reason_code = "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT"  # type: ignore[attr-defined]
    mock_msg = create_mock_message("key-domain-rejection", {"data": "value"})
    test_consumer._record_consumer_dlq_event = AsyncMock()

    result = await test_consumer._send_to_dlq_async(mock_msg, error)

    assert result is True
    payload = mock_kafka_producer.publish_message.call_args.kwargs["value"]
    assert payload["error_reason_code"] == "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT"
    assert (
        test_consumer._record_consumer_dlq_event.await_args.kwargs["error_reason_code"]
        == "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT"
    )


async def test_dlq_payload_and_headers_preserve_traceparent(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    mock_msg = create_mock_message(
        "key-trace",
        {"data": "value-trace"},
        headers=[("correlation_id", b"corr-trace"), ("traceparent", TRACEPARENT.encode("utf-8"))],
    )
    test_consumer._record_consumer_dlq_event = AsyncMock()

    result = await test_consumer._send_to_dlq_async(mock_msg, ValueError("Test Error"))

    assert result is True
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert call_args["value"]["traceparent"] == TRACEPARENT
    assert dict(call_args["headers"])["traceparent"] == TRACEPARENT.encode("utf-8")


async def test_dlq_payload_treats_invalid_traceparent_bytes_as_absent(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    mock_msg = create_mock_message(
        "key-invalid-trace",
        {"data": "value-invalid-trace"},
        headers=[("correlation_id", b"corr-trace"), ("traceparent", b"\xff\xfe")],
    )
    test_consumer._record_consumer_dlq_event = AsyncMock()

    result = await test_consumer._send_to_dlq_async(mock_msg, ValueError("Test Error"))

    assert result is True
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert call_args["value"]["traceparent"] is None
    assert "traceparent" not in dict(call_args["headers"])


async def test_dlq_publish_uses_bytes_safe_key_text(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    mock_msg = create_mock_message(b"\xff\xfe", {"data": "value-binary-key"})
    test_consumer._record_consumer_dlq_event = AsyncMock()

    result = await test_consumer._send_to_dlq_async(mock_msg, ValueError("Test Error"))

    assert result is True
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert call_args["key"] == "hex:fffe"
    assert call_args["value"]["original_key"] == "hex:fffe"


async def test_failure_budget_key_uses_bytes_safe_key_text(
    test_consumer: ConcreteTestConsumer,
):
    mock_msg = create_mock_message(b"\xff\xfe", {"data": "value-binary-key"})

    assert test_consumer._failure_message_key(mock_msg) == (
        "topic=test-topic|group=test-group|partition=0|offset=42|key=hex:fffe"
    )


async def test_dlq_success_emits_standard_consumer_metric(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    mock_msg = create_mock_message("key-dlq-metrics", {"data": "value"})
    test_consumer._record_consumer_dlq_event = AsyncMock()

    with patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric:
        result = await test_consumer._send_to_dlq_async(
            mock_msg,
            ValueError("validation failed"),
        )

    assert result is True
    assert ("dlq_published", "VALIDATION_ERROR") in _consumer_event_outcomes(event_metric)
    _assert_standard_metric_labels(event_metric)


async def test_dlq_payload_and_headers_are_redacted(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    mock_msg = create_mock_message(
        "key-sensitive",
        {
            "portfolio_id": "P1",
            "authorization": "Bearer payload-token",
            "nested": {"database_url": "postgresql://user:password@localhost/db"},
        },
        headers=[
            ("authorization", b"Bearer header-token"),
            ("source", b"postgresql://user:password@localhost/db"),
            ("optional-header", None),
        ],
    )
    test_consumer._record_consumer_dlq_event = AsyncMock()

    result = await test_consumer._send_to_dlq_async(
        mock_msg,
        ValueError("token=error-token database_url=postgresql://u:p@localhost/db"),
    )

    assert result is True
    payload = mock_kafka_producer.publish_message.call_args.kwargs["value"]
    assert "payload-token" not in payload["original_value"]
    assert "password" not in payload["original_value"]
    assert json.loads(payload["original_value"]) == {
        "authorization": "***REDACTED***",
        "nested": {"database_url": "***REDACTED***"},
        "portfolio_id": "P1",
    }
    assert payload["error_reason"] == "token=***REDACTED***"
    assert "error-token" not in payload["error_reason"]
    assert "postgresql://u:p@localhost/db" not in payload["error_reason"]

    headers_dict = dict(mock_kafka_producer.publish_message.call_args.kwargs["headers"])
    assert headers_dict["authorization"] == b"***REDACTED***"
    assert headers_dict["source"] == b"postgresql://***REDACTED***@localhost/db"
    assert headers_dict["optional-header"] == b""


async def test_dlq_validation_error_reason_omits_rejected_input_value(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    payload = _transaction_event_payload(authorization="Bearer event-drift-token")
    mock_msg = create_mock_message(
        "key-validation-drift",
        payload,
        headers=[("correlation_id", b"corr-validation-drift")],
    )
    test_consumer._record_consumer_dlq_event = AsyncMock()

    result = await test_consumer._send_to_dlq_async(
        mock_msg,
        _transaction_validation_error(payload),
    )

    assert result is True
    dlq_payload = mock_kafka_producer.publish_message.call_args.kwargs["value"]
    assert dlq_payload["error_reason_code"] == "VALIDATION_ERROR"
    assert '"validation_error_locations":["<dynamic>"]' in dlq_payload["error_reason"]
    assert "authorization" not in dlq_payload["error_reason"]
    assert "event-drift-token" not in dlq_payload["error_reason"]
    assert "event-drift-token" not in dlq_payload["error_traceback"]
    assert "input_value" not in dlq_payload["error_reason"]
    assert json.loads(dlq_payload["original_value"])["authorization"] == "***REDACTED***"


async def test_dlq_omits_unset_correlation_header(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    mock_msg = create_mock_message("key4", {"data": "value4"})
    error = ValueError("Test Error")
    test_consumer._record_consumer_dlq_event = AsyncMock()

    token = correlation_id_var.set("<not-set>")
    try:
        try:
            raise error
        except ValueError as exc:
            result = await test_consumer._send_to_dlq_async(mock_msg, exc)
    finally:
        correlation_id_var.reset(token)

    assert result is True
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert "correlation_id" not in dict(call_args["headers"])
    assert call_args["value"]["correlation_id"] is None
    test_consumer._record_consumer_dlq_event.assert_awaited_once()


async def test_dlq_persistence_uses_original_missing_header_state(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    mock_msg = create_mock_message("key-generated", {"data": "value-generated"})
    test_consumer._record_consumer_dlq_event = AsyncMock()

    token = correlation_id_var.set("SVC:generated-correlation")
    try:
        result = await test_consumer._send_to_dlq_async(mock_msg, ValueError("Test Error"))
    finally:
        correlation_id_var.reset(token)

    assert result is True
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert dict(call_args["headers"])["correlation_id"] == b"SVC:generated-correlation"
    assert call_args["value"]["correlation_id"] == "SVC:generated-correlation"
    test_consumer._record_consumer_dlq_event.assert_awaited_once()
    assert test_consumer._record_consumer_dlq_event.await_args.kwargs["correlation_id"] is None


async def test_record_consumer_dlq_event_redacts_payload_excerpt(
    test_consumer: ConcreteTestConsumer,
):
    mock_msg = create_mock_message(
        "key-persisted",
        {"authorization": "Bearer persisted-token", "safe": "visible"},
    )
    mock_db = MagicMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=None)
    added_events = []

    async def get_session_gen():
        yield mock_db

    mock_db.begin.return_value = transaction
    mock_db.add.side_effect = added_events.append

    with patch("portfolio_common.kafka_consumer.get_async_db_session", new=get_session_gen):
        await test_consumer._record_consumer_dlq_event(
            tenant_id="tenant-test",
            msg=mock_msg,
            error=ValueError("token=event-token"),
            error_reason_code="VALIDATION_ERROR",
            correlation_id="corr-redacted",
            redacted_payload_text=test_consumer._redacted_message_value_text(mock_msg),
        )

    assert len(added_events) == 1
    assert added_events[0].error_reason == "token=***REDACTED***"
    assert "event-token" not in added_events[0].error_reason
    assert "persisted-token" not in added_events[0].payload_excerpt
    assert json.loads(added_events[0].payload_excerpt) == {
        "authorization": "***REDACTED***",
        "safe": "visible",
    }


async def test_record_consumer_dlq_event_persists_durable_ingestion_job_owner(
    test_consumer: ConcreteTestConsumer,
):
    mock_msg = create_mock_message("key-owned", {"safe": "visible"})
    mock_db = MagicMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=None)
    added_events = []

    async def get_session_gen():
        yield mock_db

    mock_db.begin.return_value = transaction
    mock_db.add.side_effect = added_events.append

    with patch("portfolio_common.kafka_consumer.get_async_db_session", new=get_session_gen):
        await test_consumer._record_consumer_dlq_event(
            tenant_id="tenant-test",
            msg=mock_msg,
            error=ValueError("persistence timeout"),
            error_reason_code="PERSISTENCE_TIMEOUT",
            correlation_id="corr-owned",
            redacted_payload_text=test_consumer._redacted_message_value_text(mock_msg),
            ingestion_job_id="job-owned",
        )

    assert added_events[0].ingestion_job_id == "job-owned"


async def test_record_consumer_dlq_event_persists_missing_correlation_diagnostics(
    test_consumer: ConcreteTestConsumer,
):
    mock_msg = create_mock_message(
        None,
        {"safe": "visible"},
        topic="transactions.raw.received",
        partition=3,
        offset=9001,
    )
    mock_db = MagicMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=None)
    added_events = []

    async def get_session_gen():
        yield mock_db

    mock_db.begin.return_value = transaction
    mock_db.add.side_effect = added_events.append

    with patch("portfolio_common.kafka_consumer.get_async_db_session", new=get_session_gen):
        await test_consumer._record_consumer_dlq_event(
            tenant_id="tenant-test",
            msg=mock_msg,
            error=ValueError("missing portfolio_id"),
            error_reason_code="VALIDATION_ERROR",
            correlation_id=None,
            redacted_payload_text=test_consumer._redacted_message_value_text(mock_msg),
        )

    assert len(added_events) == 1
    assert added_events[0].correlation_id is None
    assert added_events[0].correlation_missing_reason == "message_correlation_id_absent"
    assert added_events[0].alternate_lookup_key == (
        "consumer_dlq|topic=transactions.raw.received|group=test-group|"
        "dlq=test.dlq|partition=3|offset=9001|key=unkeyed"
    )


async def test_record_consumer_dlq_event_uses_source_safe_validation_reason(
    test_consumer: ConcreteTestConsumer,
):
    payload = _transaction_event_payload(authorization="Bearer persisted-validation-token")
    mock_msg = create_mock_message("key-validation-persisted", payload)
    mock_db = MagicMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=None)
    added_events = []

    async def get_session_gen():
        yield mock_db

    mock_db.begin.return_value = transaction
    mock_db.add.side_effect = added_events.append

    with patch("portfolio_common.kafka_consumer.get_async_db_session", new=get_session_gen):
        await test_consumer._record_consumer_dlq_event(
            tenant_id="tenant-test",
            msg=mock_msg,
            error=_transaction_validation_error(payload),
            error_reason_code="VALIDATION_ERROR",
            correlation_id="corr-validation-persisted",
            redacted_payload_text=test_consumer._redacted_message_value_text(mock_msg),
        )

    assert len(added_events) == 1
    assert '"validation_error_locations":["<dynamic>"]' in added_events[0].error_reason
    assert "authorization" not in added_events[0].error_reason
    assert "persisted-validation-token" not in added_events[0].error_reason
    assert "input_value" not in added_events[0].error_reason
    assert "persisted-validation-token" not in added_events[0].payload_excerpt


async def test_message_correlation_context_keeps_existing_context(
    test_consumer: ConcreteTestConsumer,
):
    mock_msg = create_mock_message(
        "key-context",
        {"data": "value-context"},
        headers=[("correlation_id", b"corr-header")],
    )

    token = correlation_id_var.set("corr-current")
    try:
        with test_consumer._message_correlation_context(
            mock_msg,
            fallback_correlation_id="corr-fallback",
            prefer_fallback=True,
        ) as correlation_id:
            assert correlation_id == "corr-current"
            assert correlation_id_var.get() == "corr-current"
    finally:
        correlation_id_var.reset(token)


async def test_message_correlation_context_uses_header_before_fallback(
    test_consumer: ConcreteTestConsumer,
):
    mock_msg = create_mock_message(
        "key-header",
        {"data": "value-header"},
        headers=[("correlation_id", b"corr-header")],
    )

    token = correlation_id_var.set("<not-set>")
    try:
        with test_consumer._message_correlation_context(
            mock_msg,
            fallback_correlation_id="corr-fallback",
        ) as correlation_id:
            assert correlation_id == "corr-header"
            assert correlation_id_var.get() == "corr-header"
    finally:
        correlation_id_var.reset(token)


async def test_message_correlation_context_sets_traceparent_from_header(
    test_consumer: ConcreteTestConsumer,
):
    mock_msg = create_mock_message(
        "key-trace-context",
        {"data": "value-trace-context"},
        headers=[("correlation_id", b"corr-header"), ("traceparent", TRACEPARENT.encode("utf-8"))],
    )

    corr_token = correlation_id_var.set("<not-set>")
    trace_token = traceparent_var.set("<not-set>")
    try:
        with test_consumer._message_correlation_context(mock_msg) as correlation_id:
            assert correlation_id == "corr-header"
            assert traceparent_var.get() == TRACEPARENT
    finally:
        traceparent_var.reset(trace_token)
        correlation_id_var.reset(corr_token)


async def test_message_correlation_context_ignores_invalid_traceparent_bytes(
    test_consumer: ConcreteTestConsumer,
):
    mock_msg = create_mock_message(
        "key-invalid-trace-context",
        {"data": "value-invalid-trace-context"},
        headers=[("correlation_id", b"corr-header"), ("traceparent", b"\xff\xfe")],
    )

    corr_token = correlation_id_var.set("<not-set>")
    trace_token = traceparent_var.set("<not-set>")
    try:
        with test_consumer._message_correlation_context(mock_msg) as correlation_id:
            assert correlation_id == "corr-header"
            assert traceparent_var.get() == "<not-set>"
    finally:
        traceparent_var.reset(trace_token)
        correlation_id_var.reset(corr_token)


async def test_message_correlation_context_can_prefer_fallback(
    test_consumer: ConcreteTestConsumer,
):
    mock_msg = create_mock_message(
        "key-fallback",
        {"data": "value-fallback"},
        headers=[("correlation_id", b"corr-header")],
    )

    token = correlation_id_var.set("<not-set>")
    try:
        with test_consumer._message_correlation_context(
            mock_msg,
            fallback_correlation_id="corr-fallback",
            prefer_fallback=True,
        ) as correlation_id:
            assert correlation_id == "corr-fallback"
            assert correlation_id_var.get() == "corr-fallback"
    finally:
        correlation_id_var.reset(token)


async def test_dlq_flush_timeout_does_not_record_event(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    mock_msg = create_mock_message("key-timeout", {"data": "value-timeout"})
    error = RuntimeError("downstream timeout")
    test_consumer._record_consumer_dlq_event = AsyncMock()
    mock_kafka_producer.flush.return_value = 1

    with patch("portfolio_common.kafka_consumer.logger.error") as mock_log_error:
        result = await test_consumer._send_to_dlq_async(mock_msg, error)

    assert result is False
    mock_kafka_producer.publish_message.assert_called_once()
    mock_kafka_producer.flush.assert_called_once_with(timeout=5)
    test_consumer._record_consumer_dlq_event.assert_not_awaited()
    mock_log_error.assert_called_once()
    assert mock_log_error.call_args.args[0] == "Kafka DLQ publication failed."
    assert mock_log_error.call_args.kwargs["extra"]["event_name"] == "kafka.consumer.dlq_failed"
    assert mock_log_error.call_args.kwargs["extra"]["reason_code"] == "dlq_publish_error"


async def test_dlq_failure_emits_standard_consumer_metric(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    mock_msg = create_mock_message("key-dlq-failure-metrics", {"data": "value"})
    mock_kafka_producer.flush.return_value = 1

    with (
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric,
        patch("portfolio_common.kafka_consumer.logger.error"),
    ):
        result = await test_consumer._send_to_dlq_async(
            mock_msg,
            RuntimeError("downstream timeout"),
        )

    assert result is False
    assert ("dlq_failed", "dlq_publish_error") in _consumer_event_outcomes(event_metric)
    _assert_standard_metric_labels(event_metric)


async def test_dlq_publish_exception_does_not_record_event(
    test_consumer: ConcreteTestConsumer, mock_kafka_producer: MagicMock
):
    mock_msg = create_mock_message("key-fail", {"data": "value-fail"})
    error = ValueError("validation failed")
    test_consumer._record_consumer_dlq_event = AsyncMock()
    mock_kafka_producer.publish_message.side_effect = RuntimeError("producer unavailable")

    with patch("portfolio_common.kafka_consumer.logger.error") as mock_log_error:
        result = await test_consumer._send_to_dlq_async(mock_msg, error)

    assert result is False
    mock_kafka_producer.flush.assert_not_called()
    test_consumer._record_consumer_dlq_event.assert_not_awaited()
    mock_log_error.assert_called_once()


async def test_classify_dlq_reason_code_deserialization():
    assert (
        classify_dlq_reason_code(ValueError("JSON decode failed at position 13"))
        == "DESERIALIZATION_ERROR"
    )


async def test_classify_dlq_reason_code_timeout():
    assert (
        classify_dlq_reason_code(RuntimeError("downstream timeout while reading response"))
        == "DOWNSTREAM_TIMEOUT"
    )


async def test_transaction_semantic_conflict_preserves_reason_and_fingerprints() -> None:
    error = TransactionSemanticConflictError(
        semantic_key="transaction-persistence:v1:tenant-a:TX-001",
        existing_payload_fingerprint="sha256:" + "a" * 64,
        incoming_payload_fingerprint="sha256:" + "b" * 64,
    )

    assert classify_dlq_reason_code(error) == "TRANSACTION_SEMANTIC_CONFLICT"
    assert error.existing_payload_fingerprint == "sha256:" + "a" * 64
    assert error.incoming_payload_fingerprint == "sha256:" + "b" * 64
    assert "existing_payload_fingerprint=sha256:" + "a" * 64 in str(error)
    assert "incoming_payload_fingerprint=sha256:" + "b" * 64 in str(error)


@pytest.mark.parametrize(
    ("declared_reason_code", "expected_reason_code"),
    [
        ("SELL_010_NON_POSITIVE_NET_SETTLEMENT", "SELL_010_NON_POSITIVE_NET_SETTLEMENT"),
        (" interest_017_non_positive_net_settlement ", "INTEREST_017_NON_POSITIVE_NET_SETTLEMENT"),
        ("transaction-id-123", "VALIDATION_ERROR"),
        ("A" * 97, "VALIDATION_ERROR"),
    ],
)
async def test_classify_dlq_reason_code_preserves_only_bounded_application_codes(
    declared_reason_code: str,
    expected_reason_code: str,
) -> None:
    error = ValueError("required settlement cash is invalid")
    error.reason_code = declared_reason_code  # type: ignore[attr-defined]

    assert classify_dlq_reason_code(error) == expected_reason_code


@pytest.mark.parametrize(
    ("error", "expected_reason_code"),
    [
        (ValueError("required portfolio_id is missing"), "VALIDATION_ERROR"),
        (RuntimeError("foreign key constraint failed"), "DATA_INTEGRITY_ERROR"),
        (TimeoutError("deadline exceeded while calling downstream"), "DOWNSTREAM_TIMEOUT"),
        (PermissionError("access denied by policy"), "AUTHORIZATION_ERROR"),
        (RuntimeError("worker stopped unexpectedly"), "UNCLASSIFIED_PROCESSING_ERROR"),
    ],
)
async def test_classify_dlq_reason_code_taxonomy(error, expected_reason_code):
    assert classify_dlq_reason_code(error) == expected_reason_code


async def test_consumer_applies_runtime_overrides(monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON",
        '{"max.poll.interval.ms": 180000, "fetch.min.bytes": 1}',
    )
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON",
        '{"test-group": {"fetch.min.bytes": 4096, "max.partition.fetch.bytes": 1048576}}',
    )

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=MagicMock()),
        patch("portfolio_common.kafka_consumer.get_kafka_producer", return_value=MagicMock()),
    ):
        consumer = ConcreteTestConsumer(
            bootstrap_servers="mock_bs",
            topic="test-topic",
            group_id="test-group",
            dlq_topic="test.dlq",
        )

    assert consumer._consumer_config["max.poll.interval.ms"] == 180000
    assert consumer._consumer_config["fetch.min.bytes"] == 4096
    assert consumer._consumer_config["max.partition.fetch.bytes"] == 1048576


async def test_consumer_ignores_invalid_runtime_overrides(monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON",
        '{"unsupported.key": 1, "enable.auto.commit": "false"}',
    )
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON",
        '{"test-group": {"session.timeout.ms": "45000"}}',
    )

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=MagicMock()),
        patch("portfolio_common.kafka_consumer.get_kafka_producer", return_value=MagicMock()),
    ):
        consumer = ConcreteTestConsumer(
            bootstrap_servers="mock_bs",
            topic="test-topic",
            group_id="test-group",
            dlq_topic="test.dlq",
        )

    assert "unsupported.key" not in consumer._consumer_config
    assert consumer._consumer_config["enable.auto.commit"] is False
    assert consumer._consumer_config["session.timeout.ms"] == 45000


async def test_consumer_drops_invalid_merged_heartbeat_session_override(monkeypatch):
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_DEFAULTS_JSON",
        '{"session.timeout.ms": 30000}',
    )
    monkeypatch.setenv(
        "LOTUS_CORE_KAFKA_CONSUMER_GROUP_OVERRIDES_JSON",
        '{"test-group": {"heartbeat.interval.ms": 30000}}',
    )

    with (
        patch("portfolio_common.kafka_consumer.Consumer", return_value=MagicMock()),
        patch("portfolio_common.kafka_consumer.get_kafka_producer", return_value=MagicMock()),
    ):
        consumer = ConcreteTestConsumer(
            bootstrap_servers="mock_bs",
            topic="test-topic",
            group_id="test-group",
            dlq_topic="test.dlq",
        )

    assert consumer._consumer_config["session.timeout.ms"] == 30000
    assert consumer._consumer_config["heartbeat.interval.ms"] == 3000


async def test_shutdown_logs_flush_timeout_without_raising(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
    mock_kafka_producer: MagicMock,
):
    test_consumer._consumer = mock_confluent_consumer
    mock_kafka_producer.flush.return_value = 2

    with patch("portfolio_common.kafka_consumer.logger.error") as mock_log_error:
        test_consumer.shutdown()
        await test_consumer.wait_closed()

    mock_confluent_consumer.close.assert_called_once()
    mock_kafka_producer.flush.assert_called_once_with(timeout=5)
    assert (
        "DLQ producer flush left undelivered messages during shutdown."
        in mock_log_error.call_args.args[0]
    )


async def test_shutdown_awaits_serialized_close(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
):
    test_consumer._consumer = mock_confluent_consumer

    test_consumer.shutdown()
    await test_consumer.wait_closed()

    mock_confluent_consumer.wakeup.assert_not_called()
    mock_confluent_consumer.close.assert_called_once()


async def test_shutdown_does_not_use_unowned_wakeup(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
):
    test_consumer._consumer = mock_confluent_consumer
    mock_confluent_consumer.wakeup.side_effect = RuntimeError("wakeup failed")

    with patch("portfolio_common.kafka_consumer.logger.warning") as mock_warning:
        test_consumer.shutdown()
        await test_consumer.wait_closed()

    mock_confluent_consumer.close.assert_called_once()
    mock_confluent_consumer.wakeup.assert_not_called()
    mock_warning.assert_not_called()


async def test_shutdown_logs_close_failure_without_raising(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
):
    test_consumer._consumer = mock_confluent_consumer
    mock_confluent_consumer.close.side_effect = RuntimeError("close failed")

    with patch("portfolio_common.kafka_consumer.logger.error") as mock_log_error:
        test_consumer.shutdown()
        await test_consumer.wait_closed()

    mock_confluent_consumer.wakeup.assert_not_called()
    assert "Consumer close failed during shutdown." in mock_log_error.call_args.args[0]


async def test_shutdown_logs_close_and_flush_failures_without_raising(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
    mock_kafka_producer: MagicMock,
):
    test_consumer._consumer = mock_confluent_consumer
    mock_confluent_consumer.close.side_effect = RuntimeError("close failed")
    mock_kafka_producer.flush.side_effect = RuntimeError("flush failed")

    with patch("portfolio_common.kafka_consumer.logger.error") as mock_log_error:
        test_consumer.shutdown()
        await test_consumer.wait_closed()

    assert mock_log_error.call_count == 2
    assert "Consumer close failed during shutdown." == mock_log_error.call_args_list[0].args[0]
    assert "DLQ producer flush failed during shutdown." == mock_log_error.call_args_list[1].args[0]


async def test_shutdown_failures_emit_standard_consumer_metrics(
    test_consumer: ConcreteTestConsumer,
    mock_confluent_consumer: MagicMock,
    mock_kafka_producer: MagicMock,
):
    test_consumer._consumer = mock_confluent_consumer
    mock_confluent_consumer.close.side_effect = RuntimeError("close failed")
    mock_kafka_producer.flush.side_effect = RuntimeError("flush failed")

    with (
        patch("portfolio_common.kafka_consumer.observe_kafka_consumer_event") as event_metric,
        patch("portfolio_common.kafka_consumer.logger.error"),
    ):
        test_consumer.shutdown()
        await test_consumer.wait_closed()

    outcomes = _consumer_event_outcomes(event_metric)
    assert ("shutdown_failed", "consumer_close") in outcomes
    assert ("shutdown_failed", "dlq_flush") in outcomes
    _assert_standard_metric_labels(event_metric)
