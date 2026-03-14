# src/libs/portfolio-common/portfolio_common/kafka_consumer.py
import asyncio
import functools
import inspect
import logging
import time
import traceback
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional
from uuid import uuid4

from confluent_kafka import Consumer, Message

from .config import get_kafka_consumer_runtime_overrides
from .database_models import ConsumerDlqEvent
from .db import get_async_db_session
from .exceptions import RetryableConsumerError
from .kafka_utils import get_kafka_producer
from .logging_utils import correlation_id_var, generate_correlation_id, normalize_lineage_value

logger = logging.getLogger(__name__)

DLQ_REASON_CODE_VALIDATION = "VALIDATION_ERROR"
DLQ_REASON_CODE_DESERIALIZATION = "DESERIALIZATION_ERROR"
DLQ_REASON_CODE_DATA_INTEGRITY = "DATA_INTEGRITY_ERROR"
DLQ_REASON_CODE_DOWNSTREAM_TIMEOUT = "DOWNSTREAM_TIMEOUT"
DLQ_REASON_CODE_AUTHORIZATION = "AUTHORIZATION_ERROR"
DLQ_REASON_CODE_UNCLASSIFIED = "UNCLASSIFIED_PROCESSING_ERROR"


def classify_dlq_reason_code(error: Exception) -> str:
    """
    Maps terminal consumer exceptions into a deterministic reason-code taxonomy.
    """
    error_name = error.__class__.__name__.lower()
    error_text = str(error).lower()
    combined = f"{error_name}:{error_text}"

    if "json" in combined and any(
        token in combined for token in ("decode", "deserialize", "parsing")
    ):
        return DLQ_REASON_CODE_DESERIALIZATION
    if any(
        token in combined
        for token in (
            "validation",
            "missing",
            "required",
            "invalid",
            "schema",
            "keyerror",
            "valueerror",
            "typeerror",
        )
    ):
        return DLQ_REASON_CODE_VALIDATION
    if any(
        token in combined
        for token in ("integrity", "foreign key", "constraint", "unique violation", "duplicate key")
    ):
        return DLQ_REASON_CODE_DATA_INTEGRITY
    if any(token in combined for token in ("timeout", "timed out", "deadline exceeded")):
        return DLQ_REASON_CODE_DOWNSTREAM_TIMEOUT
    if any(
        token in combined
        for token in ("permission", "forbidden", "unauthorized", "access denied", "auth")
    ):
        return DLQ_REASON_CODE_AUTHORIZATION
    return DLQ_REASON_CODE_UNCLASSIFIED


class BaseConsumer(ABC):
    """
    An abstract base class for creating robust, retrying Kafka consumers
    with Dead-Letter Queue (DLQ) support and Prometheus metrics.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        dlq_topic: Optional[str] = None,
        service_prefix: str = "SVC",
        metrics: Optional[Dict] = None,
    ):
        self.topic = topic
        self.dlq_topic = dlq_topic
        self.service_prefix = service_prefix
        self._metrics = metrics
        self._consumer = None
        self._producer = None
        self._consumer_config = {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            "session.timeout.ms": 30000,
            "heartbeat.interval.ms": 3000,
        }
        runtime_overrides = get_kafka_consumer_runtime_overrides(group_id)
        if runtime_overrides:
            self._consumer_config.update(runtime_overrides)
            logger.info(
                "Applied Kafka consumer runtime overrides.",
                extra={"group_id": group_id, "override_keys": sorted(runtime_overrides.keys())},
            )
        self._running = True

        if self.dlq_topic:
            self._producer = get_kafka_producer()
            logger.info(
                "DLQ enabled for consumer of topic "
                f"'{self.topic}'. Failing messages will be sent "
                f"to '{self.dlq_topic}'."
            )

    def _initialize_consumer(self):
        """Initializes and subscribes the Kafka consumer."""
        logger.info(
            "Initializing consumer for topic "
            f"'{self.topic}' with group "
            f"'{self._consumer_config['group.id']}'..."
        )
        self._consumer = Consumer(self._consumer_config)
        self._consumer.subscribe([self.topic])
        logger.info(f"Consumer successfully subscribed to topic '{self.topic}'.")

    def _resolve_message_correlation_id(self, msg: Message) -> str:
        """
        Resolve the message correlation id from Kafka headers, falling back to a
        generated service-scoped id when no header is present.
        """
        corr_id = self._get_message_header_correlation_id(msg)
        if not corr_id:
            corr_id = generate_correlation_id(self.service_prefix)
            logger.warning(
                "No correlation ID in message from topic "
                f"'{msg.topic()}'. Generated new ID: {corr_id}"
            )

        return corr_id

    def _get_message_header_correlation_id(self, msg: Message) -> Optional[str]:
        """Return the Kafka header correlation id when present."""
        corr_id = None
        if msg.headers():
            for key, value in msg.headers():
                if key == "correlation_id":
                    corr_id = value.decode("utf-8") if value else None
                    break

        return corr_id

    @contextmanager
    def _message_correlation_context(
        self,
        msg: Message,
        fallback_correlation_id: Optional[str] = None,
        *,
        prefer_fallback: bool = False,
    ) -> Iterator[str]:
        """
        Ensure a message-scoped correlation id is present for direct
        ``process_message(...)`` invocation paths that bypass ``run()``.
        """
        current = correlation_id_var.get()
        token = None
        resolved = current
        if normalize_lineage_value(current) is None:
            header_correlation_id = self._get_message_header_correlation_id(msg)
            if prefer_fallback and fallback_correlation_id:
                resolved = fallback_correlation_id
            elif header_correlation_id:
                resolved = header_correlation_id
            elif fallback_correlation_id:
                resolved = fallback_correlation_id
            else:
                resolved = self._resolve_message_correlation_id(msg)
            token = correlation_id_var.set(resolved)

        try:
            yield resolved
        finally:
            if token is not None:
                correlation_id_var.reset(token)

    async def _send_to_dlq_async(self, msg: Message, error: Exception) -> bool:
        """
        Sends a message that failed processing to the Dead-Letter Queue.
        """
        if self._metrics:
            self._metrics["dlqd"].labels(
                topic=self.topic, consumer_group=self._consumer_config["group.id"]
            ).inc()

        if not self._producer or not self.dlq_topic:
            return False

        try:
            correlation_id = normalize_lineage_value(correlation_id_var.get())
            error_reason_code = classify_dlq_reason_code(error)

            dlq_payload = {
                "correlation_id": correlation_id,
                "original_topic": msg.topic(),
                "original_key": msg.key().decode("utf-8") if msg.key() else None,
                "original_value": msg.value().decode("utf-8"),
                "error_timestamp": datetime.now(timezone.utc).isoformat(),
                "error_reason_code": error_reason_code,
                "error_reason": str(error),
                "error_traceback": traceback.format_exc(),
            }

            dlq_headers = msg.headers() or []
            if correlation_id:
                dlq_headers.append(("correlation_id", correlation_id.encode("utf-8")))

            self._producer.publish_message(
                topic=self.dlq_topic,
                key=msg.key().decode("utf-8") if msg.key() else "NoKey",
                value=dlq_payload,
                headers=dlq_headers,
            )
            undelivered_count = self._producer.flush(timeout=5)
            if undelivered_count:
                raise RuntimeError(
                    "DLQ delivery confirmation timed out before Kafka acknowledged the message."
                )
            await self._record_consumer_dlq_event(
                msg=msg,
                error=error,
                error_reason_code=error_reason_code,
                correlation_id=correlation_id,
            )
            logger.warning(
                f"Message with key '{dlq_payload['original_key']}' sent to DLQ '{self.dlq_topic}'."
            )
            return True
        except Exception as e:
            logger.error(f"FATAL: Could not send message to DLQ. Error: {e}", exc_info=True)
            return False

    async def _record_consumer_dlq_event(
        self,
        msg: Message,
        error: Exception,
        error_reason_code: str,
        correlation_id: str | None,
    ) -> None:
        payload_excerpt = None
        try:
            raw_value = msg.value().decode("utf-8")
            payload_excerpt = raw_value[:1500]
        except Exception:
            payload_excerpt = None
        event = ConsumerDlqEvent(
            event_id=f"cdlq_{uuid4().hex}",
            original_topic=msg.topic(),
            consumer_group=self._consumer_config["group.id"],
            dlq_topic=self.dlq_topic or "",
            original_key=msg.key().decode("utf-8") if msg.key() else None,
            error_reason_code=error_reason_code,
            error_reason=str(error),
            correlation_id=correlation_id,
            payload_excerpt=payload_excerpt,
        )
        async for db in get_async_db_session():
            async with db.begin():
                db.add(event)
            break

    @abstractmethod
    def process_message(self, msg: Message):
        """
        Abstract method to be implemented by subclasses. Can be sync or async.
        """
        pass

    async def run(self):
        """
        The main consumer loop. Polls for messages, processes them, handles errors,
        and commits offsets.
        """
        self._initialize_consumer()
        loop = asyncio.get_running_loop()
        logger.info(f"Starting to consume messages from topic '{self.topic}'...")
        while self._running:
            msg = await loop.run_in_executor(None, self._consumer.poll, 1.0)

            if msg is None:
                continue
            if msg.error():
                if msg.error().fatal():
                    logger.error(
                        f"Fatal consumer error on topic {self.topic}: "
                        f"{msg.error()}. Shutting down.",
                        exc_info=True,
                    )
                    break
                else:
                    logger.warning(
                        f"Non-fatal consumer error on topic {self.topic}: {msg.error()}."
                    )
                    continue

            token = None
            start_time = time.monotonic()
            processed_successfully = False
            try:
                corr_id = self._resolve_message_correlation_id(msg)
                token = correlation_id_var.set(corr_id)

                if inspect.iscoroutinefunction(self.process_message):
                    await self.process_message(msg)
                else:
                    await loop.run_in_executor(None, functools.partial(self.process_message, msg))

            except RetryableConsumerError as e:
                # For transient errors, we log and do NOT commit, allowing Kafka to redeliver.
                logger.warning(
                    f"Retryable error occurred: {e}. Offset will not be committed.", exc_info=False
                )

            except Exception as e:
                # For terminal errors (poison pills), we send to DLQ and then commit.
                logger.error(
                    f"Terminal error processing message for topic {self.topic}: {e}", exc_info=True
                )
                dlq_succeeded = await self._send_to_dlq_async(msg, e)
                if dlq_succeeded:
                    try:
                        self._consumer.commit(message=msg, asynchronous=False)
                    except Exception as commit_error:
                        logger.warning(
                            (
                                "Offset commit failed after successful DLQ publication; "
                                "offset will not be committed so Kafka can redeliver."
                            ),
                            exc_info=True,
                            extra={
                                "topic": self.topic,
                                "consumer_group": self._consumer_config["group.id"],
                                "message_key": msg.key().decode("utf-8") if msg.key() else None,
                                "commit_error": str(commit_error),
                            },
                        )
                else:
                    logger.warning(
                        (
                            "DLQ publication failed; offset will not be committed "
                            "so Kafka can redeliver."
                        ),
                        extra={
                            "topic": self.topic,
                            "consumer_group": self._consumer_config["group.id"],
                            "message_key": msg.key().decode("utf-8") if msg.key() else None,
                        },
                    )
            else:
                try:
                    self._consumer.commit(message=msg, asynchronous=False)
                    processed_successfully = True
                except Exception as e:
                    logger.warning(
                        (
                            "Offset commit failed after successful processing; "
                            "offset will not be committed so Kafka can redeliver."
                        ),
                        exc_info=True,
                        extra={
                            "topic": self.topic,
                            "consumer_group": self._consumer_config["group.id"],
                            "message_key": msg.key().decode("utf-8") if msg.key() else None,
                            "commit_error": str(e),
                        },
                    )

            finally:
                duration = time.monotonic() - start_time
                if self._metrics:
                    labels = {
                        "topic": self.topic,
                        "consumer_group": self._consumer_config["group.id"],
                    }
                    self._metrics["latency"].labels(**labels).observe(duration)
                    if processed_successfully:
                        self._metrics["processed"].labels(**labels).inc()

                if token:
                    correlation_id_var.reset(token)

        self.shutdown()

    def shutdown(self):
        """Gracefully shuts down the consumer."""
        logger.info(f"Shutting down consumer for topic '{self.topic}'...")
        self._running = False
        if self._consumer:
            self._consumer.close()
        if self._producer:
            self._producer.flush()
        logger.info(f"Consumer for topic '{self.topic}' has been closed.")
