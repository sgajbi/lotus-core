"""Guard bounded corporate-action release Prometheus labels."""

from prometheus_client import CollectorRegistry, generate_latest

from src.services.portfolio_transaction_processing_service.app.infrastructure.corporate_action_release_observability import (  # noqa: E501
    PrometheusCorporateActionReleaseObserver,
)
from src.services.portfolio_transaction_processing_service.app.ports.corporate_action_release_observability import (  # noqa: E501
    CorporateActionLeaseRenewalOutcome,
    CorporateActionReleaseCycleOutcome,
)


def test_prometheus_observer_exposes_only_bounded_outcome_labels() -> None:
    registry = CollectorRegistry()
    observer = PrometheusCorporateActionReleaseObserver(registry=registry)

    observer.observe_cycle(CorporateActionReleaseCycleOutcome.COMPLETE, 0.25)
    observer.observe_lease_renewal(CorporateActionLeaseRenewalOutcome.RENEWED)

    metrics = generate_latest(registry).decode("utf-8")
    assert 'outcome="complete"' in metrics
    assert 'outcome="renewed"' in metrics
    for forbidden in (
        "portfolio_id",
        "corporate_action_event_id",
        "transaction_id",
        "tenant_id",
        "legal_book_id",
        "lease_token",
        "reason_code",
    ):
        assert forbidden not in metrics
