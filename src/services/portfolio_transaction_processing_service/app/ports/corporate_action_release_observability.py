"""Bounded observability contract for corporate-action release execution."""

from enum import StrEnum
from typing import Protocol


class CorporateActionReleaseCycleOutcome(StrEnum):
    IDLE = "idle"
    ADVANCED = "advanced"
    COMPLETE = "complete"
    FAILED = "failed"
    RETRYABLE_ERROR = "retryable_error"
    DATABASE_ERROR = "database_error"


class CorporateActionLeaseRenewalOutcome(StrEnum):
    RENEWED = "renewed"
    LOST = "lost"


class CorporateActionReleaseObserver(Protocol):
    def observe_cycle(
        self,
        outcome: CorporateActionReleaseCycleOutcome,
        duration_seconds: float,
    ) -> None: ...

    def observe_lease_renewal(
        self,
        outcome: CorporateActionLeaseRenewalOutcome,
    ) -> None: ...


class NoopCorporateActionReleaseObserver:
    def observe_cycle(
        self,
        outcome: CorporateActionReleaseCycleOutcome,
        duration_seconds: float,
    ) -> None:
        del outcome, duration_seconds

    def observe_lease_renewal(
        self,
        outcome: CorporateActionLeaseRenewalOutcome,
    ) -> None:
        del outcome


NOOP_CORPORATE_ACTION_RELEASE_OBSERVER = NoopCorporateActionReleaseObserver()
