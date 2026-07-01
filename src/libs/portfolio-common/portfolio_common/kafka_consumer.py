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

from .config import (
    KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS,
    get_kafka_consumer_runtime_overrides,
)
from .database_models import ConsumerDlqEvent
from .db import get_async_db_session
from .exceptions import RetryableConsumerError
from .kafka_utils import get_kafka_producer
from .logging_utils import (
    REDACTED_VALUE,
    correlation_id_var,
    generate_correlation_id,
    log_operation_event,
    normalize_lineage_value,
    normalize_traceparent,
    redact_sensitive,
    redact_sensitive_text,
    traceparent_var,
)
from .monitoring import (
    observe_kafka_consumer_event,
    observe_kafka_consumer_processing_duration,
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


class DlqPublicationBudgetExhausted(RuntimeError):
    """Raised when a terminal message repeatedly cannot be published to DLQ."""


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
        self._dlq_failure_attempts: dict[str, int] = {}
        self._dlq_failure_max_attempts = KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS

        if self.dlq_topic:
            self._producer = get_kafka_producer()
            self._log_consumer_event(
                logging.INFO,
                "Kafka consumer DLQ enabled.",
                event_name="kafka.consumer.dlq_enabled",
                status="configured",
                reason_code="dlq_configured",
                dlq_topic=self.dlq_topic,
            )

    def _initialize_consumer(self):
        """Initializes and subscribes the Kafka consumer."""
        self._log_consumer_event(
            logging.INFO,
            "Kafka consumer initialization started.",
            event_name="kafka.consumer.initialization_started",
            status="started",
            reason_code="consumer_initializing",
        )
        self._consumer = Consumer(self._consumer_config)
        self._consumer.subscribe([self.topic])
        self._log_consumer_event(
            logging.INFO,
            "Kafka consumer subscribed.",
            event_name="kafka.consumer.subscribed",
            status="succeeded",
            reason_code="consumer_subscribed",
        )

    def _resolve_message_correlation_id(self, msg: Message) -> str:
        """
        Resolve the message correlation id from Kafka headers, falling back to a
        generated service-scoped id when no header is present.
        """
        corr_id = self._get_message_header_correlation_id(msg)
        if not corr_id:
            corr_id = generate_correlation_id(self.service_prefix)
            self._log_consumer_event(
                logging.WARNING,
                "Kafka message missing correlation id; generated fallback.",
                event_name="kafka.consumer.correlation_missing",
                status="degraded",
                reason_code="message_correlation_id_absent",
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

    def _get_message_header_traceparent(self, msg: Message) -> Optional[str]:
        if msg.headers():
            for key, value in msg.headers():
                if key == "traceparent":
                    return normalize_traceparent(value.decode("utf-8") if value else None)
        return None

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
        traceparent_token = None
        resolved = self._resolve_context_correlation_id(
            msg,
            current,
            fallback_correlation_id=fallback_correlation_id,
            prefer_fallback=prefer_fallback,
        )
        if normalize_lineage_value(current) is None:
            token = correlation_id_var.set(resolved)
        if normalize_traceparent(traceparent_var.get()) is None:
            traceparent = self._get_message_header_traceparent(msg)
            if traceparent is not None:
                traceparent_token = traceparent_var.set(traceparent)

        try:
            yield resolved
        finally:
            if traceparent_token is not None:
                traceparent_var.reset(traceparent_token)
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
            self._record_consumer_event("dlq_failed", "dlq_unconfigured")
            return False

        try:
            correlation_id = normalize_lineage_value(correlation_id_var.get())
            traceparent = normalize_traceparent(
                traceparent_var.get()
            ) or self._get_message_header_traceparent(msg)
            message_correlation_id = normalize_lineage_value(
                self._get_message_header_correlation_id(msg)
            )
            error_reason_code = classify_dlq_reason_code(error)
            dlq_payload = self._build_dlq_payload(
                msg,
                error,
                error_reason_code=error_reason_code,
                correlation_id=correlation_id,
                traceparent=traceparent,
            )
            dlq_headers = self._build_dlq_headers(
                msg,
                correlation_id=correlation_id,
                traceparent=traceparent,
            )
            self._publish_dlq_message(msg, payload=dlq_payload, headers=dlq_headers)
            self._confirm_dlq_delivery()
            await self._record_consumer_dlq_event(
                msg=msg,
                error=error,
                error_reason_code=error_reason_code,
                correlation_id=message_correlation_id,
            )
            self._record_consumer_event("dlq_published", error_reason_code)
            self._log_consumer_event(
                logging.WARNING,
                "Kafka message published to DLQ.",
                event_name="kafka.consumer.dlq_published",
                status="succeeded",
                reason_code=error_reason_code,
                dlq_topic=self.dlq_topic,
            )
            return True
        except Exception as e:
            self._record_consumer_event("dlq_failed", "dlq_publish_error")
            self._log_consumer_event(
                logging.ERROR,
                "Kafka DLQ publication failed.",
                event_name="kafka.consumer.dlq_failed",
                status="failed",
                reason_code="dlq_publish_error",
                error_type=type(e).__name__,
                exc_info=True,
            )
            return False

    def _build_dlq_payload(
        self,
        msg: Message,
        error: Exception,
        *,
        error_reason_code: str,
        correlation_id: str | None,
        traceparent: str | None,
    ) -> dict[str, object]:
        return {
            "correlation_id": correlation_id,
            "traceparent": traceparent,
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
        traceparent: str | None = None,
    ) -> list[tuple[str, bytes]]:
        dlq_headers = [_redacted_dlq_header(header) for header in msg.headers() or []]
        if correlation_id:
            dlq_headers.append(("correlation_id", correlation_id.encode("utf-8")))
        normalized_traceparent = normalize_traceparent(traceparent)
        if normalized_traceparent:
            dlq_headers.append(("traceparent", normalized_traceparent.encode("utf-8")))
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
        try:
            self._initialize_consumer()
            loop = asyncio.get_running_loop()
            self._log_consumer_event(
                logging.INFO,
                "Kafka consumer loop started.",
                event_name="kafka.consumer.loop_started",
                status="started",
                reason_code="consumer_loop_started",
            )
            while self._running:
                msg = await loop.run_in_executor(None, self._consumer.poll, 1.0)

                if msg is None:
                    continue
                if self._should_skip_polled_message(msg):
                    if not self._running:
                        break
                    continue

                await self._process_polled_message(msg, loop)
        except Exception:
            self._record_consumer_event("critical_loop_exit", "unhandled_exception")
            raise
        finally:
            self.shutdown()

    async def _process_polled_message(
        self,
        msg: Message,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        token = None
        traceparent_token = None
        start_time = time.monotonic()
        processed_successfully = False
        processing_outcome = "success"
        processing_reason = "processed"
        self._record_consumer_event("processing_attempt", "message_polled")
        try:
            corr_id = self._resolve_message_correlation_id(msg)
            token = correlation_id_var.set(corr_id)
            traceparent = self._get_message_header_traceparent(msg)
            if traceparent:
                traceparent_token = traceparent_var.set(traceparent)

            await self._dispatch_message_for_processing(msg, loop)
            processed_successfully = self._commit_after_successful_processing(msg)

        except RetryableConsumerError as e:
            # For transient errors, we log and do NOT commit, allowing Kafka to redeliver.
            processing_outcome = "retryable_failure"
            processing_reason = "retryable_consumer_error"
            self._log_retryable_processing_error(e)

        except Exception as e:
            # For terminal errors (poison pills), we send to DLQ and then commit.
            processing_outcome = "terminal_failure"
            processing_reason = classify_dlq_reason_code(e)
            await self._handle_terminal_processing_error(msg, e)

        finally:
            self._record_processing_metrics(
                start_time,
                processed_successfully,
                outcome=processing_outcome,
                reason=processing_reason,
            )
            if token:
                correlation_id_var.reset(token)
            if traceparent_token:
                traceparent_var.reset(traceparent_token)

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
        self._record_consumer_event("poll_error", "fatal")
        self._log_consumer_event(
            logging.ERROR,
            "Kafka consumer poll error was fatal; shutting down.",
            event_name="kafka.consumer.poll_error",
            status="failed",
            reason_code="fatal_poll_error",
            error_type=type(error).__name__,
            exc_info=True,
        )
        self._running = False

    def _handle_nonfatal_consumer_error(self, error: object) -> None:
        self._record_consumer_event("poll_error", "nonfatal")
        self._log_consumer_event(
            logging.WARNING,
            "Kafka consumer poll error was non-fatal.",
            event_name="kafka.consumer.poll_error",
            status="degraded",
            reason_code="nonfatal_poll_error",
            error_type=type(error).__name__,
        )

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
        self._log_consumer_event(
            logging.WARNING,
            "Kafka message processing failed retryably; offset not committed.",
            event_name="kafka.consumer.processing_retryable",
            status="retryable_failure",
            reason_code="retryable_consumer_error",
            error_type=type(error).__name__,
        )

    async def _handle_terminal_processing_error(self, msg: Message, error: Exception) -> None:
        self._log_consumer_event(
            logging.ERROR,
            "Kafka message processing failed terminally.",
            event_name="kafka.consumer.processing_terminal",
            status="terminal_failure",
            reason_code=classify_dlq_reason_code(error),
            error_type=type(error).__name__,
            exc_info=True,
        )
        dlq_succeeded = await self._send_to_dlq_async(msg, error)
        if dlq_succeeded:
            self._clear_dlq_failure_attempts(msg)
            self._commit_after_dlq_publication(msg)
        else:
            self._handle_dlq_publication_failed(msg, error)

    def _record_processing_metrics(
        self,
        start_time: float,
        processed_successfully: bool,
        *,
        outcome: str,
        reason: str,
    ) -> None:
        elapsed = time.monotonic() - start_time
        self._record_consumer_event(outcome, reason)
        observe_kafka_consumer_processing_duration(
            service=self._metric_service_label(),
            topic=self.topic,
            group_id=self._consumer_config["group.id"],
            duration_seconds=elapsed,
        )
        if not self._metrics:
            return
        labels = self._metric_labels()
        self._metrics["latency"].labels(**labels).observe(elapsed)
        if processed_successfully:
            self._metrics["processed"].labels(**labels).inc()

    def _metric_labels(self) -> dict[str, str]:
        return {
            "topic": self.topic,
            "consumer_group": self._consumer_config["group.id"],
        }

    def _metric_service_label(self) -> str:
        try:
            service_name = getattr(self, "service_name")
        except Exception:
            service_name = None
        if isinstance(service_name, str) and service_name:
            return service_name
        return self.service_prefix

    def _record_consumer_event(self, outcome: str, reason: str) -> None:
        observe_kafka_consumer_event(
            service=self._metric_service_label(),
            topic=self.topic,
            group_id=self._consumer_config["group.id"],
            outcome=outcome,
            reason=reason,
        )

    def _commit_after_dlq_publication(self, msg: Message) -> None:
        try:
            self._consumer.commit(message=msg, asynchronous=False)
        except Exception as commit_error:
            self._record_consumer_event("commit_failed", "dlq_publication")
            self._log_consumer_event(
                logging.WARNING,
                "Kafka offset commit failed after DLQ publication.",
                event_name="kafka.consumer.commit_failed",
                status="failed",
                reason_code="dlq_publication",
                exc_info=True,
                error_type=type(commit_error).__name__,
            )

    def _commit_after_successful_processing(self, msg: Message) -> bool:
        try:
            self._consumer.commit(message=msg, asynchronous=False)
            return True
        except Exception as commit_error:
            self._record_consumer_event("commit_failed", "successful_processing")
            self._log_consumer_event(
                logging.WARNING,
                "Kafka offset commit failed after successful processing.",
                event_name="kafka.consumer.commit_failed",
                status="failed",
                reason_code="successful_processing",
                exc_info=True,
                error_type=type(commit_error).__name__,
            )
            return False

    def _log_dlq_publication_failed(self, msg: Message) -> None:
        self._log_consumer_event(
            logging.WARNING,
            "DLQ publication failed; offset will not be committed so Kafka can redeliver.",
            event_name="kafka.consumer.dlq_failed",
            status="failed",
            reason_code="dlq_publish_error",
            failure_attempts=self._dlq_failure_attempts.get(
                self._dlq_failure_message_key(msg),
                0,
            ),
            max_failure_attempts=self._dlq_failure_max_attempts,
        )

    def _handle_dlq_publication_failed(self, msg: Message, error: Exception) -> None:
        attempts = self._record_dlq_failure_attempt(msg)
        if self._dlq_failure_max_attempts <= 0 or attempts < self._dlq_failure_max_attempts:
            self._log_dlq_publication_failed(msg)
            return
        self._raise_dlq_publication_budget_exhausted(msg, error, attempts)

    def _record_dlq_failure_attempt(self, msg: Message) -> int:
        message_key = self._dlq_failure_message_key(msg)
        attempts = self._dlq_failure_attempts.get(message_key, 0) + 1
        self._dlq_failure_attempts[message_key] = attempts
        return attempts

    def _clear_dlq_failure_attempts(self, msg: Message) -> None:
        self._dlq_failure_attempts.pop(self._dlq_failure_message_key(msg), None)

    def _dlq_failure_message_key(self, msg: Message) -> str:
        partition = _message_attr_or_unknown(msg, "partition")
        offset = _message_attr_or_unknown(msg, "offset")
        original_key = self._message_key_text(msg) or "unkeyed"
        return (
            f"topic={msg.topic()}|group={self._consumer_config['group.id']}|"
            f"partition={partition}|offset={offset}|key={original_key}"
        )

    def _raise_dlq_publication_budget_exhausted(
        self,
        msg: Message,
        error: Exception,
        attempts: int,
    ) -> None:
        self._running = False
        self._record_consumer_event("dlq_failure_budget_exhausted", "dlq_publish_error")
        self._log_consumer_event(
            logging.ERROR,
            (
                "Kafka DLQ publication failure budget exhausted; stopping consumer without "
                "committing offset."
            ),
            event_name="kafka.consumer.dlq_failure_budget_exhausted",
            status="failed",
            reason_code="dlq_publish_error_budget_exhausted",
            original_topic=msg.topic(),
            original_partition=_message_attr_or_unknown(msg, "partition"),
            original_offset=_message_attr_or_unknown(msg, "offset"),
            dlq_topic=self.dlq_topic or "unconfigured",
            failure_attempts=attempts,
            max_failure_attempts=self._dlq_failure_max_attempts,
            processing_error_type=type(error).__name__,
        )
        raise DlqPublicationBudgetExhausted(
            "Kafka DLQ publication failure budget exhausted; consumer stopped without "
            "committing the terminal message offset."
        )

    def shutdown(self):
        """Gracefully shuts down the consumer."""
        self._log_consumer_event(
            logging.INFO,
            "Kafka consumer shutdown started.",
            event_name="kafka.consumer.shutdown_started",
            status="started",
            reason_code="consumer_shutdown_started",
        )
        self._running = False
        if self._consumer:
            self._wakeup_consumer_for_shutdown()
            self._close_consumer_for_shutdown()
        if self._producer:
            self._flush_dlq_producer_for_shutdown()
        self._log_consumer_event(
            logging.INFO,
            "Kafka consumer shutdown completed.",
            event_name="kafka.consumer.shutdown_completed",
            status="succeeded",
            reason_code="consumer_shutdown_completed",
        )

    def _wakeup_consumer_for_shutdown(self) -> None:
        if self._consumer is None:
            return
        wakeup = getattr(self._consumer, "wakeup", None)
        if not callable(wakeup):
            return
        try:
            wakeup()
        except Exception:
            self._record_consumer_event("shutdown_failed", "consumer_wakeup")
            self._log_consumer_event(
                logging.WARNING,
                "Consumer wakeup failed during shutdown.",
                event_name="kafka.consumer.shutdown_failed",
                status="failed",
                reason_code="consumer_wakeup",
                exc_info=True,
            )

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
        log_operation_event(
            logger,
            level,
            message,
            event_name=event_name,
            operation="kafka.consume",
            status=status,
            reason_code=reason_code,
            topic=self.topic,
            consumer_group=self._consumer_config["group.id"],
            **fields,
            exc_info=exc_info,
        )

    def _close_consumer_for_shutdown(self) -> None:
        if self._consumer is None:
            return
        try:
            self._consumer.close()
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

    def _flush_dlq_producer_for_shutdown(self) -> None:
        if self._producer is None:
            return
        try:
            undelivered_count = self._producer.flush(timeout=5)
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
