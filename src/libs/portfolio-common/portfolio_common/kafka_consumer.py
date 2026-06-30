# src/libs/portfolio-common/portfolio_common/kafka_consumer.py
import asyncio
import functools
import inspect
import json
import logging
import time
import traceback
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional
from uuid import uuid4

from confluent_kafka import Consumer, Message
from pydantic import ValidationError

from .config import get_kafka_consumer_runtime_overrides
from .database_models import ConsumerDlqEvent
from .db import get_async_db_session
from .exceptions import RetryableConsumerError
from .kafka_utils import get_kafka_producer
from .logging_utils import (
    REDACTED_VALUE,
    correlation_id_var,
    generate_correlation_id,
    normalize_lineage_value,
    redact_sensitive,
    redact_sensitive_text,
)

logger = logging.getLogger(__name__)

DLQ_REASON_CODE_VALIDATION = "VALIDATION_ERROR"
DLQ_REASON_CODE_DESERIALIZATION = "DESERIALIZATION_ERROR"
DLQ_REASON_CODE_DATA_INTEGRITY = "DATA_INTEGRITY_ERROR"
DLQ_REASON_CODE_DOWNSTREAM_TIMEOUT = "DOWNSTREAM_TIMEOUT"
DLQ_REASON_CODE_AUTHORIZATION = "AUTHORIZATION_ERROR"
DLQ_REASON_CODE_UNCLASSIFIED = "UNCLASSIFIED_PROCESSING_ERROR"
_DLQ_DESERIALIZATION_TOKENS = ("decode", "deserialize", "parsing")
_DLQ_REASON_TOKEN_GROUPS = (
    (
        DLQ_REASON_CODE_VALIDATION,
        (
            "validation",
            "missing",
            "required",
            "invalid",
            "schema",
            "keyerror",
            "valueerror",
            "typeerror",
        ),
    ),
    (
        DLQ_REASON_CODE_DATA_INTEGRITY,
        ("integrity", "foreign key", "constraint", "unique violation", "duplicate key"),
    ),
    (
        DLQ_REASON_CODE_DOWNSTREAM_TIMEOUT,
        ("timeout", "timed out", "deadline exceeded"),
    ),
    (
        DLQ_REASON_CODE_AUTHORIZATION,
        ("permission", "forbidden", "unauthorized", "access denied", "auth"),
    ),
)
_DLQ_SENSITIVE_HEADER_TOKENS = (
    "authorization",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "database_url",
    "connection_string",
    "credential",
)


def classify_dlq_reason_code(error: Exception) -> str:
    """
    Maps terminal consumer exceptions into a deterministic reason-code taxonomy.
    """
    combined = _combined_error_text(error)
    if "json" in combined and _contains_any_token(combined, _DLQ_DESERIALIZATION_TOKENS):
        return DLQ_REASON_CODE_DESERIALIZATION
    for reason_code, tokens in _DLQ_REASON_TOKEN_GROUPS:
        if _contains_any_token(combined, tokens):
            return reason_code
    return DLQ_REASON_CODE_UNCLASSIFIED


def _combined_error_text(error: Exception) -> str:
    error_name = error.__class__.__name__.lower()
    error_text = str(error).lower()
    return f"{error_name}:{error_text}"


def _contains_any_token(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _redacted_payload_text(raw_value: str) -> str:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return redact_sensitive_text(raw_value)
    redacted = redact_sensitive(parsed)
    if redacted == parsed:
        return raw_value
    return json.dumps(redacted, separators=(",", ":"), sort_keys=True)


def _source_safe_error_reason(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return json.dumps(
            error.errors(include_input=False),
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        )
    return redact_sensitive_text(str(error))


def _message_attr_or_unknown(msg: Message, attr_name: str) -> str:
    try:
        value = getattr(msg, attr_name)()
    except Exception:
        return "unknown"
    return str(value) if value is not None else "unknown"


def _source_safe_error_traceback(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return f"{error.__class__.__name__}: {_source_safe_error_reason(error)}"
    return redact_sensitive_text(traceback.format_exc())


def _redacted_dlq_header(header: tuple[str, bytes | None]) -> tuple[str, bytes]:
    key, value = header
    if _is_sensitive_dlq_header(key):
        return key, REDACTED_VALUE.encode("utf-8")
    if value is None:
        return key, b""
    try:
        return key, redact_sensitive_text(value.decode("utf-8")).encode("utf-8")
    except UnicodeDecodeError:
        return key, value


def _is_sensitive_dlq_header(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return any(token in normalized for token in _DLQ_SENSITIVE_HEADER_TOKENS)


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
        resolved = self._resolve_context_correlation_id(
            msg,
            current,
            fallback_correlation_id=fallback_correlation_id,
            prefer_fallback=prefer_fallback,
        )
        if normalize_lineage_value(current) is None:
            token = correlation_id_var.set(resolved)

        try:
            yield resolved
        finally:
            if token is not None:
                correlation_id_var.reset(token)

    def _resolve_context_correlation_id(
        self,
        msg: Message,
        current: str,
        *,
        fallback_correlation_id: Optional[str],
        prefer_fallback: bool,
    ) -> str:
        if normalize_lineage_value(current) is not None:
            return current
        header_correlation_id = self._get_message_header_correlation_id(msg)
        return self._select_context_correlation_id(
            msg,
            header_correlation_id=header_correlation_id,
            fallback_correlation_id=fallback_correlation_id,
            prefer_fallback=prefer_fallback,
        )

    def _select_context_correlation_id(
        self,
        msg: Message,
        *,
        header_correlation_id: Optional[str],
        fallback_correlation_id: Optional[str],
        prefer_fallback: bool,
    ) -> str:
        if prefer_fallback and fallback_correlation_id:
            return fallback_correlation_id
        if header_correlation_id:
            return header_correlation_id
        if fallback_correlation_id:
            return fallback_correlation_id
        return self._resolve_message_correlation_id(msg)

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
            message_correlation_id = normalize_lineage_value(
                self._get_message_header_correlation_id(msg)
            )
            error_reason_code = classify_dlq_reason_code(error)
            dlq_payload = self._build_dlq_payload(
                msg,
                error,
                error_reason_code=error_reason_code,
                correlation_id=correlation_id,
            )
            dlq_headers = self._build_dlq_headers(msg, correlation_id=correlation_id)
            self._publish_dlq_message(msg, payload=dlq_payload, headers=dlq_headers)
            self._confirm_dlq_delivery()
            await self._record_consumer_dlq_event(
                msg=msg,
                error=error,
                error_reason_code=error_reason_code,
                correlation_id=message_correlation_id,
            )
            logger.warning(
                f"Message with key '{dlq_payload['original_key']}' sent to DLQ '{self.dlq_topic}'."
            )
            return True
        except Exception as e:
            logger.error(f"FATAL: Could not send message to DLQ. Error: {e}", exc_info=True)
            return False

    def _build_dlq_payload(
        self,
        msg: Message,
        error: Exception,
        *,
        error_reason_code: str,
        correlation_id: str | None,
    ) -> dict[str, object]:
        return {
            "correlation_id": correlation_id,
            "original_topic": msg.topic(),
            "original_key": self._message_key_text(msg),
            "original_value": self._redacted_message_value_text(msg),
            "error_timestamp": datetime.now(timezone.utc).isoformat(),
            "error_reason_code": error_reason_code,
            "error_reason": _source_safe_error_reason(error),
            "error_traceback": _source_safe_error_traceback(error),
        }

    def _build_dlq_headers(
        self,
        msg: Message,
        *,
        correlation_id: str | None,
    ) -> list[tuple[str, bytes]]:
        dlq_headers = [_redacted_dlq_header(header) for header in msg.headers() or []]
        if correlation_id:
            dlq_headers.append(("correlation_id", correlation_id.encode("utf-8")))
        return dlq_headers

    def _publish_dlq_message(
        self,
        msg: Message,
        *,
        payload: dict[str, object],
        headers: list[tuple[str, bytes]],
    ) -> None:
        if self._producer is None or self.dlq_topic is None:
            raise RuntimeError("DLQ producer is unavailable.")
        self._producer.publish_message(
            topic=self.dlq_topic,
            key=self._message_key_text(msg) or "NoKey",
            value=payload,
            headers=headers,
        )

    def _confirm_dlq_delivery(self) -> None:
        if self._producer is None:
            raise RuntimeError("DLQ producer is unavailable.")
        undelivered_count = self._producer.flush(timeout=5)
        if undelivered_count:
            raise RuntimeError(
                "DLQ delivery confirmation timed out before Kafka acknowledged the message."
            )

    def _message_key_text(self, msg: Message) -> str | None:
        key = msg.key()
        return key.decode("utf-8") if key else None

    def _redacted_message_value_text(self, msg: Message) -> str:
        raw_value = msg.value().decode("utf-8")
        return _redacted_payload_text(raw_value)

    def _consumer_dlq_alternate_lookup_key(self, msg: Message) -> str:
        original_key = self._message_key_text(msg) or "unkeyed"
        partition = _message_attr_or_unknown(msg, "partition")
        offset = _message_attr_or_unknown(msg, "offset")
        return (
            f"consumer_dlq|topic={msg.topic()}|group={self._consumer_config['group.id']}|"
            f"dlq={self.dlq_topic or 'unconfigured'}|partition={partition}|"
            f"offset={offset}|key={original_key}"
        )

    async def _record_consumer_dlq_event(
        self,
        msg: Message,
        error: Exception,
        error_reason_code: str,
        correlation_id: str | None,
    ) -> None:
        payload_excerpt = None
        try:
            raw_value = self._redacted_message_value_text(msg)
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
            error_reason=_source_safe_error_reason(error),
            correlation_id=correlation_id,
            correlation_missing_reason=(
                None if correlation_id else "message_correlation_id_absent"
            ),
            alternate_lookup_key=(
                None if correlation_id else self._consumer_dlq_alternate_lookup_key(msg)
            ),
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
            if self._should_skip_polled_message(msg):
                if not self._running:
                    break
                continue

            await self._process_polled_message(msg, loop)

        self.shutdown()

    async def _process_polled_message(
        self,
        msg: Message,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        token = None
        start_time = time.monotonic()
        processed_successfully = False
        try:
            corr_id = self._resolve_message_correlation_id(msg)
            token = correlation_id_var.set(corr_id)

            await self._dispatch_message_for_processing(msg, loop)
            processed_successfully = self._commit_after_successful_processing(msg)

        except RetryableConsumerError as e:
            # For transient errors, we log and do NOT commit, allowing Kafka to redeliver.
            self._log_retryable_processing_error(e)

        except Exception as e:
            # For terminal errors (poison pills), we send to DLQ and then commit.
            await self._handle_terminal_processing_error(msg, e)

        finally:
            self._record_processing_metrics(start_time, processed_successfully)
            if token:
                correlation_id_var.reset(token)

    def _should_skip_polled_message(self, msg: Message) -> bool:
        error = msg.error()
        if not error:
            return False
        if error.fatal():
            self._handle_fatal_consumer_error(error)
        else:
            self._handle_nonfatal_consumer_error(error)
        return True

    def _handle_fatal_consumer_error(self, error: object) -> None:
        logger.error(
            f"Fatal consumer error on topic {self.topic}: {error}. Shutting down.",
            exc_info=True,
        )
        self._running = False

    def _handle_nonfatal_consumer_error(self, error: object) -> None:
        logger.warning(f"Non-fatal consumer error on topic {self.topic}: {error}.")

    async def _dispatch_message_for_processing(
        self,
        msg: Message,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        if inspect.iscoroutinefunction(self.process_message):
            await self.process_message(msg)
            return
        await loop.run_in_executor(None, functools.partial(self.process_message, msg))

    def _log_retryable_processing_error(self, error: RetryableConsumerError) -> None:
        logger.warning(
            f"Retryable error occurred: {error}. Offset will not be committed.",
            exc_info=False,
        )

    async def _handle_terminal_processing_error(self, msg: Message, error: Exception) -> None:
        logger.error(
            f"Terminal error processing message for topic {self.topic}: {error}", exc_info=True
        )
        dlq_succeeded = await self._send_to_dlq_async(msg, error)
        if dlq_succeeded:
            self._commit_after_dlq_publication(msg)
        else:
            self._log_dlq_publication_failed(msg)

    def _record_processing_metrics(self, start_time: float, processed_successfully: bool) -> None:
        if not self._metrics:
            return
        labels = self._metric_labels()
        self._metrics["latency"].labels(**labels).observe(time.monotonic() - start_time)
        if processed_successfully:
            self._metrics["processed"].labels(**labels).inc()

    def _metric_labels(self) -> dict[str, str]:
        return {
            "topic": self.topic,
            "consumer_group": self._consumer_config["group.id"],
        }

    def _commit_after_dlq_publication(self, msg: Message) -> None:
        try:
            self._consumer.commit(message=msg, asynchronous=False)
        except Exception as commit_error:
            logger.warning(
                (
                    "Offset commit failed after successful DLQ publication; "
                    "offset will not be committed so Kafka can redeliver."
                ),
                exc_info=True,
                extra=self._commit_failure_log_context(msg, commit_error),
            )

    def _commit_after_successful_processing(self, msg: Message) -> bool:
        try:
            self._consumer.commit(message=msg, asynchronous=False)
            return True
        except Exception as commit_error:
            logger.warning(
                (
                    "Offset commit failed after successful processing; "
                    "offset will not be committed so Kafka can redeliver."
                ),
                exc_info=True,
                extra=self._commit_failure_log_context(msg, commit_error),
            )
            return False

    def _log_dlq_publication_failed(self, msg: Message) -> None:
        logger.warning(
            "DLQ publication failed; offset will not be committed so Kafka can redeliver.",
            extra=self._message_log_context(msg),
        )

    def _commit_failure_log_context(self, msg: Message, error: Exception) -> dict[str, str | None]:
        return {
            **self._message_log_context(msg),
            "commit_error": str(error),
        }

    def _message_log_context(self, msg: Message) -> dict[str, str | None]:
        return {
            "topic": self.topic,
            "consumer_group": self._consumer_config["group.id"],
            "message_key": self._message_key_text(msg),
        }

    def shutdown(self):
        """Gracefully shuts down the consumer."""
        logger.info(f"Shutting down consumer for topic '{self.topic}'...")
        self._running = False
        if self._consumer:
            self._wakeup_consumer_for_shutdown()
            self._close_consumer_for_shutdown()
        if self._producer:
            self._flush_dlq_producer_for_shutdown()
        logger.info(f"Consumer for topic '{self.topic}' has been closed.")

    def _shutdown_log_context(self) -> dict[str, str]:
        return {
            "topic": self.topic,
            "consumer_group": self._consumer_config["group.id"],
        }

    def _wakeup_consumer_for_shutdown(self) -> None:
        if self._consumer is None:
            return
        wakeup = getattr(self._consumer, "wakeup", None)
        if not callable(wakeup):
            return
        try:
            wakeup()
        except Exception:
            logger.warning(
                "Consumer wakeup failed during shutdown.",
                exc_info=True,
                extra=self._shutdown_log_context(),
            )

    def _close_consumer_for_shutdown(self) -> None:
        if self._consumer is None:
            return
        try:
            self._consumer.close()
        except Exception:
            logger.error(
                "Consumer close failed during shutdown.",
                exc_info=True,
                extra=self._shutdown_log_context(),
            )

    def _flush_dlq_producer_for_shutdown(self) -> None:
        if self._producer is None:
            return
        try:
            undelivered_count = self._producer.flush(timeout=5)
            if undelivered_count:
                logger.error(
                    "DLQ producer flush left undelivered messages during shutdown.",
                    extra={
                        **self._shutdown_log_context(),
                        "undelivered_count": undelivered_count,
                    },
                )
        except Exception:
            logger.error(
                "DLQ producer flush failed during shutdown.",
                exc_info=True,
                extra=self._shutdown_log_context(),
            )
