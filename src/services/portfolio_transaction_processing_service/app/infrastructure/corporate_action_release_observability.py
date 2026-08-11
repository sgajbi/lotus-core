"""Prometheus adapter for bounded corporate-action release outcomes."""

import logging

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Histogram

from ..ports.corporate_action_release_observability import (
    CorporateActionLeaseRenewalOutcome,
    CorporateActionReleaseCycleOutcome,
)

logger = logging.getLogger(__name__)

_DURATION_BUCKETS_SECONDS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 15, 30, 60)


class PrometheusCorporateActionReleaseObserver:
    """Record only bounded outcome labels; identifiers belong in support APIs and logs."""

    def __init__(self, *, registry: CollectorRegistry = REGISTRY) -> None:
        self._cycles = Counter(
            "lotus_core_corporate_action_release_cycles_total",
            "Corporate-action release worker cycles by bounded outcome.",
            labelnames=("outcome",),
            registry=registry,
        )
        self._duration = Histogram(
            "lotus_core_corporate_action_release_cycle_duration_seconds",
            "Corporate-action release worker cycle duration by bounded outcome.",
            labelnames=("outcome",),
            buckets=_DURATION_BUCKETS_SECONDS,
            registry=registry,
        )
        self._lease_renewals = Counter(
            "lotus_core_corporate_action_release_lease_renewals_total",
            "Corporate-action release lease renewals by bounded outcome.",
            labelnames=("outcome",),
            registry=registry,
        )

    def observe_cycle(
        self,
        outcome: CorporateActionReleaseCycleOutcome,
        duration_seconds: float,
    ) -> None:
        try:
            labels = {"outcome": outcome.value}
            self._cycles.labels(**labels).inc()
            self._duration.labels(**labels).observe(max(duration_seconds, 0.0))
        except Exception:
            logger.exception("Corporate-action release cycle metric recording failed.")

    def observe_lease_renewal(
        self,
        outcome: CorporateActionLeaseRenewalOutcome,
    ) -> None:
        try:
            self._lease_renewals.labels(outcome=outcome.value).inc()
        except Exception:
            logger.exception("Corporate-action release lease metric recording failed.")


PROMETHEUS_CORPORATE_ACTION_RELEASE_OBSERVER = PrometheusCorporateActionReleaseObserver()
