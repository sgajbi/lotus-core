"""Shared observability contract constants for lotus-core surfaces."""

TELEMETRY_METRIC_ALLOWED_LABELS: tuple[str, ...] = (
    "aggregate_type",
    "classification",
    "compression",
    "consumer_group",
    "cost_basis_method",
    "dataset_type",
    "dependency",
    "endpoint",
    "endpoint_template",
    "entity_type",
    "error",
    "failure_phase",
    "freshness_bucket",
    "group_id",
    "job_type",
    "method",
    "mode",
    "outcome",
    "partition",
    "pool",
    "profile",
    "queue",
    "reason",
    "reconciliation_type",
    "recovery_action",
    "recovery_path",
    "repository",
    "replay_status",
    "result",
    "result_format",
    "scope",
    "service",
    "service_name",
    "severity",
    "stage",
    "state",
    "status",
    "timing",
    "topic",
    "trigger",
)

TELEMETRY_METRIC_FORBIDDEN_LABELS: tuple[str, ...] = (
    "account_id",
    "body",
    "client_id",
    "correlation_id",
    "error_message",
    "error_text",
    "exception",
    "message",
    "path",
    "payload",
    "portfolio_id",
    "raw_error",
    "raw_path",
    "request_id",
    "security_id",
    "span_id",
    "stacktrace",
    "trace_id",
    "traceparent",
)

PORTFOLIO_SUPPORTABILITY_METRIC_LABELS: tuple[str, ...] = (
    "state",
    "reason",
    "freshness_bucket",
)

SERVICE_LOCAL_METRIC_OWNERS: dict[str, str] = {
    "cost_processing_execution_total": "cost_calculator_service",
    "cost_processing_open_lots_restored": "cost_calculator_service",
    "event_processing_latency_seconds": "persistence_service",
    "events_dlqd_total": "persistence_service",
    "events_processed_total": "persistence_service",
    "lotus_core_transaction_processing_operation_duration_seconds": (
        "portfolio_transaction_processing_service"
    ),
    "lotus_core_transaction_processing_operations_total": (
        "portfolio_transaction_processing_service"
    ),
    "recalculation_depth": "cost_calculator_service",
    "recalculation_duration_seconds": "cost_calculator_service",
}
