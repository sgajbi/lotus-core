# src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from random import SystemRandom
from typing import Dict, List, Optional, cast
from uuid import uuid4

from sqlalchemy import and_, func, or_, update
from sqlalchemy.orm import aliased, sessionmaker

from portfolio_common.database_models import OutboxEvent
from portfolio_common.db import SessionLocal
from portfolio_common.ingestion_lineage import INGESTION_JOB_ID_HEADER
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.logging_utils import (
    normalize_traceparent,
    operation_log_extra,
    redact_sensitive_text,
)
from portfolio_common.monitoring import (
    observe_outbox_failed,
    observe_outbox_published,
    observe_outbox_retried,
    outbox_batch_timer,
    set_outbox_failed_stored,
    set_outbox_oldest_pending_age_seconds,
    set_outbox_pending,
    set_outbox_retry_eligible_pending,
    set_outbox_retry_waiting_pending,
)
from portfolio_common.outbox_settings import (
    OutboxRuntimeConfigurationError,
    get_outbox_runtime_settings,
)
from portfolio_common.runtime_supervision import RUNTIME_TERMINATION_GRACE_SAFETY_SECONDS

logger = logging.getLogger(__name__)

TERMINAL_FAILURE_STATUS = "FAILED"
MAX_FAILURE_MESSAGE_LENGTH = 512
DEFAULT_DELIVERY_FENCE_TIMEOUT_SECONDS = 10
CLAIM_LEASE_SAFETY_SECONDS = 5
SHUTDOWN_DRAIN_SAFETY_SECONDS = 5


@dataclass(frozen=True, slots=True)
class _ClaimedOutboxEvent:
    id: int
    aggregate_type: str
    aggregate_id: str
    partition_key: str
    event_type: str
    payload: object
    topic: str
    correlation_id: str | None
    traceparent: str | None
    retry_count: int | None
    created_at: datetime
    claim_token: str
    claim_expires_at: datetime
    ingestion_job_id: str | None = None


def _owned_delivery_claim(event: _ClaimedOutboxEvent):
    """Fence delivery-result writes on both token identity and live DB lease authority."""

    return and_(
        OutboxEvent.id == event.id,
        OutboxEvent.claim_token == event.claim_token,
        OutboxEvent.claim_expires_at > func.clock_timestamp(),
    )


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
        termination_grace_seconds: Optional[int] = None,
        retry_max_elapsed_seconds: Optional[int] = None,
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
        self._delivery_fence_timeout_seconds = _delivery_fence_timeout_seconds(kafka_producer)
        self._claim_lease_seconds = (
            max(1, int(claim_lease_seconds))
            if claim_lease_seconds is not None
            else runtime_settings.claim_lease_seconds
        )
        minimum_claim_lease_seconds = (
            self._delivery_fence_timeout_seconds + CLAIM_LEASE_SAFETY_SECONDS
        )
        if self._claim_lease_seconds < minimum_claim_lease_seconds:
            raise OutboxRuntimeConfigurationError(
                "Invalid outbox runtime configuration for "
                "OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS: expected at least "
                f"{minimum_claim_lease_seconds} seconds so an expired publisher "
                "cannot deliver after its stream lease is reclaimed"
            )
        self._shutdown_timeout_seconds = (
            self._delivery_fence_timeout_seconds + SHUTDOWN_DRAIN_SAFETY_SECONDS
        )
        self._termination_grace_seconds = (
            max(1, int(termination_grace_seconds))
            if termination_grace_seconds is not None
            else runtime_settings.termination_grace_seconds
        )
        minimum_termination_grace_seconds = (
            self._shutdown_timeout_seconds + RUNTIME_TERMINATION_GRACE_SAFETY_SECONDS
        )
        if self._termination_grace_seconds < minimum_termination_grace_seconds:
            raise OutboxRuntimeConfigurationError(
                "Invalid outbox runtime configuration for "
                "OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS: expected at least "
                f"{minimum_termination_grace_seconds} seconds so runtime supervision "
                "can fence Kafka delivery before the pod is terminated"
            )
        self._retry_max_elapsed_seconds = (
            max(0, int(retry_max_elapsed_seconds))
            if retry_max_elapsed_seconds is not None
            else runtime_settings.retry_max_elapsed_seconds
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

    @property
    def shutdown_timeout_seconds(self) -> int:
        """Return the minimum supervision budget required to fence in-flight delivery."""

        return self._shutdown_timeout_seconds

    @property
    def termination_grace_seconds(self) -> int:
        """Return the orchestrator stop budget validated for this dispatcher."""
        return self._termination_grace_seconds

    def stop(self):
        logger.info(
            "Outbox dispatcher shutdown signal received.",
            extra=operation_log_extra(
                event_name="outbox.dispatcher.shutdown_started",
                operation="outbox.dispatch",
                status="stopping",
                reason_code="shutdown_requested",
            ),
        )
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
            now = datetime.now(timezone.utc)
            retry_eligible_total = (
                s.query(func.count(OutboxEvent.id))
                .filter(OutboxEvent.status == "PENDING")
                .filter(
                    or_(
                        OutboxEvent.next_attempt_at.is_(None),
                        OutboxEvent.next_attempt_at <= now,
                    )
                )
                .scalar()
                or 0
            )
            retry_waiting_total = (
                s.query(func.count(OutboxEvent.id))
                .filter(OutboxEvent.status == "PENDING")
                .filter(OutboxEvent.next_attempt_at > now)
                .scalar()
                or 0
            )
            failed_total = (
                s.query(func.count(OutboxEvent.id))
                .filter(OutboxEvent.status == TERMINAL_FAILURE_STATUS)
                .scalar()
                or 0
            )
            set_outbox_pending(int(pending_total))
            set_outbox_retry_eligible_pending(int(retry_eligible_total))
            set_outbox_retry_waiting_pending(int(retry_waiting_total))
            set_outbox_failed_stored(int(failed_total))
            if oldest_pending_created_at is None:
                set_outbox_oldest_pending_age_seconds(0.0)
            else:
                age_seconds = max(
                    0.0,
                    (now - _as_utc(oldest_pending_created_at)).total_seconds(),
                )
                set_outbox_oldest_pending_age_seconds(age_seconds)

    def _process_batch_sync(self) -> int:
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
                return 0

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
            return len(events_to_process)

    def _claim_pending_events(self) -> list[_ClaimedOutboxEvent]:
        claim_token = uuid4().hex
        retry_now = datetime.now(timezone.utc)

        with self._session_factory() as db:
            with db.begin():
                candidate = aliased(OutboxEvent, name="candidate_outbox_event")
                earlier_unresolved = aliased(OutboxEvent, name="earlier_unresolved_outbox_event")
                earlier_stream_event_exists = (
                    db.query(earlier_unresolved.id)
                    .filter(
                        earlier_unresolved.topic == candidate.topic,
                        earlier_unresolved.partition_key == candidate.partition_key,
                        earlier_unresolved.status.in_(("PENDING", TERMINAL_FAILURE_STATUS)),
                        or_(
                            earlier_unresolved.created_at < candidate.created_at,
                            and_(
                                earlier_unresolved.created_at == candidate.created_at,
                                earlier_unresolved.id < candidate.id,
                            ),
                        ),
                    )
                    .exists()
                )
                events_to_claim: List[OutboxEvent] = (
                    db.query(candidate)
                    .filter(candidate.status == "PENDING")
                    .filter(
                        or_(
                            candidate.next_attempt_at.is_(None),
                            candidate.next_attempt_at <= retry_now,
                        )
                    )
                    .filter(
                        or_(
                            candidate.claim_token.is_(None),
                            candidate.claim_expires_at.is_(None),
                            candidate.claim_expires_at <= func.clock_timestamp(),
                        )
                    )
                    .filter(~earlier_stream_event_exists)
                    .order_by(
                        candidate.next_attempt_at.asc().nullsfirst(),
                        candidate.created_at.asc(),
                        candidate.id.asc(),
                    )
                    .with_for_update(skip_locked=True, of=candidate)
                    .limit(self._batch_size)
                    .all()
                )

                if not events_to_claim:
                    return []

                # Mint the delivery lease in PostgreSQL time only after head selection. Query
                # latency must not consume the safety margin reserved for commit and producer
                # publication, and a dispatcher with a skewed host clock must not steal a live
                # claim. RETURNING gives the caller the exact durable deadline it must fence.
                claimed_rows = (
                    db.execute(
                        update(OutboxEvent)
                        .where(OutboxEvent.id.in_([event.id for event in events_to_claim]))
                        .values(
                            claim_token=claim_token,
                            claim_expires_at=func.clock_timestamp()
                            + func.make_interval(0, 0, 0, 0, 0, 0, self._claim_lease_seconds),
                        )
                        .returning(OutboxEvent)
                        .execution_options(
                            synchronize_session=False,
                            populate_existing=True,
                        )
                    )
                    .scalars()
                    .all()
                )
                claimed_by_id = {int(event.id): event for event in claimed_rows}
                claimed_events: list[_ClaimedOutboxEvent] = []
                for selected_event in events_to_claim:
                    event = claimed_by_id.get(int(selected_event.id))
                    if event is None or event.claim_expires_at is None:
                        raise RuntimeError("Outbox claim did not return durable lease identity")
                    claimed_events.append(
                        _ClaimedOutboxEvent(
                            id=event.id,
                            aggregate_type=event.aggregate_type,
                            aggregate_id=event.aggregate_id,
                            partition_key=event.partition_key,
                            event_type=event.event_type,
                            payload=event.payload,
                            topic=event.topic,
                            correlation_id=event.correlation_id,
                            ingestion_job_id=event.ingestion_job_id,
                            traceparent=_payload_traceparent(event.payload),
                            retry_count=event.retry_count,
                            created_at=_as_utc(event.created_at),
                            claim_token=claim_token,
                            claim_expires_at=_as_utc(event.claim_expires_at),
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
                    key=event.partition_key,
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
                    extra=operation_log_extra(
                        event_name="outbox.dispatcher.publish_failed",
                        operation="outbox.dispatch",
                        status="failed",
                        reason_code="synchronous_publish_error",
                        outbox_id=event.id,
                        topic=event.topic,
                    ),
                )

    def _flush_delivery_results(
        self,
        events_to_process: list[_ClaimedOutboxEvent],
        delivery_ack: Dict[int, bool],
        delivery_errs: Dict[int, str],
    ) -> None:
        try:
            undelivered_count = self._producer.flush(timeout=self._delivery_fence_timeout_seconds)
        except Exception as e:
            logger.error(
                "Outbox dispatcher flush failed.",
                exc_info=True,
                extra=operation_log_extra(
                    event_name="outbox.dispatcher.flush_failed",
                    operation="outbox.dispatch",
                    status="failed",
                    reason_code="producer_flush_error",
                    event_count=len(events_to_process),
                    error_type=type(e).__name__,
                ),
            )
            self._producer.reset_after_flush_failure()
            _mark_callbackless_events_failed(
                events_to_process,
                delivery_ack,
                delivery_errs,
                reason=str(e),
            )
            return

        logger.debug(
            "Outbox dispatcher flush completed.",
            extra=operation_log_extra(
                event_name="outbox.dispatcher.flush_completed",
                operation="outbox.dispatch",
                status="succeeded",
                reason_code="producer_flush_completed",
                event_count=len(events_to_process),
                undelivered_count=undelivered_count,
            ),
        )
        if undelivered_count:
            self._producer.reset_after_flush_failure()
            _mark_callbackless_events_failed(
                events_to_process,
                delivery_ack,
                delivery_errs,
                reason="Kafka flush timed out before delivery callback.",
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
        now = datetime.now(timezone.utc)
        success_ids = _delivery_ids_by_outcome(delivery_ack, successful=True)
        failure_ids = _delivery_ids_by_outcome(delivery_ack, successful=False)
        terminal_failure_ids = [
            event.id
            for event in events_to_process
            if event.id in failure_ids
            and (
                (event.retry_count or 0) + 1 >= self._max_retries
                or self._retry_elapsed_budget_exhausted(event, now=now)
            )
        ]
        retryable_failure_ids = _retryable_failure_ids(failure_ids, terminal_failure_ids)
        return success_ids, retryable_failure_ids, terminal_failure_ids

    def _retry_elapsed_budget_exhausted(
        self,
        event: _ClaimedOutboxEvent,
        *,
        now: datetime,
    ) -> bool:
        if self._retry_max_elapsed_seconds <= 0:
            return False
        retry_window_seconds = (now - _as_utc(event.created_at)).total_seconds()
        return retry_window_seconds >= self._retry_max_elapsed_seconds

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
                .where(_owned_delivery_claim(event))
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
                    "OutboxDispatcher: Skipped success update because claim token no longer "
                    "owns row.",
                    extra=operation_log_extra(
                        event_name="outbox.dispatcher.success_update_skipped",
                        operation="outbox.dispatch",
                        status="skipped",
                        reason_code="claim_token_lost",
                        outbox_id=event.id,
                        topic=event.topic,
                    ),
                )
        logger.debug(
            "Outbox dispatcher marked events as processed.",
            extra=operation_log_extra(
                event_name="outbox.dispatcher.events_processed",
                operation="outbox.dispatch",
                status="succeeded",
                reason_code="database_update_completed",
                updated_count=updated_count,
            ),
        )

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
                .where(_owned_delivery_claim(event))
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
                    "OutboxDispatcher: Skipped retry update because claim token no longer "
                    "owns row.",
                    extra=operation_log_extra(
                        event_name="outbox.dispatcher.retry_update_skipped",
                        operation="outbox.dispatch",
                        status="skipped",
                        reason_code="claim_token_lost",
                        outbox_id=event.id,
                        topic=event.topic,
                    ),
                )
                continue
            observe_outbox_failed(event.aggregate_type, event.topic)
            observe_outbox_retried(event.aggregate_type, event.topic)
            reason = delivery_errs.get(event.id, "unknown error")
            logger.warning(
                "OutboxDispatcher: Kafka delivery failed; will retry later.",
                extra=operation_log_extra(
                    event_name="outbox.dispatcher.delivery_retry_scheduled",
                    operation="outbox.dispatch",
                    status="retrying",
                    reason_code="delivery_error",
                    outbox_id=event.id,
                    topic=event.topic,
                    retry_count=event.retry_count,
                    delivery_error=_source_safe_failure_message(reason),
                    next_attempt_at=next_attempt_at.isoformat(),
                ),
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
                .where(_owned_delivery_claim(event))
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
                    "OutboxDispatcher: Skipped terminal update because claim token no longer "
                    "owns row.",
                    extra=operation_log_extra(
                        event_name="outbox.dispatcher.terminal_update_skipped",
                        operation="outbox.dispatch",
                        status="skipped",
                        reason_code="claim_token_lost",
                        outbox_id=event.id,
                        topic=event.topic,
                    ),
                )
                continue
            observe_outbox_failed(event.aggregate_type, event.topic)
            reason = delivery_errs.get(event.id, "unknown error")
            logger.error(
                "OutboxDispatcher: Kafka delivery reached terminal failure threshold.",
                extra=operation_log_extra(
                    event_name="outbox.dispatcher.delivery_terminal_failure",
                    operation="outbox.dispatch",
                    status="failed",
                    reason_code="terminal_delivery_error",
                    outbox_id=event.id,
                    topic=event.topic,
                    retry_count=event.retry_count,
                    delivery_error=_source_safe_failure_message(reason),
                    max_retries=self._max_retries,
                    failure_reason_code=failure_metadata["last_failure_reason_code"],
                    failure_category=failure_metadata["last_failure_category"],
                ),
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
        logger.info(
            "Outbox dispatcher started.",
            extra=operation_log_extra(
                event_name="outbox.dispatcher.started",
                operation="outbox.dispatch",
                status="running",
                reason_code="poll_loop_started",
                poll_interval_seconds=self._poll_interval,
            ),
        )

        while self._running:
            processed_count = 0
            try:
                processed_count = await asyncio.to_thread(self._process_batch_sync)
            except Exception:
                logger.error(
                    "Outbox dispatcher batch processing failed.",
                    exc_info=True,
                    extra=operation_log_extra(
                        event_name="outbox.dispatcher.batch_failed",
                        operation="outbox.dispatch",
                        status="failed",
                        reason_code="batch_processing_error",
                    ),
                )

            if processed_count:
                await asyncio.sleep(0)
                continue

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval)
                break
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

        logger.info(
            "Outbox dispatcher stopped.",
            extra=operation_log_extra(
                event_name="outbox.dispatcher.stopped",
                operation="outbox.dispatch",
                status="stopped",
                reason_code="poll_loop_stopped",
            ),
        )


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


def _delivery_fence_timeout_seconds(kafka_producer: KafkaProducer) -> int:
    producer_policy = getattr(kafka_producer, "producer_policy", None)
    delivery_timeout_ms = getattr(producer_policy, "delivery_timeout_ms", None)
    if isinstance(delivery_timeout_ms, int) and delivery_timeout_ms > 0:
        return max(
            DEFAULT_DELIVERY_FENCE_TIMEOUT_SECONDS,
            ((delivery_timeout_ms + 999) // 1000) + 1,
        )
    return DEFAULT_DELIVERY_FENCE_TIMEOUT_SECONDS


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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _event_headers(event: _ClaimedOutboxEvent) -> list[tuple[str, bytes]]:
    headers: list[tuple[str, bytes]] = []
    if event.correlation_id:
        headers.append(("correlation_id", event.correlation_id.encode("utf-8")))
    if event.ingestion_job_id:
        headers.append((INGESTION_JOB_ID_HEADER, event.ingestion_job_id.encode("utf-8")))
    traceparent = normalize_traceparent(event.traceparent)
    if traceparent:
        headers.append(("traceparent", traceparent.encode("utf-8")))
    return headers


def _event_payload(event: _ClaimedOutboxEvent):
    if isinstance(event.payload, dict):
        return event.payload
    return json.loads(cast(str | bytes | bytearray, event.payload))


def _payload_traceparent(payload: object) -> str | None:
    if isinstance(payload, dict):
        return normalize_traceparent(payload.get("traceparent"))  # type: ignore[arg-type]
    try:
        decoded = json.loads(cast(str | bytes | bytearray, payload))
    except (TypeError, ValueError):
        return None
    if isinstance(decoded, dict):
        return normalize_traceparent(decoded.get("traceparent"))  # type: ignore[arg-type]
    return None


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
