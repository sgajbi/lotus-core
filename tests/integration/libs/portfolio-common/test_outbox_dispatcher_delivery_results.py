# tests/integration/libs/portfolio-common/integration/test_outbox_dispatcher_delivery_results.py
import json
import uuid
from unittest.mock import MagicMock

import pytest
from portfolio_common.database_models import OutboxEvent
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """
    Mock KafkaProducer that triggers delivery callbacks with a pattern of
    Success, Failure, Success when flush is called.
    """
    mock = MagicMock(spec=KafkaProducer)

    def _flush(timeout=10):
        # Simulate delivery results for 3 messages: S, F, S
        outcomes = [
            (True, None),  # Success
            (False, "simulated error"),  # Failure
            (True, None),  # Success
        ]

        for call, (ok, err_msg) in zip(mock.publish_message.call_args_list, outcomes):
            kwargs = call.kwargs
            cb = kwargs.get("on_delivery")
            outbox_id = kwargs.get("outbox_id")
            if cb and outbox_id:
                cb(outbox_id, ok, err_msg)

    mock.flush.side_effect = _flush
    return mock


async def test_marks_only_success_on_delivery(db_engine, clean_db, mock_kafka_producer):
    """
    GIVEN three pending outbox events
    WHEN one batch is processed and delivery yields S, F, S
    THEN only successes are PROCESSED; failure remains PENDING with retry_count incremented.
    """
    # ARRANGE
    ids = []
    with Session(db_engine) as session:
        with session.begin():
            for i in range(3):
                aggregate_id = f"agg-{uuid.uuid4()}"
                payload = {"i": i, "msg": "hello"}
                evt = OutboxEvent(
                    aggregate_type="TestAggregate",
                    aggregate_id=aggregate_id,
                    status="PENDING",
                    event_type="TestEvent",
                    payload=json.dumps(payload),
                    topic="test.topic",
                )
                session.add(evt)
            session.flush()
            ids = [r.id for r in session.query(OutboxEvent.id).order_by(OutboxEvent.id).all()]

    # ACT
    dispatcher = OutboxDispatcher(
        kafka_producer=mock_kafka_producer, poll_interval=1, batch_size=10
    )
    # run one deterministic synchronous cycle
    dispatcher._process_batch_sync()

    # ASSERT
    with Session(db_engine) as session:
        rows = session.execute(
            text(
                "SELECT id, status, retry_count FROM outbox_events WHERE id = ANY(:ids) ORDER BY id"
            ),
            {"ids": ids},
        ).all()

    # Expected: [S, F, S]
    assert rows[0].status == "PROCESSED"
    assert rows[1].status == "PENDING"
    assert rows[1].retry_count is not None and rows[1].retry_count >= 1
    assert rows[2].status == "PROCESSED"


# --- NEW TEST ---
async def test_increments_retry_count_from_null(db_engine, clean_db):
    """
    GIVEN an outbox event with a NULL retry_count
    WHEN delivery fails
    THEN the retry_count should be correctly updated to 1, not NULL.
    """
    # ARRANGE
    mock_producer = MagicMock(spec=KafkaProducer)

    def _failing_flush(timeout=10):
        # Simulate failed delivery for all messages
        for call in mock_producer.publish_message.call_args_list:
            kwargs = call.kwargs
            cb = kwargs.get("on_delivery")
            outbox_id = kwargs.get("outbox_id")
            if cb and outbox_id:
                cb(outbox_id, False, "Simulated delivery failure")

    mock_producer.flush.side_effect = _failing_flush

    event_id = None
    with Session(db_engine) as session:
        with session.begin():
            evt = OutboxEvent(
                aggregate_type="NullRetryTest",
                aggregate_id="agg-null-retry",
                status="PENDING",
                event_type="TestEvent",
                payload=json.dumps({"data": "test"}),
                topic="test.topic",
                retry_count=None,  # Explicitly set to NULL
            )
            session.add(evt)
            session.flush()
            event_id = evt.id

    # ACT
    dispatcher = OutboxDispatcher(kafka_producer=mock_producer, poll_interval=0.1, batch_size=5)
    dispatcher._process_batch_sync()

    # ASSERT
    with Session(db_engine) as session:
        result = session.execute(
            text("SELECT retry_count FROM outbox_events WHERE id = :id"), {"id": event_id}
        ).scalar_one_or_none()

    assert result == 1


async def test_synchronous_publish_failure_does_not_abort_accounted_batch(db_engine, clean_db):
    """
    GIVEN a batch where one publish_message call raises synchronously mid-loop
    WHEN the dispatcher processes the batch
    THEN already-queued rows are still flushed and accounted for, while the failing row is retried.
    """
    mock_producer = MagicMock(spec=KafkaProducer)
    published_outbox_ids: list[str] = []
    failing_outbox_id: str | None = None

    with Session(db_engine) as session:
        with session.begin():
            for i in range(3):
                evt = OutboxEvent(
                    aggregate_type="SyncPublishFailureTest",
                    aggregate_id=f"agg-sync-publish-{uuid.uuid4()}",
                    status="PENDING",
                    event_type="TestEvent",
                    payload=json.dumps({"i": i}),
                    topic="test.topic",
                )
                session.add(evt)
            session.flush()
            ids = [r.id for r in session.query(OutboxEvent.id).order_by(OutboxEvent.id).all()]
            failing_outbox_id = str(ids[1])

    def _publish_message(**kwargs):
        outbox_id = kwargs["outbox_id"]
        if outbox_id == failing_outbox_id:
            raise RuntimeError("synchronous publish failure")
        published_outbox_ids.append(outbox_id)

    def _flush(timeout=10):
        for call in mock_producer.publish_message.call_args_list:
            kwargs = call.kwargs
            outbox_id = kwargs.get("outbox_id")
            cb = kwargs.get("on_delivery")
            if cb and outbox_id in published_outbox_ids:
                cb(outbox_id, True, None)

    mock_producer.publish_message.side_effect = _publish_message
    mock_producer.flush.side_effect = _flush

    dispatcher = OutboxDispatcher(kafka_producer=mock_producer, poll_interval=0.1, batch_size=5)
    dispatcher._process_batch_sync()

    with Session(db_engine) as session:
        rows = session.execute(
            text(
                "SELECT id, status, retry_count FROM outbox_events WHERE id = ANY(:ids) ORDER BY id"
            ),
            {"ids": ids},
        ).all()

    assert [row.status for row in rows] == ["PROCESSED", "PENDING", "PROCESSED"]
    assert rows[1].retry_count == 1
