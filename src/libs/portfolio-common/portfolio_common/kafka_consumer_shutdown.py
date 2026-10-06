"""Shared consumer resource ownership and cancellation-aware drain."""

import asyncio
import functools
import logging
from abc import abstractmethod
from collections import deque

from confluent_kafka import Consumer, Message, TopicPartition

from .kafka_consumer_execution import KafkaConsumerExecutionProfile
from .kafka_consumer_native import ConsumerNativeOperations, join_owned_operation
from .kafka_utils import KafkaProducer


class ConsumerShutdownMixin:
    """Drain accepted work before retiring the consumer's serialized native lane."""

    _consumer: Consumer | None
    _producer: KafkaProducer | None
    _native_operations: ConsumerNativeOperations
    _shutdown_finalized: bool
    _shutdown_started: bool
    _run_active: bool
    _running: bool
    _shutdown_task: asyncio.Task[None] | None
    _run_finished: asyncio.Event
    execution_profile: KafkaConsumerExecutionProfile
    _in_flight_tasks: set[asyncio.Task[None]]
    _in_flight_task_keys: dict[asyncio.Task[None], str]
    _active_ordering_keys: set[str]
    _pending_messages_by_key: dict[str, deque[Message]]
    _pending_message_count: int
    _message_assignment_generations: dict[int, int]
    _paused_partitions_by_key: dict[str, TopicPartition]

    @abstractmethod
    def _record_consumer_event(self, outcome: str, reason: str) -> None:
        """Record bounded lifecycle telemetry on the event loop."""

    @abstractmethod
    def _log_consumer_event(
        self,
        level: int,
        message: str,
        *,
        event_name: str,
        status: str,
        reason_code: str,
        exc_info: bool = False,
        **fields: object,
    ) -> None:
        """Log source-safe lifecycle evidence on the event loop."""

    @abstractmethod
    async def _resume_ordering_partition(self, ordering_key: str) -> None:
        """Resume through the owned native lane after application work drains."""

    @abstractmethod
    def _set_in_flight_metric(self) -> None:
        """Publish the current application task count."""

    async def _drain_in_flight_on_shutdown(self, loop: asyncio.AbstractEventLoop) -> None:
        if not self._in_flight_tasks:
            return
        _, pending = await asyncio.wait(
            self._in_flight_tasks,
            timeout=self.execution_profile.shutdown_drain_timeout_seconds,
        )
        if pending:
            self._record_consumer_event("shutdown_failed", "in_flight_drain_timeout")
            for task in pending:
                task.cancel()
        # Native acknowledgement cannot be forcibly cancelled. Join before close;
        # cancelled application work unwinds its UOW before its task completes.
        results = await asyncio.gather(*self._in_flight_tasks, return_exceptions=True)
        self._in_flight_tasks.clear()
        self._in_flight_task_keys.clear()
        self._active_ordering_keys.clear()
        self._pending_messages_by_key.clear()
        self._pending_message_count = 0
        self._message_assignment_generations.clear()
        for ordering_key in list(self._paused_partitions_by_key):
            await self._resume_ordering_partition(ordering_key)
        self._set_in_flight_metric()
        for result in results:
            if isinstance(result, Exception):
                raise result

    def shutdown(self) -> None:
        """Stop polling, drain active work, and then release Kafka resources."""
        if self._shutdown_finalized:
            return
        self._start_shutdown()
        if self._run_active:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.wait_closed())
        else:
            if self._shutdown_task is None:
                self._shutdown_task = loop.create_task(self._finalize_shutdown())

    async def wait_closed(self) -> None:
        """Await resource release after processing/native operations have drained."""
        if self._run_active:
            await self._run_finished.wait()
            return
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(self._finalize_shutdown())
        await join_owned_operation(self._shutdown_task)

    def _start_shutdown(self) -> None:
        if self._shutdown_started:
            return
        self._shutdown_started = True
        self._log_consumer_event(
            logging.INFO,
            "Kafka consumer shutdown started.",
            event_name="kafka.consumer.shutdown_started",
            status="started",
            reason_code="consumer_shutdown_started",
        )
        self._running = False

    async def _finalize_shutdown(self) -> None:
        if self._shutdown_finalized:
            return
        consumer_closed = await self._close_consumer_for_shutdown()
        producer_flushed = await self._flush_dlq_producer_for_shutdown()
        self._native_operations.finish()
        self._shutdown_finalized = True
        self._log_consumer_event(
            logging.INFO,
            "Kafka consumer shutdown resource release finished.",
            event_name="kafka.consumer.shutdown_completed",
            status="succeeded" if consumer_closed and producer_flushed else "failed",
            reason_code=(
                "consumer_shutdown_completed"
                if consumer_closed and producer_flushed
                else "resource_release_failed"
            ),
        )

    async def _close_consumer_for_shutdown(self) -> bool:
        if self._consumer is None:
            return True
        try:
            await self._native_operations.call(self._consumer.close)
            return True
        except Exception:
            self._record_consumer_event("shutdown_failed", "consumer_close")
            self._log_consumer_event(
                logging.ERROR,
                "Consumer close failed during shutdown.",
                event_name="kafka.consumer.shutdown_failed",
                status="failed",
                reason_code="consumer_close",
                exc_info=True,
            )
            return False

    async def _flush_dlq_producer_for_shutdown(self) -> bool:
        if self._producer is None:
            return True
        try:
            undelivered_count = await self._native_operations.call(
                functools.partial(self._producer.flush, timeout=5)
            )
            if undelivered_count:
                self._record_consumer_event("shutdown_failed", "dlq_flush_undelivered")
                self._log_consumer_event(
                    logging.ERROR,
                    "DLQ producer flush left undelivered messages during shutdown.",
                    event_name="kafka.consumer.shutdown_failed",
                    status="failed",
                    reason_code="dlq_flush_undelivered",
                    undelivered_count=undelivered_count,
                )
            return not undelivered_count
        except Exception:
            self._record_consumer_event("shutdown_failed", "dlq_flush")
            self._log_consumer_event(
                logging.ERROR,
                "DLQ producer flush failed during shutdown.",
                event_name="kafka.consumer.shutdown_failed",
                status="failed",
                reason_code="dlq_flush",
                exc_info=True,
            )
            return False
