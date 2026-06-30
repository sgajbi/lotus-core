import portfolio_common.monitoring as monitoring
from prometheus_client.metrics import MetricWrapperBase


def test_production_prometheus_metric_labels_exclude_business_identifiers():
    forbidden_labels = {"portfolio_id", "security_id"}
    metrics_with_forbidden_labels: dict[str, tuple[str, ...]] = {}

    for name, value in vars(monitoring).items():
        if not isinstance(value, MetricWrapperBase):
            continue
        labelnames = tuple(getattr(value, "_labelnames", ()))
        if forbidden_labels.intersection(labelnames):
            metrics_with_forbidden_labels[name] = labelnames

    assert metrics_with_forbidden_labels == {}
