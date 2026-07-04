from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from portfolio_common.config import KAFKA_PORTFOLIO_DAY_AGGREGATION_JOB_REQUESTED_TOPIC
from portfolio_common.event_publisher import (
    EventPublisher,
    EventPublishRequest,
    get_kafka_event_publisher,
)
from portfolio_common.events import PortfolioAggregationRequiredEvent, event_business_payload
from portfolio_common.scheduler_dispatch_recovery import (
    DISPATCH_CONFIRMATION_TIMEOUT_PHASE,
    DISPATCH_PUBLISH_FAILURE_PHASE,
    SchedulerDispatchError,
    present_job_ids,
)


class AggregationJobPublisher(Protocol):
    def publish_job_requested(self, message: AggregationJobDispatchMessage) -> None: ...

    def confirm_delivery(self, *, timeout_seconds: int) -> int: ...


@dataclass(frozen=True, slots=True)
class AggregationJobDispatchMessage:
    job: Any
    topic: str
    record_key: str
    value: dict[str, Any]
    headers: Sequence[tuple[str, bytes]]


@dataclass(frozen=True, slots=True)
class AggregationJobDispatchPlan:
    messages: list[AggregationJobDispatchMessage]

    @property
    def jobs(self) -> list[Any]:
        return [message.job for message in self.messages]

    @property
    def record_keys(self) -> list[str]:
        return [message.record_key for message in self.messages]


@dataclass(frozen=True)
class KafkaAggregationJobPublisher:
    event_publisher: EventPublisher

    def publish_job_requested(self, message: AggregationJobDispatchMessage) -> None:
        result = self.event_publisher.publish(
            EventPublishRequest(
                topic=message.topic,
                key=message.record_key,
                value=message.value,
                headers=message.headers,
            )
        )
        if not result.succeeded:
            raise RuntimeError(result.error_message or result.status.value)

    def confirm_delivery(self, *, timeout_seconds: int) -> int:
        result = self.event_publisher.confirm_delivery(timeout_seconds=timeout_seconds)
        return result.undelivered_count


def get_aggregation_job_publisher() -> AggregationJobPublisher:
    return KafkaAggregationJobPublisher(get_kafka_event_publisher())


def aggregation_job_record_key(job: Any) -> str:
    return f"{job.portfolio_id}|{job.aggregation_date.isoformat()}"


def aggregation_job_headers(job: Any) -> list[tuple[str, bytes]]:
    if not job.correlation_id:
        return []
    return [("correlation_id", job.correlation_id.encode("utf-8"))]


def aggregation_job_payload(job: Any) -> dict[str, Any]:
    event = PortfolioAggregationRequiredEvent(
        portfolio_id=job.portfolio_id,
        aggregation_date=job.aggregation_date,
        correlation_id=job.correlation_id,
    )
    return event_business_payload(
        event,
        include_correlation_id=True,
        mode="json",
    )


def plan_aggregation_job_dispatch(jobs: Sequence[Any]) -> AggregationJobDispatchPlan:
    return AggregationJobDispatchPlan(
        messages=[
            AggregationJobDispatchMessage(
                job=job,
                topic=KAFKA_PORTFOLIO_DAY_AGGREGATION_JOB_REQUESTED_TOPIC,
                record_key=aggregation_job_record_key(job),
                value=aggregation_job_payload(job),
                headers=aggregation_job_headers(job),
            )
            for job in jobs
        ]
    )


def publish_aggregation_dispatch_plan(
    *,
    plan: AggregationJobDispatchPlan,
    publisher: AggregationJobPublisher,
) -> None:
    record_keys = plan.record_keys
    jobs = plan.jobs
    for index, message in enumerate(plan.messages):
        try:
            publisher.publish_job_requested(message)
        except Exception as exc:
            _raise_aggregation_dispatch_failure(
                queued_count=index,
                published_jobs=jobs[:index],
                published_record_keys=record_keys[:index],
                remaining_jobs=jobs[index:],
                remaining_record_keys=record_keys[index:],
                publisher=publisher,
                cause=exc,
            )

    _confirm_aggregation_dispatch(
        jobs=jobs,
        record_keys=record_keys,
        publisher=publisher,
    )


def _raise_aggregation_dispatch_failure(
    *,
    queued_count: int,
    published_jobs: list[Any],
    published_record_keys: list[str],
    remaining_jobs: list[Any],
    remaining_record_keys: list[str],
    publisher: AggregationJobPublisher,
    cause: Exception,
) -> None:
    undelivered_count = publisher.confirm_delivery(timeout_seconds=10)
    if undelivered_count:
        affected_record_keys = [*published_record_keys, *remaining_record_keys]
        affected_keys = ", ".join(affected_record_keys)
        raise SchedulerDispatchError(
            message=(
                "Delivery confirmation timed out while recovering from aggregation dispatch "
                f"failure. Affected job keys: {affected_keys}."
            ),
            recovery_job_ids=present_job_ids([*published_jobs, *remaining_jobs]),
            recovery_record_keys=tuple(affected_record_keys),
            published_record_keys=tuple(published_record_keys),
            failure_phase=DISPATCH_CONFIRMATION_TIMEOUT_PHASE,
        ) from cause
    remaining_keys = ", ".join(remaining_record_keys)
    raise SchedulerDispatchError(
        message=(
            "Failed to dispatch aggregation jobs after "
            f"{queued_count} earlier job(s) were queued. Remaining job keys: {remaining_keys}."
        ),
        recovery_job_ids=present_job_ids(remaining_jobs),
        recovery_record_keys=tuple(remaining_record_keys),
        published_record_keys=tuple(published_record_keys),
        failure_phase=DISPATCH_PUBLISH_FAILURE_PHASE,
    ) from cause


def _confirm_aggregation_dispatch(
    *,
    jobs: list[Any],
    record_keys: list[str],
    publisher: AggregationJobPublisher,
) -> None:
    undelivered_count = publisher.confirm_delivery(timeout_seconds=10)
    if not undelivered_count:
        return
    affected_keys = ", ".join(record_keys)
    raise SchedulerDispatchError(
        message=(
            "Delivery confirmation timed out while dispatching aggregation jobs. "
            f"Affected job keys: {affected_keys}."
        ),
        recovery_job_ids=present_job_ids(jobs),
        recovery_record_keys=tuple(record_keys),
        published_record_keys=tuple(record_keys),
        failure_phase=DISPATCH_CONFIRMATION_TIMEOUT_PHASE,
    )
