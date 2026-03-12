# src/libs/portfolio-common/portfolio_common/monitoring.py
import logging
from collections import Counter as CollectionsCounter

from prometheus_client import Counter, Gauge, Histogram

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


def observe_kafka_published(topic: str, count: int = 1) -> None:
    KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic).inc(count)


def observe_kafka_publish_error(topic: str, error: str, count: int = 1) -> None:
    KAFKA_PUBLISH_ERRORS_TOTAL.labels(topic, error).inc(count)


def observe_kafka_consumed(topic: str, group_id: str, count: int = 1) -> None:
    KAFKA_MESSAGES_CONSUMED_TOTAL.labels(topic, group_id).inc(count)


def observe_kafka_consume_error(topic: str, error: str, count: int = 1) -> None:
    KAFKA_CONSUME_ERRORS_TOTAL.labels(topic, error).inc(count)


def kafka_publish_timer(topic: str):
    """Context manager that observes Kafka publish latency for a topic."""
    return KAFKA_PUBLISH_LATENCY_SECONDS.labels(topic).time()


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

_OUTBOX_BATCH_SECONDS = Histogram(
    "outbox_dispatch_batch_seconds",
    "Time taken to process one outbox dispatch batch (lock, publish, update statuses).",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)


def observe_outbox_published(aggregate_type: str, topic: str, count: int = 1) -> None:
    _OUTBOX_PUBLISHED.labels(aggregate_type, topic).inc(count)


def observe_outbox_failed(aggregate_type: str, topic: str, count: int = 1) -> None:
    _OUTBOX_FAILED.labels(aggregate_type, topic).inc(count)


def observe_outbox_retried(aggregate_type: str, topic: str, count: int = 1) -> None:
    _OUTBOX_RETRIED.labels(aggregate_type, topic).inc(count)


def set_outbox_pending(total_pending: int) -> None:
    _OUTBOX_PENDING.set(total_pending)


def outbox_batch_timer():
    """Context manager that observes outbox batch duration."""
    return _OUTBOX_BATCH_SECONDS.time()


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
    labelnames=("service_name", "topic", "portfolio_id", "security_id"),
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
    labelnames=("portfolio_id", "security_id"),
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

POSITION_STATE_WATERMARK_LAG_DAYS = Gauge(
    "position_state_watermark_lag_days",
    "The current lag in days between the latest business date and a key's watermark.",
    labelnames=("portfolio_id", "security_id"),
)

VALUATION_JOBS_CREATED_TOTAL = Counter(
    "valuation_jobs_created_total",
    "Total number of valuation jobs created by the scheduler.",
    labelnames=("portfolio_id", "security_id"),
)

VALUATION_JOBS_SKIPPED_TOTAL = Counter(
    "valuation_jobs_skipped_total",
    "Total number of valuation jobs skipped by the consumer due to no position history.",
    labelnames=("portfolio_id", "security_id"),
)

VALUATION_JOBS_FAILED_TOTAL = Counter(
    "valuation_jobs_failed_total",
    "Total number of valuation jobs that failed for terminal reasons (e.g., missing ref data).",
    labelnames=("portfolio_id", "security_id", "reason"),
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


def observe_reprocessing_worker_jobs_claimed(job_type: str, count: int = 1) -> None:
    REPROCESSING_WORKER_JOBS_CLAIMED_TOTAL.labels(job_type).inc(count)


def observe_reprocessing_worker_jobs_completed(job_type: str, count: int = 1) -> None:
    REPROCESSING_WORKER_JOBS_COMPLETED_TOTAL.labels(job_type).inc(count)


def observe_reprocessing_worker_jobs_failed(job_type: str, count: int = 1) -> None:
    REPROCESSING_WORKER_JOBS_FAILED_TOTAL.labels(job_type).inc(count)


def reprocessing_worker_batch_timer():
    """Context manager that observes one reprocessing worker batch duration."""
    return REPROCESSING_WORKER_BATCH_SECONDS.time()


def observe_valuation_worker_jobs_claimed(count: int = 1) -> None:
    VALUATION_WORKER_JOBS_CLAIMED_TOTAL.inc(count)


def observe_valuation_worker_stale_resets(count: int = 1) -> None:
    VALUATION_WORKER_STALE_RESETS_TOTAL.inc(count)


# --------------------------------------------------------------------------------------
# Optional generic HTTP metrics (use across services if helpful)
# --------------------------------------------------------------------------------------
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "HTTP requests total",
    labelnames=("service", "method", "path", "status"),
)

HTTP_REQUEST_LATENCY_SECONDS = Histogram(
    "http_request_latency_seconds",
    "HTTP request latency in seconds",
    labelnames=("service", "method", "path"),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def http_request_timer(service: str, method: str, path: str):
    """Context manager for timing an HTTP request handler."""
    return HTTP_REQUEST_LATENCY_SECONDS.labels(service, method, path).time()


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
