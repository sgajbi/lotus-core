import portfolio_common.monitoring as monitoring
from prometheus_client.metrics import MetricWrapperBase


def test_production_prometheus_metric_labels_exclude_business_identifiers():
    forbidden_labels = {
        "account_id",
        "client_id",
        "correlation_id",
        "outbox_id",
        "portfolio_id",
        "requested_by",
        "request_body",
        "response_body",
        "security_id",
        "trace_id",
        "transaction_id",
    }
    metrics_with_forbidden_labels: dict[str, tuple[str, ...]] = {}

    for name, value in vars(monitoring).items():
        if not isinstance(value, MetricWrapperBase):
            continue
        labelnames = tuple(getattr(value, "_labelnames", ()))
        if forbidden_labels.intersection(labelnames):
            metrics_with_forbidden_labels[name] = labelnames

    assert metrics_with_forbidden_labels == {}


def test_outbox_recovery_metric_uses_bounded_operator_labels():
    assert monitoring._OUTBOX_RECOVERY_ATTEMPTS._labelnames == (
        "recovery_action",
        "outcome",
        "reason",
    )


def test_health_dependency_metrics_use_bounded_labels():
    assert monitoring.HEALTH_DEPENDENCY_CHECKS_TOTAL._labelnames == (
        "service",
        "dependency",
        "status",
    )
    assert monitoring.HEALTH_DEPENDENCY_CHECK_DURATION_SECONDS._labelnames == (
        "service",
        "dependency",
    )
    assert monitoring.HEALTH_READINESS_STATE._labelnames == ("service", "state")
    assert monitoring.HEALTH_READINESS_STATES == ("ready", "not_ready")
