"""Offline caller-boundary proofs for DLQ replay's owned native lifecycle."""

import asyncio
import json
import logging
import threading
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from confluent_kafka import TopicPartition

from tools import dlq_replayer
from tools.dlq_replayer import DLQReplayConsumer

pytestmark = pytest.mark.asyncio
TRACEPARENT = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"


class ReplayMessage:
    def __init__(self, payload=None, offset=7):
        self.payload = (
            payload
            if payload is not None
            else json.dumps(
                {
                    "original_topic": "original",
                    "original_key": "key",
                    "original_value": json.dumps({"amount": 10}),
                    "correlation_id": "correlation",
                    "traceparent": TRACEPARENT,
                }
            ).encode()
        )
        self.position = offset

    def value(self):
        return self.payload

    def key(self):
        return b"dlq-key"

    def topic(self):
        return "dlq"

    def partition(self):
        return 2

    def offset(self):
        return self.position

    def error(self):
        return None

    def headers(self):
        return []


class RecordingNative:
    def __init__(self, messages, calls):
        self.messages = deque(messages)
        self.calls = calls
        self.ack = None

    def record(self, name, value=None):
        self.calls.append((name, value, threading.get_ident()))

    def subscribe(self, topics, **callbacks):
        self.record("subscribe", topics)

    def poll(self, timeout):
        self.record("poll")
        return self.messages.popleft() if self.messages else None

    def commit(self, *, message, asynchronous):
        assert asynchronous is False
        self.record("commit", message.offset())
        return (
            self.ack
            if self.ack is not None
            else [TopicPartition(message.topic(), message.partition(), message.offset() + 1)]
        )

    def get_watermark_offsets(self, partition, *, cached):
        return 0, 10

    def close(self):
        self.record("close")


class RecordingProducer:
    def __init__(self, calls):
        self.calls = calls
        self.undelivered = 0
        self.publish_error = None
        self.flush_hook = lambda: None

    def publish_message(self, **kwargs):
        self.calls.append(("publish", kwargs, threading.get_ident()))
        if self.publish_error:
            raise self.publish_error

    def flush(self, timeout):
        self.calls.append(("flush", timeout, threading.get_ident()))
        self.flush_hook()
        return self.undelivered


def compose(messages, limit=1):
    calls = []
    native = RecordingNative(messages, calls)
    producer = RecordingProducer(calls)
    with patch("tools.dlq_replayer.get_kafka_producer", return_value=producer):
        consumer = DLQReplayConsumer(
            bootstrap_servers="offline:9092", topic="dlq", group_id="offline-dlq", limit=limit
        )
    return consumer, native, producer, calls


async def test_actual_caller_initializes_then_replays_before_exact_ack_and_close():
    consumer, native, producer, calls = compose([ReplayMessage()])
    with patch("portfolio_common.kafka_consumer.Consumer", return_value=native):
        try:
            await consumer.run()
        finally:
            consumer.shutdown()
            await consumer.wait_closed()
    operations = [name for name, _, _ in calls]
    assert operations.index("subscribe") < operations.index("poll")
    assert operations.index("publish") < operations.index("flush") < operations.index("commit")
    assert operations.index("commit") < operations.index("close")
    assert operations.count("commit") == operations.count("close") == 1
    publish = next(value for name, value, _ in calls if name == "publish")
    assert publish == {
        "topic": "original",
        "key": "key",
        "value": {"amount": 10},
        "headers": [("correlation_id", b"correlation"), ("traceparent", TRACEPARENT.encode())],
    }
    assert len({thread for _, _, thread in calls}) == 1
    assert calls[0][2] != threading.get_ident()


@pytest.mark.parametrize("failure", ["undelivered", "publish", "flush"])
async def test_failed_replay_stops_admission_without_acknowledging_later_offset(failure):
    consumer, native, producer, calls = compose([ReplayMessage(), ReplayMessage(offset=8)], limit=2)
    if failure == "undelivered":
        producer.undelivered = 1
    elif failure == "publish":
        producer.publish_error = RuntimeError("producer unavailable")
    else:

        def fail_flush():
            raise RuntimeError("flush unavailable")

        producer.flush_hook = fail_flush
    with patch("portfolio_common.kafka_consumer.Consumer", return_value=native):
        await consumer.run()
    assert consumer._processed_count == 1
    assert len(native.messages) == 1
    assert not any(name == "commit" for name, _, _ in calls)
    assert sum(name == "close" for name, _, _ in calls) == 1
    assert consumer._shutdown_finalized


@pytest.mark.parametrize(
    "ack",
    [
        [],
        None,
        [TopicPartition("wrong", 2, 8)],
        [TopicPartition("dlq", 3, 8)],
        [TopicPartition("dlq", 2, 7)],
        [SimpleNamespace(topic="dlq", partition=2, offset=8, error="bad")],
    ],
)
async def test_negative_ack_does_not_allow_later_replay(ack):
    consumer, native, producer, calls = compose([ReplayMessage(), ReplayMessage(offset=8)], limit=2)
    native.commit = lambda **kwargs: ack
    with patch("portfolio_common.kafka_consumer.Consumer", return_value=native):
        await consumer.run()
    assert consumer._processed_count == 1
    assert len(native.messages) == 1
    assert sum(name == "publish" for name, _, _ in calls) == 1
    assert sum(name == "close" for name, _, _ in calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"\xff",
        b"null",
        b"[]",
        b"{}",
        b'{"original_topic":"original","original_key":"key","original_value":"{}"}',
        b'{"original_topic":"","original_key":"key","original_value":"{\\"amount\\":1}"}',
        b'{"original_topic":"original","original_key":"key","original_value":"[]"}',
        b'{"original_topic":"original","original_key":"key","original_value":"{\\"amount\\":1}","correlation_id":4}',
    ],
)
async def test_explicit_malformed_discard_then_valid_replay_remains_ordered(payload, caplog):
    consumer, native, producer, calls = compose(
        [ReplayMessage(payload), ReplayMessage(offset=8)], 2
    )
    with (
        caplog.at_level(logging.WARNING, logger=dlq_replayer.logger.name),
        patch("portfolio_common.kafka_consumer.Consumer", return_value=native),
    ):
        await consumer.run()
    assert "Discarding malformed DLQ record" in caplog.text
    assert [value for name, value, _ in calls if name == "commit"] == [7, 8]
    assert sum(name == "publish" for name, _, _ in calls) == 1
    assert consumer._processed_count == 2
    assert sum(name == "close" for name, _, _ in calls) == 1


async def test_missing_optional_headers_preserve_replay_payload():
    payload = json.dumps(
        {
            "original_topic": "original",
            "original_key": "key",
            "original_value": json.dumps({"amount": 0}),
        }
    ).encode()
    consumer, native, producer, calls = compose([ReplayMessage(payload)])
    with patch("portfolio_common.kafka_consumer.Consumer", return_value=native):
        await consumer.run()
    publish = next(value for name, value, _ in calls if name == "publish")
    assert publish["value"] == {"amount": 0}
    assert publish["headers"] == [("correlation_id", b"")]


async def test_finite_operator_deadline_stops_idle_polling_and_closes_once(caplog):
    consumer, native, producer, calls = compose([], None)
    loop = asyncio.get_running_loop()
    schedule = loop.call_later
    delays = []

    def short_deadline(delay, callback, *args, **kwargs):
        if callback == consumer.shutdown:
            delays.append(delay)
            return schedule(0.01, callback, *args, **kwargs)
        return schedule(delay, callback, *args, **kwargs)

    with (
        caplog.at_level(logging.WARNING, logger=dlq_replayer.logger.name),
        patch("portfolio_common.kafka_consumer.Consumer", return_value=native),
        patch.object(loop, "call_later", side_effect=short_deadline),
    ):
        await consumer.run()
    assert delays == [15]
    assert "No DLQ records processed" in caplog.text
    assert not any(name in ("publish", "commit") for name, _, _ in calls)
    assert sum(name == "close" for name, _, _ in calls) == 1


@pytest.mark.parametrize("stop", ["deadline", "cancel", "repeated_cancel"])
async def test_active_native_flush_drains_before_close_and_event_loop_stays_live(stop):
    consumer, native, producer, calls = compose([ReplayMessage(), ReplayMessage(offset=8)], 2)
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()

    def hold_flush():
        loop.call_soon_threadsafe(entered.set)
        if not release.wait(5):
            raise RuntimeError("test handshake failed")

    producer.flush_hook = hold_flush
    with patch("portfolio_common.kafka_consumer.Consumer", return_value=native):
        task = asyncio.create_task(consumer.run())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            # The event loop can perform unrelated work while native flush is active.
            responsive = asyncio.Event()
            loop.call_soon(responsive.set)
            await asyncio.wait_for(responsive.wait(), 1)
            if stop == "deadline":
                consumer.shutdown()
            else:
                task.cancel()
                if stop == "repeated_cancel":
                    await asyncio.sleep(0)
                    task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            assert not any(name == "close" for name, _, _ in calls)
        finally:
            release.set()
            if stop == "deadline":
                await task
            else:
                with pytest.raises(asyncio.CancelledError):
                    await task
        await consumer.wait_closed()
    operations = [name for name, _, _ in calls]
    assert operations.count("publish") == operations.count("close") == 1
    assert len(native.messages) == 1
    if stop == "deadline":
        assert operations.index("flush") < operations.index("commit") < operations.index("close")
    else:
        assert "commit" not in operations
    assert len({thread for _, _, thread in calls}) == 1


async def test_cancellation_during_poll_leaves_returned_message_unadmitted():
    consumer, native, producer, calls = compose([ReplayMessage()], 1)
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()

    def hold_poll(timeout):
        native.record("poll")
        loop.call_soon_threadsafe(entered.set)
        if not release.wait(5):
            raise RuntimeError("test handshake failed")
        return native.messages.popleft()

    native.poll = hold_poll
    with patch("portfolio_common.kafka_consumer.Consumer", return_value=native):
        task = asyncio.create_task(consumer.run())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert not any(name in ("publish", "commit") for name, _, _ in calls)
    assert sum(name == "close" for name, _, _ in calls) == 1


@pytest.mark.parametrize("limit", [None, 2])
async def test_cli_awaits_operator_and_preserves_requested_limit_and_broker(monkeypatch, limit):
    arguments = ["dlq_replayer", "--dlq-topic", "requested-dlq"]
    if limit is not None:
        arguments.extend(["--limit", str(limit)])
    monkeypatch.setattr("sys.argv", arguments)
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "requested-broker:9092")
    operator = SimpleNamespace(run=AsyncMock())
    with patch.object(dlq_replayer, "DLQReplayConsumer", return_value=operator) as constructor:
        await dlq_replayer.main()
    assert constructor.call_args.kwargs == {
        "bootstrap_servers": "requested-broker:9092",
        "topic": "requested-dlq",
        "group_id": f"dlq-replayer-{dlq_replayer.os.getpid()}",
        "limit": limit,
    }
    operator.run.assert_awaited_once()
