"""Coordinate and build evidence for corporate-action basis reconciliation."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Sequence

from ..domain.cost_basis import (
    DEFAULT_CORPORATE_ACTION_BASIS_TOLERANCE,
    CorporateActionBasisReconciliation,
    CorporateActionBasisReconciliationStatus,
    missing_corporate_action_dependencies,
    reconcile_corporate_action_basis,
)
from ..domain.transaction import BookedTransaction
from ..domain.transaction.corporate_action import is_bundle_a_corporate_action
from ..ports.corporate_action_reconciliation import (
    CorporateActionReconciliationEvidence,
    CorporateActionReconciliationFindingEvidence,
    CorporateActionReconciliationKey,
    CorporateActionReconciliationObservation,
    CorporateActionReconciliationObserver,
    CorporateActionReconciliationRepository,
    CorporateActionReconciliationRunEvidence,
)

CORPORATE_ACTION_RECONCILIATION_TYPE = "corporate_action_bundle_a"
CORPORATE_ACTION_RECONCILIATION_REQUEST_OWNER = "cost-calculator"


class CorporateActionReconciliationFindingType(StrEnum):
    """Classify support findings emitted by corporate-action reconciliation."""

    BASIS_MISMATCH = "ca_bundle_a_basis_mismatch"
    INSUFFICIENT_CASH_BASIS = "ca_bundle_a_insufficient_cash_basis"
    INSUFFICIENT_LEGS = "ca_bundle_a_insufficient_legs"
    MISSING_DEPENDENCY = "ca_bundle_a_missing_dependency"


class CorporateActionReconciliationReasonCode(StrEnum):
    """Expose stable machine-readable reasons for reconciliation findings."""

    BASIS_MISMATCH = "CA_BUNDLE_A_BASIS_MISMATCH"
    INSUFFICIENT_CASH_BASIS = "CA_BUNDLE_A_INSUFFICIENT_CASH_BASIS"
    INSUFFICIENT_LEGS = "CA_BUNDLE_A_INSUFFICIENT_LEGS"
    MISSING_DEPENDENCY = "CA_BUNDLE_A_MISSING_DEPENDENCY"


class CorporateActionReconciliationCoordinator:
    """Reconcile each complete linked corporate-action group once per processing batch."""

    def __init__(
        self,
        repository: CorporateActionReconciliationRepository,
        *,
        observer: CorporateActionReconciliationObserver | None = None,
        clock: Callable[[], datetime] | None = None,
        basis_tolerance: Decimal = DEFAULT_CORPORATE_ACTION_BASIS_TOLERANCE,
    ) -> None:
        self._repository = repository
        self._observer = observer
        self._clock = clock or (lambda: datetime.now(UTC))
        self._basis_tolerance = basis_tolerance
        self._reconciled_groups: set[CorporateActionReconciliationKey] = set()

    async def reconcile(
        self,
        processed_transaction: BookedTransaction,
        *,
        correlation_id: str | None,
    ) -> CorporateActionReconciliationEvidence | None:
        """Persist and observe evidence when the transaction identifies a new complete group."""

        key = _reconciliation_key(processed_transaction)
        if key is None or key in self._reconciled_groups:
            return None

        group_transactions = await self._repository.load_group(key)
        reconciliation = reconcile_corporate_action_basis(
            group_transactions,
            basis_tolerance=self._basis_tolerance,
        )
        missing_dependencies = missing_corporate_action_dependencies(
            processed_transaction,
            {transaction.transaction_id for transaction in group_transactions},
        )
        evidence = build_corporate_action_reconciliation_evidence(
            processed_transaction=processed_transaction,
            linked_transaction_group_id=key.linked_transaction_group_id,
            parent_event_reference=key.parent_event_reference,
            reconciliation=reconciliation,
            missing_dependency_reference_ids=missing_dependencies,
            correlation_id=correlation_id,
            completed_at=self._clock(),
        )
        await self._repository.save_evidence(evidence)
        if self._observer is not None:
            self._observer.observe(
                _observation(
                    key=key,
                    processed_transaction=processed_transaction,
                    reconciliation=reconciliation,
                    missing_dependencies=missing_dependencies,
                    evidence=evidence,
                )
            )
        self._reconciled_groups.add(key)
        return evidence


def _reconciliation_key(
    transaction: BookedTransaction,
) -> CorporateActionReconciliationKey | None:
    if not is_bundle_a_corporate_action(transaction.transaction_type):
        return None
    linked_group = (transaction.linked_transaction_group_id or "").strip()
    parent_reference = (transaction.parent_event_reference or "").strip()
    if not linked_group or not parent_reference:
        return None
    return CorporateActionReconciliationKey(
        portfolio_id=transaction.portfolio_id,
        linked_transaction_group_id=linked_group,
        parent_event_reference=parent_reference,
    )


def _observation(
    *,
    key: CorporateActionReconciliationKey,
    processed_transaction: BookedTransaction,
    reconciliation: CorporateActionBasisReconciliation,
    missing_dependencies: tuple[str, ...],
    evidence: CorporateActionReconciliationEvidence,
) -> CorporateActionReconciliationObservation:
    return CorporateActionReconciliationObservation(
        key=key,
        processed_transaction=processed_transaction,
        reconciliation_status=reconciliation.status,
        source_leg_count=reconciliation.source_leg_count,
        target_leg_count=reconciliation.target_leg_count,
        cash_consideration_count=reconciliation.cash_consideration_count,
        source_basis_out_local=reconciliation.source_basis_out_local,
        target_basis_in_local=reconciliation.target_basis_in_local,
        cash_basis_local=reconciliation.cash_basis_local,
        missing_cash_basis_count=reconciliation.missing_cash_basis_count,
        net_basis_delta_local=reconciliation.net_basis_delta_local,
        basis_tolerance=reconciliation.basis_tolerance,
        missing_dependency_reference_ids=missing_dependencies,
        finding_severities=tuple(finding.severity for finding in evidence.findings),
    )


def build_corporate_action_reconciliation_evidence(
    *,
    processed_transaction: BookedTransaction,
    linked_transaction_group_id: str,
    parent_event_reference: str,
    reconciliation: CorporateActionBasisReconciliation,
    missing_dependency_reference_ids: Sequence[str],
    correlation_id: str | None,
    completed_at: datetime,
) -> CorporateActionReconciliationEvidence:
    """Build stable run and finding evidence without persistence or telemetry concerns."""

    missing_dependencies = tuple(missing_dependency_reference_ids)
    evidence_signature = _stable_digest(
        {
            "portfolio_id": processed_transaction.portfolio_id,
            "linked_transaction_group_id": linked_transaction_group_id,
            "parent_event_reference": parent_event_reference,
            "status": reconciliation.status,
            "source_basis_out_local": str(reconciliation.source_basis_out_local),
            "target_basis_in_local": str(reconciliation.target_basis_in_local),
            "cash_basis_local": str(reconciliation.cash_basis_local),
            "missing_cash_basis_count": reconciliation.missing_cash_basis_count,
            "net_basis_delta_local": str(reconciliation.net_basis_delta_local),
            "basis_tolerance": str(reconciliation.basis_tolerance),
            "missing_dependency_reference_ids": list(missing_dependencies),
        }
    )
    run_id = f"recon-ca-bundle-a-{evidence_signature}"
    run = CorporateActionReconciliationRunEvidence(
        run_id=run_id,
        reconciliation_type=CORPORATE_ACTION_RECONCILIATION_TYPE,
        portfolio_id=processed_transaction.portfolio_id,
        business_date=processed_transaction.transaction_date.date(),
        epoch=processed_transaction.epoch,
        status="COMPLETED",
        requested_by=CORPORATE_ACTION_RECONCILIATION_REQUEST_OWNER,
        dedupe_key=f"auto:{CORPORATE_ACTION_RECONCILIATION_TYPE}:{evidence_signature}",
        correlation_id=correlation_id,
        tolerance=reconciliation.basis_tolerance,
        summary=_summary(reconciliation, missing_dependencies),
        failure_reason=None,
        completed_at=completed_at,
    )
    return CorporateActionReconciliationEvidence(
        run=run,
        findings=_findings(
            run_id=run_id,
            evidence_signature=evidence_signature,
            processed_transaction=processed_transaction,
            linked_transaction_group_id=linked_transaction_group_id,
            parent_event_reference=parent_event_reference,
            reconciliation=reconciliation,
            missing_dependencies=missing_dependencies,
        ),
    )


def _stable_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _summary(
    reconciliation: CorporateActionBasisReconciliation,
    missing_dependencies: tuple[str, ...],
) -> dict[str, object]:
    finding_count = int(
        reconciliation.status is not CorporateActionBasisReconciliationStatus.BALANCED
    ) + int(bool(missing_dependencies))
    return {
        "examined_count": (
            reconciliation.source_leg_count
            + reconciliation.target_leg_count
            + reconciliation.cash_consideration_count
        ),
        "finding_count": finding_count,
        "error_count": finding_count,
        "warning_count": 0,
        "passed": finding_count == 0,
        "reconciliation_status": reconciliation.status,
        "source_leg_count": reconciliation.source_leg_count,
        "target_leg_count": reconciliation.target_leg_count,
        "cash_consideration_count": reconciliation.cash_consideration_count,
        "source_basis_out_local": str(reconciliation.source_basis_out_local),
        "target_basis_in_local": str(reconciliation.target_basis_in_local),
        "cash_basis_local": str(reconciliation.cash_basis_local),
        "net_basis_delta_local": str(reconciliation.net_basis_delta_local),
        "missing_cash_basis_count": reconciliation.missing_cash_basis_count,
        "missing_dependency_count": len(missing_dependencies),
    }


def _findings(
    *,
    run_id: str,
    evidence_signature: str,
    processed_transaction: BookedTransaction,
    linked_transaction_group_id: str,
    parent_event_reference: str,
    reconciliation: CorporateActionBasisReconciliation,
    missing_dependencies: tuple[str, ...],
) -> tuple[CorporateActionReconciliationFindingEvidence, ...]:
    findings: list[CorporateActionReconciliationFindingEvidence] = []
    status = reconciliation.status
    if status is CorporateActionBasisReconciliationStatus.BASIS_MISMATCH:
        findings.append(
            _finding(
                run_id=run_id,
                evidence_signature=evidence_signature,
                finding_type=CorporateActionReconciliationFindingType.BASIS_MISMATCH,
                reason_code=CorporateActionReconciliationReasonCode.BASIS_MISMATCH,
                processed_transaction=processed_transaction,
                linked_transaction_group_id=linked_transaction_group_id,
                parent_event_reference=parent_event_reference,
                reconciliation=reconciliation,
                expected_value={
                    "net_basis_delta_local_abs": f"<= {reconciliation.basis_tolerance}"
                },
                observed_value={
                    "source_basis_out_local": str(reconciliation.source_basis_out_local),
                    "target_basis_in_local": str(reconciliation.target_basis_in_local),
                    "cash_basis_local": str(reconciliation.cash_basis_local),
                    "net_basis_delta_local": str(reconciliation.net_basis_delta_local),
                },
            )
        )
    elif status is CorporateActionBasisReconciliationStatus.INSUFFICIENT_LEGS:
        findings.append(
            _finding(
                run_id=run_id,
                evidence_signature=evidence_signature,
                finding_type=CorporateActionReconciliationFindingType.INSUFFICIENT_LEGS,
                reason_code=CorporateActionReconciliationReasonCode.INSUFFICIENT_LEGS,
                processed_transaction=processed_transaction,
                linked_transaction_group_id=linked_transaction_group_id,
                parent_event_reference=parent_event_reference,
                reconciliation=reconciliation,
                expected_value={"source_leg_count": ">=1", "target_leg_count": ">=1"},
                observed_value={
                    "source_leg_count": reconciliation.source_leg_count,
                    "target_leg_count": reconciliation.target_leg_count,
                },
            )
        )
    elif status is CorporateActionBasisReconciliationStatus.INSUFFICIENT_CASH_BASIS:
        findings.append(
            _finding(
                run_id=run_id,
                evidence_signature=evidence_signature,
                finding_type=CorporateActionReconciliationFindingType.INSUFFICIENT_CASH_BASIS,
                reason_code=CorporateActionReconciliationReasonCode.INSUFFICIENT_CASH_BASIS,
                processed_transaction=processed_transaction,
                linked_transaction_group_id=linked_transaction_group_id,
                parent_event_reference=parent_event_reference,
                reconciliation=reconciliation,
                expected_value={"missing_cash_basis_count": 0},
                observed_value={
                    "cash_consideration_count": reconciliation.cash_consideration_count,
                    "missing_cash_basis_count": reconciliation.missing_cash_basis_count,
                    "cash_basis_local": str(reconciliation.cash_basis_local),
                },
            )
        )
    if missing_dependencies:
        findings.append(
            _finding(
                run_id=run_id,
                evidence_signature=evidence_signature,
                finding_type=CorporateActionReconciliationFindingType.MISSING_DEPENDENCY,
                reason_code=CorporateActionReconciliationReasonCode.MISSING_DEPENDENCY,
                processed_transaction=processed_transaction,
                linked_transaction_group_id=linked_transaction_group_id,
                parent_event_reference=parent_event_reference,
                reconciliation=reconciliation,
                expected_value={"dependency_reference_ids": "present in linked Bundle A group"},
                observed_value={"missing_dependency_reference_ids": list(missing_dependencies)},
                extra_detail={"missing_dependency_reference_ids": list(missing_dependencies)},
            )
        )
    return tuple(findings)


def _finding(
    *,
    run_id: str,
    evidence_signature: str,
    finding_type: CorporateActionReconciliationFindingType,
    reason_code: CorporateActionReconciliationReasonCode,
    processed_transaction: BookedTransaction,
    linked_transaction_group_id: str,
    parent_event_reference: str,
    reconciliation: CorporateActionBasisReconciliation,
    expected_value: dict[str, object],
    observed_value: dict[str, object],
    extra_detail: dict[str, object] | None = None,
) -> CorporateActionReconciliationFindingEvidence:
    detail = {
        "reason_code": reason_code,
        "linked_transaction_group_id": linked_transaction_group_id,
        "parent_event_reference": parent_event_reference,
        "reconciliation_status": reconciliation.status,
        "source_leg_count": reconciliation.source_leg_count,
        "target_leg_count": reconciliation.target_leg_count,
        "cash_consideration_count": reconciliation.cash_consideration_count,
        "cash_basis_local": str(reconciliation.cash_basis_local),
        "missing_cash_basis_count": reconciliation.missing_cash_basis_count,
        "basis_tolerance": str(reconciliation.basis_tolerance),
        **(extra_detail or {}),
    }
    return CorporateActionReconciliationFindingEvidence(
        finding_id=f"finding-{finding_type}-{evidence_signature}",
        run_id=run_id,
        reconciliation_type=CORPORATE_ACTION_RECONCILIATION_TYPE,
        finding_type=finding_type,
        severity="ERROR",
        portfolio_id=processed_transaction.portfolio_id,
        security_id=processed_transaction.security_id,
        transaction_id=processed_transaction.transaction_id,
        business_date=processed_transaction.transaction_date.date(),
        epoch=processed_transaction.epoch,
        expected_value=expected_value,
        observed_value=observed_value,
        detail=detail,
    )
