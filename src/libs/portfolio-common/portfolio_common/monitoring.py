# src/libs/portfolio-common/portfolio_common/monitoring.py
import logging
from collections import Counter as CollectionsCounter

from prometheus_client import Counter, Gauge, Histogram

from portfolio_common.observability_contracts import PORTFOLIO_SUPPORTABILITY_METRIC_LABELS

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------
# DB metrics (used by portfolio_common.utils.async_timed, etc.)
# --------------------------------------------------------------------------------------
DB_OPERATION_LATENCY_SECONDS = Histogram(
    "db_operation_latency_seconds",
    "Latency of database operations in seconds",
    labelnames=("repository", "method"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def db_timer(operation: str):
    """
    Backwards/ergonomic helper. Times a DB operation using a generic repository label.
    Usage:
        with db_timer("transaction_upsert"):
            ...
    """
    return DB_OPERATION_LATENCY_SECONDS.labels(repository="db", method=operation).time()


# --------------------------------------------------------------------------------------
# Kafka (generic) metrics – available for any service to use
# --------------------------------------------------------------------------------------
KAFKA_MESSAGES_PUBLISHED_TOTAL = Counter(
    "kafka_messages_published_total",
    "Number of messages successfully published to Kafka",
    labelnames=("topic",),
)

KAFKA_PUBLISH_ERRORS_TOTAL = Counter(
    "kafka_publish_errors_total",
    "Number of Kafka publish errors",
    labelnames=("topic", "error"),
)

KAFKA_MESSAGES_CONSUMED_TOTAL = Counter(
    "kafka_messages_consumed_total",
    "Number of messages consumed from Kafka",
    labelnames=("topic", "group_id"),
)

KAFKA_CONSUME_ERRORS_TOTAL = Counter(
    "kafka_consume_errors_total",
    "Number of Kafka consume errors",
    labelnames=("topic", "error"),
)

KAFKA_PUBLISH_LATENCY_SECONDS = Histogram(
    "kafka_publish_latency_seconds",
    "Kafka publish latency in seconds by topic",
    labelnames=("topic",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

KAFKA_CONSUMER_EVENTS_TOTAL = Counter(
    "kafka_consumer_events_total",
    "Standard Kafka consumer lifecycle and processing events.",
    labelnames=("service", "topic", "group_id", "outcome", "reason"),
)

KAFKA_PRODUCER_EVENTS_TOTAL = Counter(
    "kafka_producer_events_total",
    "Standard Kafka producer publish events.",
    labelnames=("service", "topic", "outcome", "reason"),
)

RETRY_POLICY_EVENTS_TOTAL = Counter(
    "retry_policy_events_total",
    "Bounded retry policy events.",
    labelnames=("profile", "outcome", "reason"),
)

KAFKA_CONSUMER_PROCESSING_DURATION_SECONDS = Histogram(
    "kafka_consumer_processing_duration_seconds",
    "Kafka consumer message processing duration in seconds.",
    labelnames=("service", "topic", "group_id"),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

KAFKA_CONSUMER_IN_FLIGHT_MESSAGES = Gauge(
    "kafka_consumer_in_flight_messages",
    "Kafka consumer messages currently in application processing.",
    labelnames=("service", "topic", "group_id"),
)

KAFKA_CONSUMER_POLL_IDLE_SECONDS = Histogram(
    "kafka_consumer_poll_idle_seconds",
    "Kafka consumer poll calls that returned no message.",
    labelnames=("service", "topic", "group_id"),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

KAFKA_CONSUMER_BACKLOG_PRESSURE_TOTAL = Counter(
    "kafka_consumer_backlog_pressure_total",
    "Kafka consumer times polling paused or messages were queued because worker capacity was full.",
    labelnames=("service", "topic", "group_id", "reason"),
)

HEALTH_DEPENDENCY_CHECKS_TOTAL = Counter(
    "health_dependency_check_total",
    "Health dependency check outcomes by service, dependency, and bounded status.",
    labelnames=("service", "dependency", "status"),
)

HEALTH_DEPENDENCY_CHECK_DURATION_SECONDS = Histogram(
    "health_dependency_check_duration_seconds",
    "Health dependency check latency in seconds by service and dependency.",
    labelnames=("service", "dependency"),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

HEALTH_READINESS_STATE = Gauge(
    "health_readiness_state",
    "Current readiness state for a service. ready=1 for the active state, 0 otherwise.",
    labelnames=("service", "state"),
)

HEALTH_READINESS_STATES = ("ready", "not_ready")


def observe_kafka_published(topic: str, count: int = 1) -> None:
    KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic).inc(count)


def observe_kafka_publish_error(topic: str, error: str, count: int = 1) -> None:
    KAFKA_PUBLISH_ERRORS_TOTAL.labels(topic, error).inc(count)


def observe_kafka_producer_event(
    *,
    service: str,
    topic: str,
    outcome: str,
    reason: str,
    count: int = 1,
) -> None:
    KAFKA_PRODUCER_EVENTS_TOTAL.labels(service, topic, outcome, reason).inc(count)


def observe_retry_policy_event(
    *,
    profile: str,
    outcome: str,
    reason: str,
    count: int = 1,
) -> None:
    RETRY_POLICY_EVENTS_TOTAL.labels(profile, outcome, reason).inc(count)


def observe_kafka_consumed(topic: str, group_id: str, count: int = 1) -> None:
    KAFKA_MESSAGES_CONSUMED_TOTAL.labels(topic, group_id).inc(count)


def observe_kafka_consume_error(topic: str, error: str, count: int = 1) -> None:
    KAFKA_CONSUME_ERRORS_TOTAL.labels(topic, error).inc(count)


def kafka_publish_timer(topic: str):
    """Context manager that observes Kafka publish latency for a topic."""
    return KAFKA_PUBLISH_LATENCY_SECONDS.labels(topic).time()


def observe_kafka_consumer_event(
    *,
    service: str,
    topic: str,
    group_id: str,
    outcome: str,
    reason: str,
) -> None:
    KAFKA_CONSUMER_EVENTS_TOTAL.labels(service, topic, group_id, outcome, reason).inc()


def observe_kafka_consumer_processing_duration(
    *,
    service: str,
    topic: str,
    group_id: str,
    duration_seconds: float,
) -> None:
    KAFKA_CONSUMER_PROCESSING_DURATION_SECONDS.labels(service, topic, group_id).observe(
        max(0.0, duration_seconds)
    )


def set_kafka_consumer_in_flight(
    *,
    service: str,
    topic: str,
    group_id: str,
    count: int,
) -> None:
    KAFKA_CONSUMER_IN_FLIGHT_MESSAGES.labels(service, topic, group_id).set(max(0, count))


def observe_kafka_consumer_poll_idle_duration(
    *,
    service: str,
    topic: str,
    group_id: str,
    duration_seconds: float,
) -> None:
    KAFKA_CONSUMER_POLL_IDLE_SECONDS.labels(service, topic, group_id).observe(
        max(0.0, duration_seconds)
    )


def observe_kafka_consumer_backlog_pressure(
    *,
    service: str,
    topic: str,
    group_id: str,
    reason: str,
) -> None:
    KAFKA_CONSUMER_BACKLOG_PRESSURE_TOTAL.labels(service, topic, group_id, reason).inc()


def observe_health_dependency_check(
    *,
    service: str,
    dependency: str,
    status: str,
    duration_seconds: float,
) -> None:
    HEALTH_DEPENDENCY_CHECKS_TOTAL.labels(service, dependency, status).inc()
    HEALTH_DEPENDENCY_CHECK_DURATION_SECONDS.labels(service, dependency).observe(
        max(0.0, duration_seconds)
    )


def set_health_readiness_state(*, service: str, state: str) -> None:
    normalized_state = state if state in HEALTH_READINESS_STATES else "not_ready"
    for candidate in HEALTH_READINESS_STATES:
        HEALTH_READINESS_STATE.labels(service, candidate).set(
            1 if candidate == normalized_state else 0
        )


# --------------------------------------------------------------------------------------
# Outbox Dispatcher Metrics
# --------------------------------------------------------------------------------------
_OUTBOX_PUBLISHED = Counter(
    "outbox_events_published_total",
    "Number of outbox events successfully published to Kafka",
    labelnames=("aggregate_type", "topic"),
)

_OUTBOX_FAILED = Counter(
    "outbox_events_failed_total",
    "Number of outbox events that failed to publish to Kafka",
    labelnames=("aggregate_type", "topic"),
)

_OUTBOX_RETRIED = Counter(
    "outbox_events_retried_total",
    "Number of outbox events marked for retry after failed publishes",
    labelnames=("aggregate_type", "topic"),
)

_OUTBOX_PENDING = Gauge(
    "outbox_events_pending",
    "Total number of PENDING outbox events in the database",
)

_OUTBOX_RETRY_ELIGIBLE_PENDING = Gauge(
    "outbox_events_retry_eligible_pending",
    "Total number of PENDING outbox events eligible for immediate dispatch or retry.",
)

_OUTBOX_RETRY_WAITING_PENDING = Gauge(
    "outbox_events_retry_waiting_pending",
    "Total number of PENDING outbox events waiting for a future retry eligibility timestamp.",
)

_OUTBOX_FAILED_STORED = Gauge(
    "outbox_events_failed_stored",
    "Total number of terminal FAILED outbox events in the database",
)

_OUTBOX_OLDEST_PENDING_AGE_SECONDS = Gauge(
    "outbox_events_oldest_pending_age_seconds",
    "Age in seconds of the oldest PENDING outbox event in the database",
)

_OUTBOX_BATCH_SECONDS = Histogram(
    "outbox_dispatch_batch_seconds",
    "Time taken to process one outbox dispatch batch (lock, publish, update statuses).",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

_OUTBOX_RECOVERY_ATTEMPTS = Counter(
    "outbox_recovery_attempts_total",
    "Number of governed failed-outbox recovery command attempts by bounded outcome.",
    labelnames=("recovery_action", "outcome", "reason"),
)

_CONTROL_QUEUE_PENDING = Gauge(
    "control_queue_pending",
    "Total number of pending rows in durable control queues.",
    labelnames=("queue",),
)

_CONTROL_QUEUE_FAILED_STORED = Gauge(
    "control_queue_failed_stored",
    "Total number of terminal failed rows in durable control queues.",
    labelnames=("queue",),
)

_CONTROL_QUEUE_OLDEST_PENDING_AGE_SECONDS = Gauge(
    "control_queue_oldest_pending_age_seconds",
    "Age in seconds of the oldest pending row in durable control queues.",
    labelnames=("queue",),
)


def observe_outbox_published(aggregate_type: str, topic: str, count: int = 1) -> None:
    _OUTBOX_PUBLISHED.labels(aggregate_type, topic).inc(count)


def observe_outbox_failed(aggregate_type: str, topic: str, count: int = 1) -> None:
    _OUTBOX_FAILED.labels(aggregate_type, topic).inc(count)


def observe_outbox_retried(aggregate_type: str, topic: str, count: int = 1) -> None:
    _OUTBOX_RETRIED.labels(aggregate_type, topic).inc(count)


def set_outbox_pending(total_pending: int) -> None:
    _OUTBOX_PENDING.set(total_pending)


def set_outbox_retry_eligible_pending(total_pending: int) -> None:
    _OUTBOX_RETRY_ELIGIBLE_PENDING.set(total_pending)


def set_outbox_retry_waiting_pending(total_pending: int) -> None:
    _OUTBOX_RETRY_WAITING_PENDING.set(total_pending)


def set_outbox_failed_stored(total_failed: int) -> None:
    _OUTBOX_FAILED_STORED.set(total_failed)


def set_outbox_oldest_pending_age_seconds(age_seconds: float) -> None:
    _OUTBOX_OLDEST_PENDING_AGE_SECONDS.set(age_seconds)


def outbox_batch_timer():
    """Context manager that observes outbox batch duration."""
    return _OUTBOX_BATCH_SECONDS.time()


def observe_outbox_recovery_attempt(
    recovery_action: str,
    outcome: str,
    reason: str,
    count: int = 1,
) -> None:
    _OUTBOX_RECOVERY_ATTEMPTS.labels(recovery_action, outcome, reason).inc(count)


def set_control_queue_pending(queue: str, total_pending: int) -> None:
    _CONTROL_QUEUE_PENDING.labels(queue).set(total_pending)


def set_control_queue_failed_stored(queue: str, total_failed: int) -> None:
    _CONTROL_QUEUE_FAILED_STORED.labels(queue).set(total_failed)


def set_control_queue_oldest_pending_age_seconds(queue: str, age_seconds: float) -> None:
    _CONTROL_QUEUE_OLDEST_PENDING_AGE_SECONDS.labels(queue).set(age_seconds)


# --------------------------------------------------------------------------------------
# Reprocessing & Epoch Metrics
# --------------------------------------------------------------------------------------
INSTRUMENT_REPROCESSING_TRIGGERS_PENDING = Gauge(
    "instrument_reprocessing_triggers_pending",
    "Total number of pending instrument reprocessing triggers awaiting fan-out.",
)

EPOCH_MISMATCH_DROPPED_TOTAL = Counter(
    "epoch_mismatch_dropped_total",
    "Number of Kafka messages dropped due to a stale epoch.",
    labelnames=("service_name", "topic"),
)

REPROCESSING_ACTIVE_KEYS_TOTAL = Gauge(
    "reprocessing_active_keys_total",
    "Total number of (portfolio, security) keys currently in a REPROCESSING state.",
)

SNAPSHOT_LAG_SECONDS = Histogram(
    "snapshot_lag_seconds",
    "The lag between the latest business date and a key's watermark, in seconds.",
    buckets=(3600, 86400, 172800, 604800, 2592000),  # 1hr, 1d, 2d, 1wk, 30d
)

SCHEDULER_GAP_DAYS = Histogram(
    "scheduler_gap_days",
    "The gap in days between the latest business date and a key's watermark.",
    buckets=(1, 2, 5, 10, 30, 90, 365),
)

REPROCESSING_EPOCH_BUMPED_TOTAL = Counter(
    "reprocessing_epoch_bumped_total",
    "Total number of times a reprocessing flow was triggered by an epoch increment.",
    labelnames=("trigger",),
)

REPROCESSING_WORKER_JOBS_CLAIMED_TOTAL = Counter(
    "reprocessing_worker_jobs_claimed_total",
    "Total number of reprocessing jobs claimed by the worker.",
    ["job_type"],
)

REPROCESSING_WORKER_JOBS_COMPLETED_TOTAL = Counter(
    "reprocessing_worker_jobs_completed_total",
    "Total number of reprocessing jobs completed by the worker.",
    ["job_type"],
)

REPROCESSING_WORKER_JOBS_NOOP_TOTAL = Counter(
    "reprocessing_worker_jobs_noop_total",
    "Total number of reprocessing jobs that completed without mutating any state.",
    ["job_type", "reason"],
)

REPROCESSING_WORKER_JOBS_FAILED_TOTAL = Counter(
    "reprocessing_worker_jobs_failed_total",
    "Total number of reprocessing jobs that failed in worker processing.",
    ["job_type"],
)

REPROCESSING_WORKER_BATCH_SECONDS = Histogram(
    "reprocessing_worker_batch_seconds",
    "Time taken to claim and process one reprocessing worker batch.",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

REPROCESSING_DUPLICATES_NORMALIZED_TOTAL = Counter(
    "reprocessing_duplicates_normalized_total",
    "Number of duplicate replay or reprocessing records normalized away on durable paths.",
    ["scope"],
)

REPROCESSING_STALE_SKIPS_TOTAL = Counter(
    "reprocessing_stale_skips_total",
    "Number of stale epoch-fenced records skipped during replay normalization or fanout.",
    ["stage"],
)

POSITION_STATE_WATERMARK_LAG_DAYS = Gauge(
    "position_state_watermark_lag_days",
    "The most recently observed lag in days between the latest business date "
    "and a key's watermark.",
)

VALUATION_JOBS_CREATED_TOTAL = Counter(
    "valuation_jobs_created_total",
    "Total number of valuation jobs created by the scheduler.",
    labelnames=("job_type",),
)

VALUATION_JOBS_SKIPPED_TOTAL = Counter(
    "valuation_jobs_skipped_total",
    "Total number of valuation jobs skipped by the consumer due to no position history.",
    labelnames=("reason",),
)

VALUATION_JOBS_FAILED_TOTAL = Counter(
    "valuation_jobs_failed_total",
    "Total number of valuation jobs that failed for terminal reasons (e.g., missing ref data).",
    labelnames=("reason",),
)

VALUATION_SCHEDULER_POLL_DURATION_SECONDS = Histogram(
    "valuation_scheduler_poll_duration_seconds",
    "Duration of valuation scheduler poll work in seconds.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60),
)

VALUATION_SCHEDULER_JOBS_CLAIMED_TOTAL = Counter(
    "valuation_scheduler_jobs_claimed_total",
    "Total number of valuation jobs claimed by the scheduler for dispatch.",
)

VALUATION_SCHEDULER_JOBS_DISPATCHED_TOTAL = Counter(
    "valuation_scheduler_jobs_dispatched_total",
    "Total number of valuation jobs confirmed or handed off for dispatch by the scheduler.",
)

VALUATION_SCHEDULER_BUDGET_EXHAUSTED_TOTAL = Counter(
    "valuation_scheduler_budget_exhausted_total",
    "Number of valuation scheduler poll or dispatch budget exhaustion events.",
    labelnames=("stage",),
)

VALUATION_SCHEDULER_PRODUCER_BACKPRESSURE_TOTAL = Counter(
    "valuation_scheduler_producer_backpressure_total",
    "Number of valuation scheduler dispatch stops caused by producer back-pressure.",
)

VALUATION_WORKER_JOBS_CLAIMED_TOTAL = Counter(
    "valuation_worker_jobs_claimed_total",
    "Total number of valuation jobs claimed for processing.",
)

VALUATION_WORKER_STALE_RESETS_TOTAL = Counter(
    "valuation_worker_stale_resets_total",
    "Total number of stale valuation jobs reset from PROCESSING to PENDING.",
)

CASHFLOWS_CREATED_TOTAL = Counter(
    "cashflows_created_total",
    "Total number of cashflows created, by classification and timing.",
    ["classification", "timing"],
)

CASHFLOW_RULE_CACHE_EVENTS_TOTAL = Counter(
    "cashflow_rule_cache_events_total",
    "Cashflow rule cache events for hit, miss, reload, stale, invalidation, "
    "and missing-rule paths.",
    labelnames=("outcome", "reason"),
)

BUY_LIFECYCLE_STAGE_TOTAL = Counter(
    "buy_lifecycle_stage_total",
    "Count of BUY lifecycle stage outcomes.",
    ["stage", "status"],
)

SELL_LIFECYCLE_STAGE_TOTAL = Counter(
    "sell_lifecycle_stage_total",
    "Count of SELL lifecycle stage outcomes.",
    ["stage", "status"],
)

INGESTION_JOBS_CREATED_TOTAL = Counter(
    "ingestion_jobs_created_total",
    "Number of ingestion jobs created by endpoint and entity type.",
    ["endpoint", "entity_type"],
)

INGESTION_JOBS_RETRIED_TOTAL = Counter(
    "ingestion_jobs_retried_total",
    "Number of ingestion job retries attempted.",
    ["endpoint", "entity_type", "result"],
)

INGESTION_JOBS_FAILED_TOTAL = Counter(
    "ingestion_jobs_failed_total",
    "Number of ingestion jobs marked failed.",
    ["endpoint", "entity_type", "failure_phase"],
)

INGESTION_BACKLOG_AGE_SECONDS = Gauge(
    "ingestion_backlog_age_seconds",
    "Current age in seconds of oldest non-terminal ingestion job.",
)

INGESTION_MODE_STATE = Gauge(
    "ingestion_mode_state",
    "Current ingestion operations mode: normal=0, paused=1, drain=2.",
)

INGESTION_REPLAY_AUDIT_TOTAL = Counter(
    "ingestion_replay_audit_total",
    "Replay audit events recorded for ingestion recovery paths.",
    ["recovery_path", "replay_status"],
)

INGESTION_REPLAY_DUPLICATE_BLOCKED_TOTAL = Counter(
    "ingestion_replay_duplicate_blocked_total",
    "Replay attempts blocked due to duplicate deterministic fingerprint.",
    ["recovery_path"],
)

INGESTION_REPLAY_FAILURE_TOTAL = Counter(
    "ingestion_replay_failure_total",
    "Replay attempts that failed or were not replayable.",
    ["recovery_path", "replay_status"],
)

ANALYTICS_EXPORT_JOBS_TOTAL = Counter(
    "analytics_export_jobs_total",
    "Number of analytics export jobs by dataset_type and terminal status.",
    ["dataset_type", "status"],
)

ANALYTICS_EXPORT_JOB_DURATION_SECONDS = Histogram(
    "analytics_export_job_duration_seconds",
    "Duration of analytics export job execution in seconds.",
    labelnames=("dataset_type",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 60),
)

ANALYTICS_EXPORT_RESULT_BYTES = Histogram(
    "analytics_export_result_bytes",
    "Serialized payload size for analytics export results.",
    labelnames=("result_format", "compression"),
    buckets=(1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216),
)

ANALYTICS_EXPORT_PAGE_DEPTH = Histogram(
    "analytics_export_page_depth",
    "Number of source pages traversed while building analytics export result.",
    labelnames=("dataset_type",),
    buckets=(1, 2, 5, 10, 20, 50, 100, 200),
)

FINANCIAL_RECONCILIATION_RUNS_TOTAL = Counter(
    "financial_reconciliation_runs_total",
    "Number of reconciliation runs completed by reconciliation type and terminal status.",
    ["reconciliation_type", "status"],
)

FINANCIAL_RECONCILIATION_FINDINGS_TOTAL = Counter(
    "financial_reconciliation_findings_total",
    "Number of reconciliation findings recorded by reconciliation type and severity.",
    ["reconciliation_type", "severity"],
)

FINANCIAL_RECONCILIATION_RUN_DURATION_SECONDS = Histogram(
    "financial_reconciliation_run_duration_seconds",
    "Duration of reconciliation runs in seconds.",
    labelnames=("reconciliation_type", "status"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)

LOTUS_CORE_PORTFOLIO_SUPPORTABILITY_TOTAL = Counter(
    "lotus_core_portfolio_supportability_total",
    "Portfolio supportability readiness summaries emitted by lotus-core.",
    PORTFOLIO_SUPPORTABILITY_METRIC_LABELS,
)


def observe_reprocessing_worker_jobs_claimed(job_type: str, count: int = 1) -> None:
    REPROCESSING_WORKER_JOBS_CLAIMED_TOTAL.labels(job_type).inc(count)


def observe_reprocessing_worker_jobs_completed(job_type: str, count: int = 1) -> None:
    REPROCESSING_WORKER_JOBS_COMPLETED_TOTAL.labels(job_type).inc(count)


def observe_reprocessing_worker_jobs_noop(job_type: str, reason: str, count: int = 1) -> None:
    REPROCESSING_WORKER_JOBS_NOOP_TOTAL.labels(job_type, reason).inc(count)


def observe_reprocessing_worker_jobs_failed(job_type: str, count: int = 1) -> None:
    REPROCESSING_WORKER_JOBS_FAILED_TOTAL.labels(job_type).inc(count)


def reprocessing_worker_batch_timer():
    """Context manager that observes one reprocessing worker batch duration."""
    return REPROCESSING_WORKER_BATCH_SECONDS.time()


def observe_reprocessing_duplicates_normalized(scope: str, count: int = 1) -> None:
    REPROCESSING_DUPLICATES_NORMALIZED_TOTAL.labels(scope).inc(count)


def observe_reprocessing_stale_skips(stage: str, count: int = 1) -> None:
    REPROCESSING_STALE_SKIPS_TOTAL.labels(stage).inc(count)


def observe_valuation_scheduler_poll_duration(duration_seconds: float) -> None:
    VALUATION_SCHEDULER_POLL_DURATION_SECONDS.observe(max(duration_seconds, 0.0))


def observe_valuation_scheduler_jobs_claimed(count: int = 1) -> None:
    VALUATION_SCHEDULER_JOBS_CLAIMED_TOTAL.inc(count)


def observe_valuation_scheduler_jobs_dispatched(count: int = 1) -> None:
    VALUATION_SCHEDULER_JOBS_DISPATCHED_TOTAL.inc(count)


def observe_valuation_scheduler_budget_exhausted(stage: str, count: int = 1) -> None:
    VALUATION_SCHEDULER_BUDGET_EXHAUSTED_TOTAL.labels(stage).inc(count)


def observe_valuation_scheduler_producer_backpressure(count: int = 1) -> None:
    VALUATION_SCHEDULER_PRODUCER_BACKPRESSURE_TOTAL.inc(count)


def observe_valuation_worker_jobs_claimed(count: int = 1) -> None:
    VALUATION_WORKER_JOBS_CLAIMED_TOTAL.inc(count)


def observe_valuation_worker_stale_resets(count: int = 1) -> None:
    VALUATION_WORKER_STALE_RESETS_TOTAL.inc(count)


def observe_cashflow_rule_cache_event(outcome: str, reason: str, count: int = 1) -> None:
    CASHFLOW_RULE_CACHE_EVENTS_TOTAL.labels(outcome, reason).inc(count)


def observe_portfolio_supportability(
    state: str,
    reason: str,
    freshness_bucket: str,
    count: int = 1,
) -> None:
    LOTUS_CORE_PORTFOLIO_SUPPORTABILITY_TOTAL.labels(
        state,
        reason,
        freshness_bucket,
    ).inc(count)


# --------------------------------------------------------------------------------------
# Optional generic HTTP metrics (use across services if helpful)
# --------------------------------------------------------------------------------------
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "HTTP requests total",
    labelnames=("service", "method", "endpoint_template", "status"),
)

HTTP_REQUEST_LATENCY_SECONDS = Histogram(
    "http_request_latency_seconds",
    "HTTP request latency in seconds",
    labelnames=("service", "method", "endpoint_template"),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def http_request_timer(service: str, method: str, endpoint_template: str):
    """Context manager for timing an HTTP request handler."""
    return HTTP_REQUEST_LATENCY_SECONDS.labels(service, method, endpoint_template).time()


def observe_financial_reconciliation_run(
    reconciliation_type: str,
    status: str,
    duration_seconds: float,
    findings: list[object] | None = None,
) -> None:
    FINANCIAL_RECONCILIATION_RUNS_TOTAL.labels(reconciliation_type, status).inc()
    FINANCIAL_RECONCILIATION_RUN_DURATION_SECONDS.labels(
        reconciliation_type,
        status,
    ).observe(duration_seconds)
    if not findings:
        return
    severity_counts = CollectionsCounter(
        str(getattr(finding, "severity", "UNKNOWN")).upper() for finding in findings
    )
    for severity, count in severity_counts.items():
        FINANCIAL_RECONCILIATION_FINDINGS_TOTAL.labels(reconciliation_type, severity).inc(count)
