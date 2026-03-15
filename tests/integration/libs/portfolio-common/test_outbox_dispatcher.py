# libs/portfolio-common/tests/integration/test_outbox_dispatcher.py
import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from portfolio_common import outbox_dispatcher as outbox_dispatcher_module
from portfolio_common.database_models import OutboxEvent
from portfolio_common.db import AsyncSessionLocal
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from portfolio_common.outbox_repository import OutboxRepository
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def smart_mock_kafka_producer() -> MagicMock:
    """
    Provides a mock of KafkaProducer that allows assertions on publish_message
    and simulates successful delivery callbacks when flush is called.
    """
    mock = MagicMock(spec=KafkaProducer)

    def _flush(timeout=10):
        # Simulate successful delivery for all captured calls to publish_message
        for call in mock.publish_message.call_args_list:
            kwargs = call.kwargs
            cb = kwargs.get("on_delivery")
            outbox_id = kwargs.get("outbox_id")
            if cb and outbox_id:
                cb(outbox_id, True, None)  # Simulate success

    mock.flush.side_effect = _flush
    return mock


@pytest.mark.asyncio
async def test_create_outbox_event_fails_with_missing_aggregate_id(db_engine, clean_db):
    """
    GIVEN an attempt to create an outbox event with a missing or empty aggregate_id
    WHEN create_outbox_event is called
    THEN it should raise a ValueError.
    """
    async with AsyncSessionLocal() as session:
        repo = OutboxRepository(session)

        match_str = "aggregate_id \\(portfolio_id\\) is required for outbox events"

        with pytest.raises(ValueError, match=match_str):
            await repo.create_outbox_event(
                aggregate_type="Test",
                aggregate_id=None,
                event_type="TestEvent",
                topic="test.topic",
                payload={},
            )
        with pytest.raises(ValueError, match=match_str):
            await repo.create_outbox_event(
                aggregate_type="Test",
                aggregate_id="",
                event_type="TestEvent",
                topic="test.topic",
                payload={},
            )


def test_dispatcher_processes_and_updates_pending_events(
    db_engine, clean_db, smart_mock_kafka_producer
):
    """
    GIVEN a pending event in the outbox_events table
    WHEN the OutboxDispatcher runs
    THEN it should publish the event and update its status to PROCESSED.
    """
    # ARRANGE
    TestSessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestSessionFactory()

    aggregate_id = f"agg-id-{uuid.uuid4()}"
    new_event = OutboxEvent(
        aggregate_type="TestAggregate",
        aggregate_id=aggregate_id,
        status="PENDING",
        event_type="TestEvent",
        payload=json.dumps({"msg": "hi"}),
        topic="test.topic",
    )
    session.add(new_event)
    session.commit()
    event_id = new_event.id  # Get the ID after commit
    session.close()

    # ACT: Run one synchronous, deterministic cycle, injecting the test session factory
    dispatcher = OutboxDispatcher(
        kafka_producer=smart_mock_kafka_producer, db_session_factory=TestSessionFactory
    )
    dispatcher._process_batch_sync()

    # ASSERT
    smart_mock_kafka_producer.publish_message.assert_called_once()

    # Verify the database state in a new session to ensure the change was committed
    session = TestSessionFactory()
    result = session.get(OutboxEvent, event_id)
    assert result is not None
    assert result.status == "PROCESSED"
    session.close()


def test_dispatcher_propagates_correlation_id(db_engine, clean_db, smart_mock_kafka_producer):
    """
    GIVEN multiple pending events, one with a correlation_id and one without
    WHEN the OutboxDispatcher runs
    THEN it should publish both with the correct correlation_id in the Kafka headers.
    """
    # ARRANGE
    TestSessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    agg_id_1 = f"agg-id-{uuid.uuid4()}"
    agg_id_2 = f"agg-id-{uuid.uuid4()}"
    existing_corr_id = f"corr-id-{uuid.uuid4()}"

    with TestSessionFactory() as session:
        with session.begin():
            # Event with an existing correlation ID
            session.add(
                OutboxEvent(
                    aggregate_type="TestCorrId",
                    aggregate_id=agg_id_1,
                    status="PENDING",
                    event_type="EventWithCorrId",
                    payload="{}",
                    topic="test.topic",
                    correlation_id=existing_corr_id,
                )
            )
            # Event without a correlation ID
            session.add(
                OutboxEvent(
                    aggregate_type="TestCorrId",
                    aggregate_id=agg_id_2,
                    status="PENDING",
                    event_type="EventWithoutCorrId",
                    payload="{}",
                    topic="test.topic",
                    correlation_id=None,
                )
            )

    # ACT
    dispatcher = OutboxDispatcher(
        kafka_producer=smart_mock_kafka_producer, db_session_factory=TestSessionFactory
    )
    dispatcher._process_batch_sync()

    # ASSERT
    assert smart_mock_kafka_producer.publish_message.call_count == 2

    # Check call for the event that HAD a correlation ID
    call_with_id = next(
        c
        for c in smart_mock_kafka_producer.publish_message.call_args_list
        if c.kwargs["key"] == agg_id_1
    )
    headers_with_id = {key: value for key, value in call_with_id.kwargs["headers"]}
    assert headers_with_id["correlation_id"] == existing_corr_id.encode("utf-8")

    # Check call for the event that DID NOT have a correlation ID
    call_without_id = next(
        c
        for c in smart_mock_kafka_producer.publish_message.call_args_list
        if c.kwargs["key"] == agg_id_2
    )
    headers_without_id = {key: value for key, value in call_without_id.kwargs["headers"]}
    # It should not have a correlation_id header
    assert "correlation_id" not in headers_without_id


def test_dispatcher_recovers_after_failure(db_engine, clean_db, smart_mock_kafka_producer):
    """
    GIVEN a pending event
    WHEN the dispatcher fails on its first poll and then recovers
    THEN the event should be processed on the subsequent poll.
    """
    # ARRANGE
    TestSessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    aggregate_id = f"agg-id-{uuid.uuid4()}"
    with TestSessionFactory() as session:
        with session.begin():
            session.add(
                OutboxEvent(
                    aggregate_type="TestResilience",
                    aggregate_id=aggregate_id,
                    status="PENDING",
                    event_type="TestEvent",
                    payload="{}",
                    topic="resilience.topic",
                )
            )

    call_count = 0
    pending_deliveries: list[dict[str, object]] = []

    def _publish_message(**kwargs):
        pending_deliveries.append(kwargs)

    def stateful_flush_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            for queued in pending_deliveries:
                cb = queued.get("on_delivery")
                outbox_id = queued.get("outbox_id")
                if cb and outbox_id:
                    cb(outbox_id, False, "Kafka is down!")
        else:
            for queued in pending_deliveries:
                cb = queued.get("on_delivery")
                outbox_id = queued.get("outbox_id")
                if cb and outbox_id:
                    cb(outbox_id, True, None)
        pending_deliveries.clear()

    smart_mock_kafka_producer.publish_message.side_effect = _publish_message
    smart_mock_kafka_producer.flush.side_effect = stateful_flush_side_effect

    dispatcher = OutboxDispatcher(
        kafka_producer=smart_mock_kafka_producer, db_session_factory=TestSessionFactory
    )

    # ACT 1: First poll cycle fails internally, but dispatcher should handle it
    dispatcher._process_batch_sync()

    # ASSERT 1
    with TestSessionFactory() as session:
        status, retry_count = session.execute(
            text("SELECT status, retry_count FROM outbox_events WHERE aggregate_id = :id"),
            {"id": aggregate_id},
        ).one()
        assert status == "PENDING"
        assert retry_count == 1

    # ACT 2: Second poll cycle should succeed
    dispatcher._process_batch_sync()

    # ASSERT 2
    assert smart_mock_kafka_producer.flush.call_count == 2
    with TestSessionFactory() as session:
        status = session.execute(
            text("SELECT status FROM outbox_events WHERE aggregate_id = :id"), {"id": aggregate_id}
        ).scalar_one()
        assert status == "PROCESSED"


def test_dispatcher_marks_terminal_failures_as_failed(db_engine, clean_db):
    """
    GIVEN a pending outbox event already at MAX_RETRIES - 1
    WHEN delivery fails again
    THEN the dispatcher should mark it FAILED and stop leaving it PENDING.
    """
    failing_producer = MagicMock(spec=KafkaProducer)

    def _failing_flush(timeout=10):
        for call in failing_producer.publish_message.call_args_list:
            kwargs = call.kwargs
            cb = kwargs.get("on_delivery")
            outbox_id = kwargs.get("outbox_id")
            if cb and outbox_id:
                cb(outbox_id, False, "terminal failure")

    failing_producer.flush.side_effect = _failing_flush

    TestSessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    aggregate_id = f"terminal-agg-{uuid.uuid4()}"
    with TestSessionFactory() as session:
        with session.begin():
            session.add(
                OutboxEvent(
                    aggregate_type="TerminalFailureTest",
                    aggregate_id=aggregate_id,
                    status="PENDING",
                    event_type="TestEvent",
                    payload="{}",
                    topic="terminal.topic",
                    retry_count=2,
                )
            )

    dispatcher = OutboxDispatcher(
        kafka_producer=failing_producer,
        db_session_factory=TestSessionFactory,
    )
    dispatcher._process_batch_sync()

    with TestSessionFactory() as session:
        status, retry_count = session.execute(
            text("SELECT status, retry_count FROM outbox_events WHERE aggregate_id = :id"),
            {"id": aggregate_id},
        ).one()
        assert status == "FAILED"
        assert retry_count == 3


def test_dispatcher_respects_configured_terminal_retry_ceiling(db_engine, clean_db):
    """
    GIVEN a pending outbox event with retry_count just below a custom ceiling
    WHEN delivery fails and the dispatcher uses a non-default max_retries
    THEN the event should move to FAILED at that configured threshold.
    """
    failing_producer = MagicMock(spec=KafkaProducer)

    def _failing_flush(timeout=10):
        for call in failing_producer.publish_message.call_args_list:
            kwargs = call.kwargs
            cb = kwargs.get("on_delivery")
            outbox_id = kwargs.get("outbox_id")
            if cb and outbox_id:
                cb(outbox_id, False, "terminal failure")

    failing_producer.flush.side_effect = _failing_flush

    TestSessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    aggregate_id = f"custom-terminal-agg-{uuid.uuid4()}"
    with TestSessionFactory() as session:
        with session.begin():
            session.add(
                OutboxEvent(
                    aggregate_type="TerminalFailureTest",
                    aggregate_id=aggregate_id,
                    status="PENDING",
                    event_type="TestEvent",
                    payload="{}",
                    topic="terminal.topic",
                    retry_count=1,
                )
            )

    dispatcher = OutboxDispatcher(
        kafka_producer=failing_producer,
        db_session_factory=TestSessionFactory,
        max_retries=2,
    )
    dispatcher._process_batch_sync()

    with TestSessionFactory() as session:
        status, retry_count = session.execute(
            text("SELECT status, retry_count FROM outbox_events WHERE aggregate_id = :id"),
            {"id": aggregate_id},
        ).one()
        assert status == "FAILED"
        assert retry_count == 2


def test_dispatcher_reads_pending_failed_and_oldest_age_gauges(db_engine, clean_db, monkeypatch):
    """
    GIVEN pending and terminal FAILED outbox rows with different ages
    WHEN the dispatcher refreshes its gauges
    THEN it should publish pending count, failed count, and oldest pending age.
    """
    TestSessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    now = datetime.now(timezone.utc)
    with TestSessionFactory() as session:
        with session.begin():
            session.add_all(
                [
                    OutboxEvent(
                        aggregate_type="GaugeTest",
                        aggregate_id=f"pending-old-{uuid.uuid4()}",
                        status="PENDING",
                        event_type="TestEvent",
                        payload="{}",
                        topic="gauge.topic",
                        created_at=now - timedelta(minutes=10),
                    ),
                    OutboxEvent(
                        aggregate_type="GaugeTest",
                        aggregate_id=f"pending-new-{uuid.uuid4()}",
                        status="PENDING",
                        event_type="TestEvent",
                        payload="{}",
                        topic="gauge.topic",
                        created_at=now - timedelta(minutes=1),
                    ),
                    OutboxEvent(
                        aggregate_type="GaugeTest",
                        aggregate_id=f"failed-{uuid.uuid4()}",
                        status="FAILED",
                        event_type="TestEvent",
                        payload="{}",
                        topic="gauge.topic",
                        created_at=now - timedelta(minutes=20),
                    ),
                ]
            )

    observed: dict[str, float] = {}
    monkeypatch.setattr(
        outbox_dispatcher_module,
        "set_outbox_pending",
        lambda value: observed.__setitem__("pending", float(value)),
    )
    monkeypatch.setattr(
        outbox_dispatcher_module,
        "set_outbox_failed_stored",
        lambda value: observed.__setitem__("failed", float(value)),
    )
    monkeypatch.setattr(
        outbox_dispatcher_module,
        "set_outbox_oldest_pending_age_seconds",
        lambda value: observed.__setitem__("oldest_age", float(value)),
    )

    dispatcher = OutboxDispatcher(
        kafka_producer=MagicMock(spec=KafkaProducer),
        db_session_factory=TestSessionFactory,
    )
    dispatcher._read_pending_gauge()

    assert observed["pending"] == 2.0
    assert observed["failed"] == 1.0
    assert 540.0 <= observed["oldest_age"] <= 660.0


@pytest.mark.asyncio
async def test_dispatcher_is_concurrent_safe(db_engine, clean_db, smart_mock_kafka_producer):
    # ARRANGE
    TestSessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    num_events = 10
    with TestSessionFactory() as session:
        with session.begin():
            for i in range(num_events):
                session.add(
                    OutboxEvent(
                        aggregate_type="ConcurrentTest",
                        aggregate_id=f"concurrent-agg-{i}",
                        status="PENDING",
                        event_type="TestEvent",
                        payload="{}",
                        topic="concurrent.topic",
                    )
                )

    # ACT
    dispatcher1 = OutboxDispatcher(
        kafka_producer=smart_mock_kafka_producer,
        poll_interval=0.1,
        batch_size=5,
        db_session_factory=TestSessionFactory,
    )
    dispatcher2 = OutboxDispatcher(
        kafka_producer=smart_mock_kafka_producer,
        poll_interval=0.1,
        batch_size=5,
        db_session_factory=TestSessionFactory,
    )
    task1 = asyncio.create_task(dispatcher1.run())
    task2 = asyncio.create_task(dispatcher2.run())

    # Wait deterministically until all events are processed (or timeout),
    # instead of relying on a fixed sleep that can be flaky under load.
    deadline = asyncio.get_event_loop().time() + 10.0
    while True:
        with TestSessionFactory() as session:
            processed = session.execute(
                text("SELECT count(*) FROM outbox_events WHERE status = 'PROCESSED'")
            ).scalar_one()
        if processed == num_events:
            break
        if asyncio.get_event_loop().time() >= deadline:
            break
        await asyncio.sleep(0.2)

    dispatcher1.stop()
    dispatcher2.stop()
    await asyncio.gather(task1, task2)

    # ASSERT: The most important check is that all events were processed exactly once.
    with TestSessionFactory() as session:
        count = session.execute(
            text("SELECT count(*) FROM outbox_events WHERE status = 'PROCESSED'")
        ).scalar_one()
        assert count == num_events


def test_dispatcher_respects_batch_size(db_engine, clean_db, smart_mock_kafka_producer):
    # ARRANGE
    TestSessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    num_events, batch_size = 15, 10
    with TestSessionFactory() as session:
        with session.begin():
            for i in range(num_events):
                session.add(
                    OutboxEvent(
                        aggregate_type="BatchTest",
                        aggregate_id=f"batch-agg-{i}",
                        status="PENDING",
                        event_type="TestEvent",
                        payload="{}",
                        topic="batch.topic",
                    )
                )

    # ACT
    dispatcher = OutboxDispatcher(
        kafka_producer=smart_mock_kafka_producer,
        batch_size=batch_size,
        db_session_factory=TestSessionFactory,
    )
    dispatcher._process_batch_sync()

    # ASSERT
    assert smart_mock_kafka_producer.publish_message.call_count == batch_size
    with TestSessionFactory() as session:
        processed_count = session.execute(
            text("SELECT count(*) FROM outbox_events WHERE status = 'PROCESSED'")
        ).scalar_one()
        pending_count = session.execute(
            text("SELECT count(*) FROM outbox_events WHERE status = 'PENDING'")
        ).scalar_one()
        assert processed_count == batch_size
        assert pending_count == num_events - batch_size
