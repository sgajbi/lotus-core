# src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from random import SystemRandom
from typing import Dict, List, Optional, cast
from uuid import uuid4

from sqlalchemy import func, or_, update
from sqlalchemy.orm import sessionmaker

from portfolio_common.database_models import OutboxEvent
from portfolio_common.db import SessionLocal
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.logging_utils import redact_sensitive_text
from portfolio_common.monitoring import (
    observe_outbox_failed,
    observe_outbox_published,
    observe_outbox_retried,
    outbox_batch_timer,
    set_outbox_failed_stored,
    set_outbox_oldest_pending_age_seconds,
    set_outbox_pending,
)
from portfolio_common.outbox_settings import get_outbox_runtime_settings

logger = logging.getLogger(__name__)

TERMINAL_FAILURE_STATUS = "FAILED"
MAX_FAILURE_MESSAGE_LENGTH = 512


@dataclass(frozen=True, slots=True)
class _ClaimedOutboxEvent:
    id: int
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: object
    topic: str
    correlation_id: str | None
    retry_count: int | None
    claim_token: str
    claim_expires_at: datetime


class OutboxDispatcher:
    """
    Polls the outbox_events table and publishes PENDING events to Kafka.
    Tracks per-message delivery results and only marks successful ones as PROCESSED.
    Failed deliveries remain PENDING with retry_count incremented.
    Emits Prometheus metrics for visibility.
    """

    def __init__(
        self,
        kafka_producer: KafkaProducer,
        poll_interval: Optional[int] = None,
        batch_size: Optional[int] = None,
        db_session_factory: Optional[sessionmaker] = None,
        max_retries: Optional[int] = None,
        claim_lease_seconds: Optional[int] = None,
        retry_initial_delay_seconds: Optional[int] = None,
        retry_max_delay_seconds: Optional[int] = None,
        retry_jitter_seconds: Optional[int] = None,
    ):
        runtime_settings = get_outbox_runtime_settings()
        self._producer = kafka_producer
        self._poll_interval = (
            max(1, int(poll_interval))
            if poll_interval is not None
            else runtime_settings.poll_interval_seconds
        )
        self._batch_size = (
            max(1, int(batch_size)) if batch_size is not None else runtime_settings.batch_size
        )
        self._running = True
        self._stop_event = asyncio.Event()
        self._session_factory = db_session_factory or SessionLocal
        self._max_retries = (
            max(1, int(max_retries)) if max_retries is not None else runtime_settings.max_retries
        )
        self._claim_lease_seconds = (
            max(1, int(claim_lease_seconds))
            if claim_lease_seconds is not None
            else runtime_settings.claim_lease_seconds
        )
        self._retry_initial_delay_seconds = (
            max(1, int(retry_initial_delay_seconds))
            if retry_initial_delay_seconds is not None
            else runtime_settings.retry_initial_delay_seconds
        )
        self._retry_max_delay_seconds = (
            max(self._retry_initial_delay_seconds, int(retry_max_delay_seconds))
            if retry_max_delay_seconds is not None
            else runtime_settings.retry_max_delay_seconds
        )
        self._retry_jitter_seconds = (
            max(0, int(retry_jitter_seconds))
            if retry_jitter_seconds is not None
            else runtime_settings.retry_jitter_seconds
        )
        self._retry_random = SystemRandom()

    def stop(self):
        logger.info("Outbox dispatcher shutdown signal received.")
        self._running = False
        self._stop_event.set()

    def _read_pending_gauge(self) -> None:
        """Reads PENDING count in a short-lived session to avoid interfering with the batch tx."""
        with self._session_factory() as s:
            pending_total, oldest_pending_created_at = (
                s.query(
                    func.count(OutboxEvent.id),
                    func.min(OutboxEvent.created_at),
                )
                .filter(OutboxEvent.status == "PENDING")
                .one()
            )
            failed_total = (
                s.query(func.count(OutboxEvent.id))
                .filter(OutboxEvent.status == TERMINAL_FAILURE_STATUS)
                .scalar()
                or 0
            )
            set_outbox_pending(int(pending_total))
            set_outbox_failed_stored(int(failed_total))
            if oldest_pending_created_at is None:
                set_outbox_oldest_pending_age_seconds(0.0)
            else:
                age_seconds = max(
                    0.0,
                    (datetime.now(timezone.utc) - oldest_pending_created_at).total_seconds(),
                )
                set_outbox_oldest_pending_age_seconds(age_seconds)

    def _process_batch_sync(self) -> None:
        """
        Single batch:
        - Read pending gauge using a separate short-lived session (no open tx carried over)
        - Claim a slice of PENDING events in one short SELECT ... FOR UPDATE SKIP LOCKED tx
        - Publish to Kafka outside DB row locks
        - Update statuses with claim-token fencing in a second short transaction
        """
        self._read_pending_gauge()

        with outbox_batch_timer():
            events_to_process = self._claim_pending_events()

            if not events_to_process:
                return

            delivery_ack: Dict[int, bool] = {}
            delivery_errs: Dict[int, str] = {}

            self._publish_events(events_to_process, delivery_ack, delivery_errs)
            self._flush_delivery_results(events_to_process, delivery_ack, delivery_errs)

            with self._session_factory() as db:
                with db.begin():
                    self._persist_delivery_results(
                        db,
                        events_to_process,
                        delivery_ack,
                        delivery_errs,
                    )

    def _claim_pending_events(self) -> list[_ClaimedOutboxEvent]:
        claim_token = uuid4().hex
        now = datetime.now(timezone.utc)
        claim_expires_at = now + timedelta(seconds=self._claim_lease_seconds)

        with self._session_factory() as db:
            with db.begin():
                events_to_claim: List[OutboxEvent] = (
                    db.query(OutboxEvent)
                    .filter(OutboxEvent.status == "PENDING")
                    .filter(
                        or_(
                            OutboxEvent.next_attempt_at.is_(None),
                            OutboxEvent.next_attempt_at <= now,
                        )
                    )
                    .filter(
                        or_(
                            OutboxEvent.claim_token.is_(None),
                            OutboxEvent.claim_expires_at.is_(None),
                            OutboxEvent.claim_expires_at <= now,
                        )
                    )
                    .order_by(
                        OutboxEvent.next_attempt_at.asc().nullsfirst(),
                        OutboxEvent.created_at.asc(),
                    )
                    .with_for_update(skip_locked=True, of=OutboxEvent)
                    .limit(self._batch_size)
                    .all()
                )

                if not events_to_claim:
                    return []

                claimed_events: list[_ClaimedOutboxEvent] = []
                for event in events_to_claim:
                    event.claim_token = claim_token
                    event.claim_expires_at = claim_expires_at
                    claimed_events.append(
                        _ClaimedOutboxEvent(
                            id=event.id,
                            aggregate_type=event.aggregate_type,
                            aggregate_id=event.aggregate_id,
                            event_type=event.event_type,
                            payload=event.payload,
                            topic=event.topic,
                            correlation_id=event.correlation_id,
                            retry_count=event.retry_count,
                            claim_token=claim_token,
                            claim_expires_at=claim_expires_at,
                        )
                    )
                return claimed_events

    def _publish_events(
        self,
        events_to_process: list[_ClaimedOutboxEvent],
        delivery_ack: Dict[int, bool],
        delivery_errs: Dict[int, str],
    ) -> None:
        for event in events_to_process:
            try:
                self._producer.publish_message(
                    topic=event.topic,
                    key=event.aggregate_id,
                    value=_event_payload(event),
                    headers=_event_headers(event),
                    outbox_id=str(event.id),
                    on_delivery=_make_on_delivery(event.id, delivery_ack, delivery_errs),
                )
            except Exception as e:
                delivery_ack[event.id] = False
                delivery_errs[event.id] = str(e)
                logger.error(
                    "OutboxDispatcher: Synchronous Kafka publish failed.",
                    exc_info=True,
                    extra={"outbox_id": event.id, "topic": event.topic},
                )

    def _flush_delivery_results(
        self,
        events_to_process: list[_ClaimedOutboxEvent],
        delivery_ack: Dict[int, bool],
        delivery_errs: Dict[int, str],
    ) -> None:
        try:
            undelivered_count = self._producer.flush(timeout=10)
            logger.info(f"OutboxDispatcher: Flush complete for {len(events_to_process)} events.")
            if undelivered_count:
                _mark_callbackless_events_failed(
                    events_to_process,
                    delivery_ack,
                    delivery_errs,
                    reason="Kafka flush timed out before delivery callback.",
                )
        except Exception as e:
            logger.error("OutboxDispatcher: Kafka flush failed.", exc_info=True)
            _mark_callbackless_events_failed(
                events_to_process,
                delivery_ack,
                delivery_errs,
                reason=str(e),
            )

    def _persist_delivery_results(
        self,
        db,
        events_to_process: list[_ClaimedOutboxEvent],
        delivery_ack: Dict[int, bool],
        delivery_errs: Dict[int, str],
    ) -> None:
        success_ids, retryable_failure_ids, terminal_failure_ids = self._classify_delivery_results(
            events_to_process, delivery_ack
        )
        self._mark_successes(db, events_to_process, success_ids)
        self._mark_retryable_failures(
            db,
            events_to_process,
            retryable_failure_ids,
            delivery_errs,
        )
        self._mark_terminal_failures(
            db,
            events_to_process,
            terminal_failure_ids,
            delivery_errs,
        )

    def _classify_delivery_results(
        self,
        events_to_process: list[_ClaimedOutboxEvent],
        delivery_ack: Dict[int, bool],
    ) -> tuple[list[int], list[int], list[int]]:
        success_ids = _delivery_ids_by_outcome(delivery_ack, successful=True)
        failure_ids = _delivery_ids_by_outcome(delivery_ack, successful=False)
        terminal_failure_ids = [
            event.id
            for event in events_to_process
            if event.id in failure_ids and (event.retry_count or 0) + 1 >= self._max_retries
        ]
        retryable_failure_ids = _retryable_failure_ids(failure_ids, terminal_failure_ids)
        return success_ids, retryable_failure_ids, terminal_failure_ids

    def _mark_successes(
        self,
        db,
        events_to_process: list[_ClaimedOutboxEvent],
        success_ids: list[int],
    ) -> None:
        if not success_ids:
            return
        success_id_set = set(success_ids)
        processed_at = datetime.now(timezone.utc)
        updated_count = 0
        for event in events_to_process:
            if event.id not in success_id_set:
                continue
            result = db.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == event.id)
                .where(OutboxEvent.claim_token == event.claim_token)
                .values(
                    status="PROCESSED",
                    processed_at=processed_at,
                    next_attempt_at=None,
                    claim_token=None,
                    claim_expires_at=None,
                    last_failure_reason_code=None,
                    last_failure_category=None,
                    last_failure_message=None,
                    last_failure_at=None,
                )
            )
            if result.rowcount == 1:
                updated_count += 1
                observe_outbox_published(event.aggregate_type, event.topic)
            else:
                logger.warning(
                    "OutboxDispatcher: Skipped success update because claim token no longer owns row.",
                    extra={"outbox_id": event.id},
                )
        logger.info(f"OutboxDispatcher: Marked {updated_count} events as PROCESSED in DB.")

    def _mark_retryable_failures(
        self,
        db,
        events_to_process: list[_ClaimedOutboxEvent],
        retryable_failure_ids: list[int],
        delivery_errs: Dict[int, str],
    ) -> None:
        if not retryable_failure_ids:
            return
        attempted_at = datetime.now(timezone.utc)
        retryable_failure_id_set = set(retryable_failure_ids)
        retryable_events = [
            event for event in events_to_process if event.id in retryable_failure_id_set
        ]
        for event in retryable_events:
            next_retry_count = (event.retry_count or 0) + 1
            next_attempt_at = self._next_attempt_at(
                now=attempted_at,
                retry_count=next_retry_count,
            )
            failure_metadata = _failure_metadata(
                delivery_errs.get(event.id, "unknown error"),
                failed_at=attempted_at,
            )
            result = db.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == event.id)
                .where(OutboxEvent.claim_token == event.claim_token)
                .values(
                    # Use COALESCE to treat NULL as 0 before incrementing.
                    retry_count=func.coalesce(OutboxEvent.retry_count, 0) + 1,
                    last_attempted_at=attempted_at,
                    next_attempt_at=next_attempt_at,
                    claim_token=None,
                    claim_expires_at=None,
                    **failure_metadata,
                )
            )
            if result.rowcount != 1:
                logger.warning(
                    "OutboxDispatcher: Skipped retry update because claim token no longer owns row.",
                    extra={"outbox_id": event.id},
                )
                continue
            observe_outbox_failed(event.aggregate_type, event.topic)
            observe_outbox_retried(event.aggregate_type, event.topic)
            reason = delivery_errs.get(event.id, "unknown error")
            logger.warning(
                "OutboxDispatcher: Kafka delivery failed; will retry later.",
                extra={
                    "outbox_id": event.id,
                    "reason": reason,
                    "next_attempt_at": next_attempt_at.isoformat(),
                },
            )

    def _mark_terminal_failures(
        self,
        db,
        events_to_process: list[_ClaimedOutboxEvent],
        terminal_failure_ids: list[int],
        delivery_errs: Dict[int, str],
    ) -> None:
        if not terminal_failure_ids:
            return
        failed_at = datetime.now(timezone.utc)
        terminal_failure_id_set = set(terminal_failure_ids)
        terminal_events = [
            event for event in events_to_process if event.id in terminal_failure_id_set
        ]
        for event in terminal_events:
            failure_metadata = _failure_metadata(
                delivery_errs.get(event.id, "unknown error"),
                failed_at=failed_at,
            )
            result = db.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == event.id)
                .where(OutboxEvent.claim_token == event.claim_token)
                .values(
                    status=TERMINAL_FAILURE_STATUS,
                    retry_count=func.coalesce(OutboxEvent.retry_count, 0) + 1,
                    last_attempted_at=failed_at,
                    next_attempt_at=None,
                    claim_token=None,
                    claim_expires_at=None,
                    **failure_metadata,
                )
            )
            if result.rowcount != 1:
                logger.warning(
                    "OutboxDispatcher: Skipped terminal update because claim token no longer owns row.",
                    extra={"outbox_id": event.id},
                )
                continue
            observe_outbox_failed(event.aggregate_type, event.topic)
            reason = delivery_errs.get(event.id, "unknown error")
            logger.error(
                "OutboxDispatcher: Kafka delivery reached terminal failure threshold.",
                extra={
                    "outbox_id": event.id,
                    "reason": _source_safe_failure_message(reason),
                    "max_retries": self._max_retries,
                    "failure_reason_code": failure_metadata["last_failure_reason_code"],
                    "failure_category": failure_metadata["last_failure_category"],
                },
            )

    def _retry_delay_seconds(self, retry_count: int) -> float:
        normalized_retry_count = max(1, retry_count)
        delay_seconds = self._retry_initial_delay_seconds * (2 ** (normalized_retry_count - 1))
        bounded_delay = min(self._retry_max_delay_seconds, delay_seconds)
        if self._retry_jitter_seconds <= 0 or bounded_delay >= self._retry_max_delay_seconds:
            return float(bounded_delay)
        jittered_delay = bounded_delay + self._retry_random.uniform(0, self._retry_jitter_seconds)
        return float(min(self._retry_max_delay_seconds, jittered_delay))

    def _next_attempt_at(self, *, now: datetime, retry_count: int) -> datetime:
        return now + timedelta(seconds=self._retry_delay_seconds(retry_count))

    async def run(self):
        logger.info(f"Outbox dispatcher started. Polling every {self._poll_interval} seconds.")

        while self._running:
            try:
                await asyncio.to_thread(self._process_batch_sync)
            except Exception:
                logger.error("Failed to process outbox batch.", exc_info=True)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
                break
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

        logger.info("Outbox dispatcher has stopped.")


def _make_on_delivery(
    outbox_id: int,
    delivery_ack: Dict[int, bool],
    delivery_errs: Dict[int, str],
):
    def _cb(_replayed_outbox_id: str, success: bool, error_message: Optional[str]):
        if success:
            delivery_ack[outbox_id] = True
        else:
            delivery_ack[outbox_id] = False
            delivery_errs[outbox_id] = str(error_message)

    return _cb


def _delivery_ids_by_outcome(delivery_ack: Dict[int, bool], *, successful: bool) -> list[int]:
    return [outbox_id for outbox_id, ok in delivery_ack.items() if ok is successful]


def _retryable_failure_ids(failure_ids: list[int], terminal_failure_ids: list[int]) -> list[int]:
    terminal_failure_id_set = set(terminal_failure_ids)
    return [failure_id for failure_id in failure_ids if failure_id not in terminal_failure_id_set]


def _failure_metadata(reason: str, *, failed_at: datetime) -> dict[str, object]:
    return {
        "last_failure_reason_code": _failure_reason_code(reason),
        "last_failure_category": "event_publish_delivery",
        "last_failure_message": _source_safe_failure_message(reason),
        "last_failure_at": failed_at,
    }


def _failure_reason_code(reason: str) -> str:
    normalized = str(reason or "").lower()
    if "timed out" in normalized or "timeout" in normalized:
        return "kafka_delivery_timeout"
    if "flush" in normalized:
        return "kafka_flush_failed"
    if "publish" in normalized:
        return "kafka_publish_failed"
    return "kafka_delivery_failed"


def _source_safe_failure_message(reason: str) -> str:
    redacted = redact_sensitive_text(str(reason or "unknown error"))
    return str(redacted[:MAX_FAILURE_MESSAGE_LENGTH])


def _event_headers(event: _ClaimedOutboxEvent) -> list[tuple[str, bytes]]:
    if not event.correlation_id:
        return []
    return [("correlation_id", event.correlation_id.encode("utf-8"))]


def _event_payload(event: _ClaimedOutboxEvent):
    if isinstance(event.payload, dict):
        return event.payload
    return json.loads(cast(str | bytes | bytearray, event.payload))


def _mark_callbackless_events_failed(
    events_to_process: list[_ClaimedOutboxEvent],
    delivery_ack: Dict[int, bool],
    delivery_errs: Dict[int, str],
    *,
    reason: str,
) -> None:
    for event in events_to_process:
        if event.id not in delivery_ack:
            delivery_ack[event.id] = False
            delivery_errs[event.id] = reason
