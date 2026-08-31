"""Typed ports and boundary records for corporate-action reconciliation."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from portfolio_common.domain.tenant import TenantId

from ..domain.transaction import BookedTransaction


@dataclass(frozen=True, slots=True)
class CorporateActionReconciliationKey:
    """Identify one portfolio-owned linked corporate-action group."""

    tenant_id: str
    portfolio_id: str
    linked_transaction_group_id: str
    parent_event_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", TenantId(self.tenant_id).value)


@dataclass(frozen=True, slots=True)
class CorporateActionReconciliationRunEvidence:
    """Describe one deterministic corporate-action reconciliation run."""

    run_id: str
    reconciliation_type: str
    portfolio_id: str
    business_date: date
    epoch: int | None
    status: str
    requested_by: str
    dedupe_key: str
    correlation_id: str | None
    tolerance: Decimal
    summary: dict[str, object]
    failure_reason: str | None
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class CorporateActionReconciliationFindingEvidence:
    """Describe one deterministic support finding from a reconciliation run."""

    finding_id: str
    run_id: str
    reconciliation_type: str
    finding_type: str
    severity: str
    portfolio_id: str
    security_id: str
    transaction_id: str
    business_date: date
    epoch: int | None
    expected_value: dict[str, object]
    observed_value: dict[str, object]
    detail: dict[str, object]
    owner: str
    resolution_state: str
    tolerance: Decimal | None
    observed_delta: Decimal | None
    repair_recommendation: str


@dataclass(frozen=True, slots=True)
class CorporateActionReconciliationEvidence:
    """Group the run and findings produced by one reconciliation assessment."""

    tenant_id: str
    run: CorporateActionReconciliationRunEvidence
    findings: tuple[CorporateActionReconciliationFindingEvidence, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", TenantId(self.tenant_id).value)


@dataclass(frozen=True, slots=True)
class CorporateActionReconciliationObservation:
    """Expose reconciliation outcomes without coupling the application to telemetry."""

    key: CorporateActionReconciliationKey
    processed_transaction: BookedTransaction
    reconciliation_status: str
    source_leg_count: int
    target_leg_count: int
    cash_consideration_count: int
    fractional_cash_leg_count: int
    source_basis_out_local: Decimal
    target_basis_in_local: Decimal
    target_basis_retained_local: Decimal
    cash_basis_local: Decimal
    cash_consideration_basis_local: Decimal
    fractional_basis_local: Decimal
    missing_cash_basis_count: int
    excluded_cash_settlement_adjustment_count: int
    unsupported_adjustment_count: int
    net_basis_delta_local: Decimal
    basis_tolerance: Decimal
    missing_dependency_reference_ids: tuple[str, ...]
    finding_severities: tuple[str, ...]
    linkage_finding_count: int = 0


class CorporateActionReconciliationRepository(Protocol):
    """Load linked transactions and persist source-owned reconciliation evidence."""

    async def load_group(
        self, key: CorporateActionReconciliationKey
    ) -> tuple[BookedTransaction, ...]: ...

    async def save_evidence(self, evidence: CorporateActionReconciliationEvidence) -> None: ...


class CorporateActionReconciliationObserver(Protocol):
    """Observe a successfully persisted corporate-action reconciliation result."""

    def observe(self, observation: CorporateActionReconciliationObservation) -> None: ...
