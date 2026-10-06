"""Recording-client proofs for durable, responsive native consumer ownership."""

import asyncio
import logging
import threading
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from confluent_kafka import KafkaError, TopicPartition
from portfolio_common import runtime_supervision, worker_runtime
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.kafka_consumer_execution import KafkaConsumerExecutionProfile

pytestmark = pytest.mark.asyncio


@dataclass
class RecordedMessage:
    partition_id: int = 0
    offset_id: int = 0

    def topic(self):
        return "recorded"

    def partition(self):
        return self.partition_id

    def offset(self):
        return self.offset_id

    def headers(self):
        return []

    def key(self):
        return b"recorded"

    def value(self):
        return b"{}"

    def error(self):
        return None


class RecordingConsumer:
    def __init__(self):
        self.calls = []
        self.callbacks = {}
        self.commit_hook = lambda: None
        self.poll_hook = lambda: None
        self.close_hook = lambda: None
        self.closed = False

    def record(self, operation, value=None):
        self.calls.append((operation, value, threading.get_ident()))

    def subscribe(self, topics, **callbacks):
        self.record("subscribe", topics)
        self.callbacks = callbacks

    def poll(self, timeout):
        self.record("poll", timeout)
        return self.poll_hook()

    def commit(self, *, message, asynchronous):
        assert asynchronous is False
        self.record("commit_enter", message.offset())
        self.commit_hook()
        self.record("commit_ack", message.offset())
        return [TopicPartition(message.topic(), message.partition(), message.offset() + 1)]

    def get_watermark_offsets(self, partition, *, cached):
        assert cached is True
        self.record("watermark")
        return 0, 10

    def pause(self, partitions):
        self.record("pause")

    def resume(self, partitions):
        self.record("resume")

    def close(self):
        self.record("close")
        self.close_hook()
        self.closed = True


class ComposedConsumer(BaseConsumer):
    def __init__(self):
        super().__init__(
            bootstrap_servers="recording-only",
            topic="recorded",
            group_id="recording-group",
            execution_profile=KafkaConsumerExecutionProfile(max_in_flight_messages=2),
        )
        self.process = AsyncMock()

    async def process_message(self, message):
        await self.process(message)


@pytest_asyncio.fixture
async def composed():
    native = RecordingConsumer()
    with patch("portfolio_common.kafka_consumer.Consumer", return_value=native):
        consumer = ComposedConsumer()
        await consumer._initialize_consumer()
        yield consumer, native
        consumer.shutdown()
        await consumer.wait_closed()


async def test_native_ack_keeps_loop_and_other_uow_responsive(composed):
    consumer, native = composed
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    heartbeat = asyncio.Event()
    uow_progress = asyncio.Event()
    observations = []

    def block_commit():
        loop.call_soon_threadsafe(entered.set)
        # Only a deadlock watchdog: success requires the acknowledgement handshake,
        # not passing an elapsed-time threshold or an arbitrary sleep.
        if not release.wait(10):
            raise RuntimeError("Recording commit handshake did not release")

    async def other_uow():
        await entered.wait()
        observations.append("other_uow_progress_before_ack")
        uow_progress.set()

    native.commit_hook = block_commit
    processing = asyncio.create_task(consumer._process_polled_message(RecordedMessage(), loop))
    other = asyncio.create_task(other_uow())
    try:
        await entered.wait()
        loop.call_soon(heartbeat.set)
        await heartbeat.wait()
        await uow_progress.wait()
        assert not processing.done()
        assert not any(call[0] == "commit_ack" for call in native.calls)
        assert observations == ["other_uow_progress_before_ack"]
    finally:
        release.set()
        await asyncio.gather(processing, other)
    assert {call[2] for call in native.calls} == {native.calls[0][2]}
    assert native.calls[0][2] != threading.get_ident()


async def test_active_empty_poll_does_not_hold_acknowledgement_lane(composed):
    consumer, native = composed
    loop = asyncio.get_running_loop()
    active_poll, blocking_poll, watermark_done = (asyncio.Event() for _ in range(3))
    release = threading.Event()
    delivered = False
    original_watermark = native.get_watermark_offsets

    def poll(timeout):
        nonlocal delivered
        native.record("poll", timeout)
        if not delivered:
            delivered = True
            return RecordedMessage()
        loop.call_soon_threadsafe(active_poll.set)
        if timeout > 0:
            loop.call_soon_threadsafe(blocking_poll.set)
            assert release.wait(10), "Recording poll was not released"
        return None

    async def process(_message):
        await active_poll.wait()

    def watermark(partition, *, cached):
        result = original_watermark(partition, cached=cached)
        loop.call_soon_threadsafe(watermark_done.set)
        return result

    native.poll = poll
    native.get_watermark_offsets = watermark
    consumer.process.side_effect = process
    running = asyncio.create_task(consumer._run_concurrent_consumer_loop(loop))
    blocked = asyncio.create_task(blocking_poll.wait())
    completed = asyncio.create_task(watermark_done.wait())
    try:
        # Timeout is only a deadlock watchdog; the native poll/ack handshake is the oracle.
        await asyncio.wait_for(active_poll.wait(), 10)
        await asyncio.wait_for(
            asyncio.wait({blocked, completed}, return_when=asyncio.FIRST_COMPLETED), 10
        )
        assert not blocking_poll.is_set(), "Active empty poll holds the FIFO acknowledgement lane"
        assert watermark_done.is_set()
    finally:
        release.set()
        consumer._running = False
        await running
        for observer in (blocked, completed):
            observer.cancel()
        await asyncio.gather(blocked, completed, return_exceptions=True)
    names = [call[0] for call in native.calls]
    assert names.index("commit_ack") < names.index("watermark")
    assert [call[1] for call in native.calls if call[0] == "commit_ack"] == [0]
    assert len({call[2] for call in native.calls}) == 1


@pytest.mark.parametrize("configured_timeout", [0.05, 1.0])
async def test_active_empty_poll_waits_off_worker_and_services_callbacks(
    composed, configured_timeout
):
    consumer, native = composed
    loop = asyncio.get_running_loop()
    consumer.execution_profile = KafkaConsumerExecutionProfile(
        max_in_flight_messages=2, poll_timeout_seconds=configured_timeout
    )
    entered, release_wait, release_handler = (asyncio.Event() for _ in range(3))
    waits = []

    async def process(_message):
        await release_handler.wait()

    def poll(timeout):
        native.record("poll", timeout)
        native.callbacks["on_assign"](native, [TopicPartition("recorded", 1)])
        return None

    async def wait(_loop, *, timeout_seconds):
        waits.append(timeout_seconds)
        entered.set()
        await release_wait.wait()
        return False

    native.poll = poll
    consumer.process.side_effect = process
    consumer._wait_for_next_processing_task = wait
    consumer._schedule_processing_task(RecordedMessage(), loop, "partition:recorded:0")
    running = asyncio.create_task(consumer._run_concurrent_consumer_loop(loop))
    try:
        await asyncio.wait_for(entered.wait(), 10)
        # While event-loop wait is suspended, the lane is available for native observations.
        marker = await consumer._native_operations.call(lambda: native.record("control_progress"))
        assert marker is None
        assert [call[1] for call in native.calls if call[0] == "poll"] == [0.0]
        assert waits == [min(configured_timeout, 0.1)]
        assert consumer._native_operations.generation(RecordedMessage(1)) == 1
        assert not any(call[0] == "commit_ack" for call in native.calls)
    finally:
        consumer._running = False
        release_handler.set()
        release_wait.set()
        await running
    assert [call[1] for call in native.calls if call[0] == "commit_ack"] == [0]
    assert len({call[2] for call in native.calls}) == 1


async def test_active_empty_poll_real_wait_times_out_then_wakes_on_completion(composed):
    consumer, native = composed
    loop = asyncio.get_running_loop()
    release_handler = asyncio.Event()
    observations = []
    original_wait = asyncio.wait
    poll_count = 0

    async def process(_message):
        await release_handler.wait()

    def poll(timeout):
        nonlocal poll_count
        poll_count += 1
        native.record("poll", timeout)
        if poll_count == 2:
            native.callbacks["on_assign"](native, [TopicPartition("recorded", 1)])
        return None

    async def observe_wait(tasks, *, timeout, return_when):
        assert timeout == 0.1
        assert return_when == asyncio.FIRST_COMPLETED
        assert not active.done()
        if observations:
            assert poll_count == 2
            assert consumer._native_operations.generation(RecordedMessage(1)) == 1
            loop.call_soon(release_handler.set)
        # Delegate to the real asyncio wait used by the unchanged consumer helper.
        done, pending = await original_wait(tasks, timeout=timeout, return_when=return_when)
        observations.append((done, pending))
        if done:
            consumer._running = False
        return done, pending

    native.poll = poll
    consumer.process.side_effect = process
    consumer._schedule_processing_task(RecordedMessage(), loop, "partition:recorded:0")
    active = next(iter(consumer._in_flight_tasks))
    with patch("portfolio_common.kafka_consumer.asyncio.wait", side_effect=observe_wait):
        running = asyncio.create_task(consumer._run_concurrent_consumer_loop(loop))
        try:
            # Watchdog only: no hardware-dependent elapsed-time success threshold.
            await asyncio.wait_for(asyncio.shield(running), 10)
        finally:
            consumer._running = False
            release_handler.set()
            await running
    assert observations == [(set(), {active}), ({active}, set())]
    assert not active.cancelled()
    assert not consumer._in_flight_tasks
    assert [call[1] for call in native.calls if call[0] == "poll"] == [0.0, 0.0]
    assert [call[1] for call in native.calls if call[0] == "commit_ack"] == [0]
    assert len({call[2] for call in native.calls}) == 1


@pytest.mark.parametrize("error_kind", ["nonfatal", "partition_eof"])
async def test_active_nonfatal_poll_stream_keeps_other_uow_and_callbacks_responsive(
    composed, error_kind
):
    consumer, native = composed
    loop = asyncio.get_running_loop()
    first_poll, other_progress, stream_observed = (asyncio.Event() for _ in range(3))
    release_handler = asyncio.Event()
    poll_count = 0
    error_message = RecordedMessage()
    error = (
        KafkaError(KafkaError._PARTITION_EOF)
        if error_kind == "partition_eof"
        else SimpleNamespace(fatal=lambda: False)
    )
    error_message.error = lambda: error

    async def process(_message):
        await release_handler.wait()

    async def other_uow():
        await first_poll.wait()
        other_progress.set()

    def poll(timeout):
        nonlocal poll_count
        poll_count += 1
        native.record("poll", timeout)
        native.callbacks["on_assign"](native, [TopicPartition("recorded", 1)])
        loop.call_soon_threadsafe(first_poll.set)
        if poll_count >= 16:
            loop.call_soon_threadsafe(stream_observed.set)
        return error_message

    native.poll = poll
    consumer.process.side_effect = process
    consumer._schedule_processing_task(RecordedMessage(), loop, "partition:recorded:0")
    active = next(iter(consumer._in_flight_tasks))
    running = asyncio.create_task(consumer._run_concurrent_consumer_loop(loop))
    other = asyncio.create_task(other_uow())
    try:
        await asyncio.wait_for(stream_observed.wait(), 10)
        await asyncio.wait_for(other_progress.wait(), 10)
        assert not active.done()
        assert consumer._native_operations.generation(RecordedMessage(1)) >= 16
        assert all(call[1] == 0.0 for call in native.calls if call[0] == "poll")
        assert not any(call[0] == "commit_ack" for call in native.calls)
    finally:
        consumer._running = False
        release_handler.set()
        await asyncio.gather(running, other)
    assert not active.cancelled()
    assert [call[1] for call in native.calls if call[0] == "commit_ack"] == [0]
    assert len({call[2] for call in native.calls}) == 1


async def test_durable_processing_precedes_ack_and_failure_never_commits(composed):
    consumer, native = composed
    durable = asyncio.Event()

    async def process(_message):
        await durable.wait()
        native.record("durable_stub")

    consumer.process.side_effect = process
    task = asyncio.create_task(
        consumer._process_polled_message(RecordedMessage(), asyncio.get_running_loop())
    )
    await asyncio.sleep(0)  # scheduling yield; not an elapsed-time assertion
    assert not any(c[0] == "commit_enter" for c in native.calls)
    durable.set()
    await task
    names = [c[0] for c in native.calls]
    assert names.index("durable_stub") < names.index("commit_enter")
    consumer.process.side_effect = ValueError("durable failure")
    consumer._send_to_dlq_async = AsyncMock(return_value=False)
    consumer._running = False
    await consumer._process_polled_message(RecordedMessage(offset_id=1), asyncio.get_running_loop())
    assert [c[1] for c in native.calls if c[0] == "commit_ack"] == [0]


async def test_same_partition_waits_for_ack_other_partition_can_process(composed):
    consumer, native = composed
    loop = asyncio.get_running_loop()
    entered, independent = asyncio.Event(), asyncio.Event()
    release = threading.Event()

    async def process(message):
        if message.partition() == 1:
            independent.set()

    consumer.process.side_effect = process

    def commit():
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10)

    native.commit_hook = commit
    await consumer._dispatch_or_queue_message(RecordedMessage(), loop)
    await entered.wait()
    # Pause is itself serialized behind commit. Queue the second message directly
    # using the existing ordered pending buffer to inspect its admission invariant.
    key = consumer._message_ordering_key(RecordedMessage())
    consumer._pending_messages_by_key[key].append(RecordedMessage(offset_id=1))
    consumer._pending_message_count += 1
    consumer._schedule_processing_task(RecordedMessage(1, 2), loop, "partition:recorded:1")
    try:
        await independent.wait()
        assert consumer.process.await_count == 2
        assert key in consumer._active_ordering_keys
    finally:
        release.set()
        await asyncio.gather(*consumer._in_flight_tasks)
    await consumer._drain_completed_processing_tasks(loop)
    await asyncio.gather(*consumer._in_flight_tasks)
    assert [c[1] for c in native.calls if c[0] == "commit_ack"] == [0, 2, 1]


async def test_commit_failure_stops_before_later_same_partition_offset(composed):
    consumer, native = composed
    native.commit_hook = lambda: (_ for _ in ()).throw(RuntimeError("broker refusal"))
    await consumer._process_polled_message(RecordedMessage(), asyncio.get_running_loop())
    assert consumer._running is False
    assert not any(c[0] == "commit_ack" for c in native.calls)


async def test_rebalance_callback_invalidates_old_work_without_reentrant_wait(composed):
    consumer, native = composed
    loop = asyncio.get_running_loop()
    message = RecordedMessage()
    native.poll_hook = lambda: message
    assert await consumer._poll_next_message(loop) is message

    async def revoke(_message):
        await consumer._native_operations.call(
            lambda: native.callbacks["on_revoke"](native, [TopicPartition("recorded", 0)])
        )

    consumer.process.side_effect = revoke
    await consumer._process_polled_message(message, loop)
    assert consumer._running is False
    assert not any(c[0] == "commit_enter" for c in native.calls)


@pytest.mark.parametrize("commit_refused", [False, True])
async def test_cancellation_and_shutdown_join_commit_before_close(composed, commit_refused):
    consumer, native = composed
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()

    def commit():
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10)
        if commit_refused:
            raise RuntimeError("broker refused cancelled operation")

    native.commit_hook = commit
    task = asyncio.create_task(consumer._process_polled_message(RecordedMessage(), loop))
    await entered.wait()
    task.cancel()
    consumer.shutdown()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    assert not native.closed
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await consumer.wait_closed()
    names = [c[0] for c in native.calls]
    assert names.index("commit_enter") < names.index("close")
    assert ("commit_ack" in names) is not commit_refused


async def test_dlq_durability_precedes_offset_ack(composed):
    consumer, native = composed
    consumer._send_to_dlq_async = AsyncMock(return_value=True)
    await consumer._recover_message_via_dlq(RecordedMessage(), ValueError("poison"))
    consumer._send_to_dlq_async.assert_awaited_once()
    assert [c[1] for c in native.calls if c[0] == "commit_ack"] == [0]


async def test_serialized_poll_callbacks_and_close_share_worker(composed):
    consumer, native = composed
    native.poll_hook = lambda: native.callbacks["on_assign"](
        native, [TopicPartition("recorded", 0)]
    )
    await consumer._poll_next_message(asyncio.get_running_loop())
    consumer.shutdown()
    await consumer.wait_closed()
    assert len({c[2] for c in native.calls}) == 1
    assert native.closed


async def test_cancelled_initialization_retains_and_closes_created_handle():
    native = RecordingConsumer()
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    original_subscribe = native.subscribe

    def subscribe(topics, **callbacks):
        original_subscribe(topics, **callbacks)
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10)

    native.subscribe = subscribe
    with patch("portfolio_common.kafka_consumer.Consumer", return_value=native):
        consumer = ComposedConsumer()
        running = asyncio.create_task(consumer.run())
        await entered.wait()
        running.cancel()
        await asyncio.sleep(0)
        assert not running.done()
        assert not native.closed
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await running
    assert [c[0] for c in native.calls] == ["subscribe", "close"]
    assert len({c[2] for c in native.calls}) == 1
    with pytest.raises(RuntimeError, match="lane is closed"):
        await consumer._native_operations.call(lambda: None)


async def test_shutdown_close_failure_is_not_reported_as_success(composed):
    consumer, native = composed
    native.close = lambda: (_ for _ in ()).throw(RuntimeError("close refused"))
    with patch.object(consumer, "_log_consumer_event") as log:
        consumer.shutdown()
        await consumer.wait_closed()
    completed = [
        c.kwargs
        for c in log.call_args_list
        if c.kwargs.get("event_name") == "kafka.consumer.shutdown_completed"
    ]
    assert len(completed) == 1
    assert completed[0]["status"] == "failed"
    assert completed[0]["reason_code"] == "resource_release_failed"
    assert not native.closed


@pytest.mark.parametrize("failure_stage", ["construct", "subscribe"])
async def test_initialization_failure_releases_only_created_handle(failure_stage):
    native = RecordingConsumer()

    def subscribe(topics, **callbacks):
        native.record("subscribe_failed")
        raise RuntimeError("subscribe refused")

    native.subscribe = subscribe
    with patch("portfolio_common.kafka_consumer.Consumer", return_value=native) as factory:
        if failure_stage == "construct":
            factory.side_effect = RuntimeError("construction refused")
        consumer = ComposedConsumer()
        with pytest.raises(RuntimeError, match="refused"):
            await consumer.run()
    assert [c[0] for c in native.calls].count("close") == (failure_stage == "subscribe")
    with pytest.raises(RuntimeError, match="lane is closed"):
        await consumer._native_operations.call(lambda: None)


async def test_running_consumer_shutdown_waits_for_ack_before_close(composed):
    consumer, native = composed
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    messages = iter([RecordedMessage()])
    native.poll_hook = lambda: next(messages, None)

    def commit():
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10)

    native.commit_hook = commit
    running = asyncio.create_task(consumer.run())
    await entered.wait()
    consumer.shutdown()
    closing = asyncio.create_task(consumer.wait_closed())
    await asyncio.sleep(0)
    assert not closing.done()
    assert not native.closed
    release.set()
    await asyncio.gather(running, closing)
    names = [c[0] for c in native.calls]
    assert names.index("commit_ack") < names.index("close")
    assert names.count("close") == 1


@pytest.mark.parametrize(
    "result_kind",
    ["none", "empty", "duplicate", "error", "topic", "partition", "offset", "malformed"],
)
async def test_inexact_or_failed_partition_ack_stops_redelivery_gap(composed, result_kind):
    consumer, native = composed
    partition = SimpleNamespace(topic="recorded", partition=0, offset=1, error=None)
    result = [partition]
    if result_kind == "none":
        result = None
    elif result_kind == "empty":
        result = []
    elif result_kind == "duplicate":
        result = [partition, partition]
    elif result_kind == "error":
        partition.error = RuntimeError("partition refused")
    elif result_kind == "topic":
        partition.topic = "other"
    elif result_kind == "partition":
        partition.partition = 1
    elif result_kind == "offset":
        partition.offset = 2
    elif result_kind == "malformed":
        result = [object()]
    native.commit = lambda **_kwargs: result
    await consumer._process_polled_message(RecordedMessage(), asyncio.get_running_loop())
    assert consumer._running is False
    consumer.process.assert_awaited_once()
    assert not any(c[0] == "watermark" for c in native.calls)


@pytest.mark.parametrize("latched_phase", ["poll", "commit", "close"])
async def test_actual_worker_supervision_joins_native_work_after_deadline(
    monkeypatch, latched_phase
):
    native = RecordingConsumer()
    loop = asyncio.get_running_loop()
    entered, deadline = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    shutdown, auxiliary_stop = asyncio.Event(), asyncio.Event()
    tasks = []

    def latch():
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10)

    if latched_phase == "poll":
        native.poll_hook = latch
    elif latched_phase == "commit":
        messages = iter([RecordedMessage()])
        native.poll_hook = lambda: next(messages, None)
        native.commit_hook = latch
    else:
        native.poll_hook = lambda: loop.call_soon_threadsafe(shutdown.set) and None
        native.close_hook = latch

    original_gather = runtime_supervision._gather_runtime_tasks

    async def expired_deadline(runtime_tasks, _configured_timeout):
        # Exercise the actual deadline-cancellation branch deterministically.
        # Production budgets and their validation are unchanged.
        deadline.set()
        await original_gather(runtime_tasks, 0)

    monkeypatch.setattr(runtime_supervision, "_gather_runtime_tasks", expired_deadline)

    async def auxiliary_run():
        await auxiliary_stop.wait()

    dispatcher = SimpleNamespace(
        run=auxiliary_run,
        stop=auxiliary_stop.set,
        shutdown_timeout_seconds=1,
        termination_grace_seconds=60,
    )
    server = SimpleNamespace(serve=auxiliary_run, should_exit=False)
    with patch("portfolio_common.kafka_consumer.Consumer", return_value=native):
        consumer = ComposedConsumer()
        runtime = asyncio.create_task(
            worker_runtime.run_kafka_worker_runtime(
                consumers=[consumer],
                dispatcher=dispatcher,
                web_app=object(),
                web_port=8080,
                readiness_service_name="recording_worker",
                shutdown_event=shutdown,
                signal_handler=lambda *_args: None,
                tasks=tasks,
                logger=logging.getLogger("recording_worker"),
                ensure_topics=lambda _topics: None,
                signal_module=SimpleNamespace(SIGINT=2, SIGTERM=15, signal=lambda *_args: None),
                server_config_factory=lambda *_args, **_kwargs: None,
                server_factory=lambda _config: server,
            )
        )
        try:
            await entered.wait()
            shutdown.set()
            await deadline.wait()
            await asyncio.sleep(0)
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.sleep(0)
            for task in tasks:
                if not task.done():
                    task.cancel()
            assert not runtime.done()
            assert not native.closed
        finally:
            release.set()
            await runtime
    assert native.closed
    assert [c[0] for c in native.calls].count("close") == 1
    assert all(task.done() for task in tasks)


async def test_supervision_joins_standalone_shutdown_without_run_task(composed):
    consumer, native = composed
    await runtime_supervision.shutdown_runtime_components(tasks=[], consumers=[consumer])
    assert native.closed


@pytest.mark.parametrize("max_in_flight", [1, 2])
@pytest.mark.parametrize("returned_message", [None, RecordedMessage()])
async def test_shutdown_during_poll_refuses_new_admission(
    monkeypatch, max_in_flight, returned_message
):
    monkeypatch.setenv("ENVIRONMENT", "test")
    native = RecordingConsumer()
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()

    def pending_poll():
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(10), "recording deadlock watchdog"
        return returned_message

    native.poll_hook = pending_poll
    with patch("portfolio_common.kafka_consumer.Consumer", return_value=native):
        consumer = ComposedConsumer()
        consumer.execution_profile = KafkaConsumerExecutionProfile(
            max_in_flight_messages=max_in_flight
        )
        running = asyncio.create_task(consumer.run())
        try:
            await entered.wait()
            consumer.shutdown()
            release.set()
            await running
            consumer.process.assert_not_awaited()
            assert not any(call[0] == "commit_enter" for call in native.calls)
            assert not consumer._message_assignment_generations
            assert native.closed
            assert [call[0] for call in native.calls].count("close") == 1
            assert consumer._native_operations._closed
        finally:
            release.set()
            if not running.done():
                consumer.shutdown()
                await running
            await consumer.wait_closed()
