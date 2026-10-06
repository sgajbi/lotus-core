"""Own serialized native consumer calls without blocking the asyncio loop."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import Lock
from typing import TypeVar

from confluent_kafka import Consumer, Message, TopicPartition

_Result = TypeVar("_Result")


async def join_owned_operation(future: asyncio.Future[_Result]) -> _Result:
    """Reconcile owned work before propagating cancellation of its waiter."""
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(future)
            break
        except asyncio.CancelledError:
            if future.cancelled():
                raise
            cancelled = True
        except BaseException:
            if cancelled:
                raise asyncio.CancelledError from None
            raise
    if cancelled:
        raise asyncio.CancelledError
    return result


class PartitionOwnershipLost(RuntimeError):
    """A message's assignment ended before its durable offset acknowledgement."""


class OffsetAcknowledgementFailed(RuntimeError):
    """The native result did not acknowledge exactly the processed message offset."""


class ConsumerNativeOperations:
    """One FIFO worker owns poll, control, acknowledged commit and close calls.

    Rebalance callbacks execute on this worker and only update short-lived state;
    they never submit another operation or wait for an asyncio task.
    """

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kafka-consumer")
        self._lock = Lock()
        self._generations: dict[tuple[str, int], int] = {}
        self._closed = False

    async def call(self, operation: Callable[[], _Result]) -> _Result:
        if self._closed:
            raise RuntimeError("Native consumer operation lane is closed")
        future = asyncio.wrap_future(self._executor.submit(copy_context().run, operation))
        return await join_owned_operation(future)

    def generation(self, message: Message) -> int:
        with self._lock:
            return self._generations.get((message.topic(), message.partition()), 0)

    def on_assignment(self, _consumer: Consumer, partitions: list[TopicPartition]) -> None:
        self._invalidate(partitions)

    def on_revocation(self, _consumer: Consumer, partitions: list[TopicPartition]) -> None:
        self._invalidate(partitions)

    def _invalidate(self, partitions: list[TopicPartition]) -> None:
        with self._lock:
            for partition in partitions:
                key = (partition.topic, partition.partition)
                self._generations[key] = self._generations.get(key, 0) + 1

    async def commit(self, consumer: Consumer, message: Message, generation: int) -> None:
        def acknowledge() -> None:
            if self.generation(message) != generation:
                raise PartitionOwnershipLost("Partition assignment changed during processing")
            result = consumer.commit(message=message, asynchronous=False)
            if not isinstance(result, list) or len(result) != 1:
                raise OffsetAcknowledgementFailed("Missing exact partition acknowledgement")
            partition = result[0]
            expected = (message.topic(), message.partition(), message.offset() + 1)
            if (
                getattr(partition, "error", True) is not None
                or (
                    getattr(partition, "topic", None),
                    getattr(partition, "partition", None),
                    getattr(partition, "offset", None),
                )
                != expected
            ):
                raise OffsetAcknowledgementFailed("Partition offset acknowledgement failed")
            if self.generation(message) != generation:
                raise PartitionOwnershipLost("Assignment changed during offset acknowledgement")

        await self.call(acknowledge)

    def finish(self) -> None:
        """Release the worker only after the awaited close operation has drained it."""
        self._closed = True
        self._executor.shutdown(wait=False)
