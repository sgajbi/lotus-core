"""Coordinate and build evidence for corporate-action basis reconciliation."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Sequence

from portfolio_common.domain.tenant import TenantId

from ..domain.cost_basis import (
    DEFAULT_CORPORATE_ACTION_BASIS_TOLERANCE,
    CorporateActionBasisReconciliation,
    CorporateActionBasisReconciliationStatus,
    CorporateActionLegLinkageFinding,
    missing_corporate_action_dependencies,
    reconcile_corporate_action_basis,
    reconcile_corporate_action_leg_linkage,
)
from ..domain.transaction import BookedTransaction
from ..domain.transaction.corporate_action import (
    SOURCE_QUANTITY_TRANSFER_TRANSACTION_TYPES,
    TARGET_QUANTITY_TRANSFER_TRANSACTION_TYPES,
    is_reconcilable_corporate_action,
    normalize_corporate_action_transaction_type,
)
from ..domain.transaction.semantic_identity import build_transaction_semantic_identity
from ..ports.corporate_action_reconciliation import (
    CorporateActionReconciliationEvidence,
    CorporateActionReconciliationFindingEvidence,
    CorporateActionReconciliationKey,
    CorporateActionReconciliationObservation,
    CorporateActionReconciliationObserver,
    CorporateActionReconciliationRepository,
    CorporateActionReconciliationRunEvidence,
)

CORPORATE_ACTION_BUNDLE_A_RECONCILIATION_TYPE = "corporate_action_bundle_a"
# Preserve the established Bundle A application export while quantity-transfer groups use their
# own evidence type.
CORPORATE_ACTION_RECONCILIATION_TYPE = CORPORATE_ACTION_BUNDLE_A_RECONCILIATION_TYPE
CORPORATE_ACTION_QUANTITY_TRANSFER_RECONCILIATION_TYPE = "corporate_action_quantity_transfer"
CORPORATE_ACTION_RECONCILIATION_REQUEST_OWNER = "cost-calculator"
CORPORATE_ACTION_FINDING_OWNER = "CORPORATE_ACTION_OPERATIONS"
CORPORATE_ACTION_RECONCILIATION_POLICY_ID = "CORPORATE_ACTION_BASIS_CONSERVATION"
CORPORATE_ACTION_RECONCILIATION_POLICY_VERSION = "1.0.0"


class CorporateActionReconciliationFindingType(StrEnum):
    """Classify support findings emitted by corporate-action reconciliation."""

    BASIS_MISMATCH = "ca_bundle_a_basis_mismatch"
    INSUFFICIENT_CASH_BASIS = "ca_bundle_a_insufficient_cash_basis"
    INSUFFICIENT_LEGS = "ca_bundle_a_insufficient_legs"
    INVALID_BASIS_ALLOCATION = "ca_bundle_a_invalid_basis_allocation"
    MISSING_DEPENDENCY = "ca_bundle_a_missing_dependency"
    LEG_LINKAGE_MISMATCH = "ca_linked_leg_mismatch"
    UNSUPPORTED_ADJUSTMENT = "ca_bundle_a_unsupported_adjustment"


class CorporateActionReconciliationReasonCode(StrEnum):
    """Expose stable machine-readable reasons for reconciliation findings."""

    BASIS_MISMATCH = "CA_BUNDLE_A_BASIS_MISMATCH"
    INSUFFICIENT_CASH_BASIS = "CA_BUNDLE_A_INSUFFICIENT_CASH_BASIS"
    INSUFFICIENT_LEGS = "CA_BUNDLE_A_INSUFFICIENT_LEGS"
    INVALID_BASIS_ALLOCATION = "CA_BUNDLE_A_INVALID_BASIS_ALLOCATION"
    MISSING_DEPENDENCY = "CA_BUNDLE_A_MISSING_DEPENDENCY"
    LEG_LINKAGE_MISMATCH = "CA_LINKED_LEG_MISMATCH"
    UNSUPPORTED_ADJUSTMENT = "CA_BUNDLE_A_UNSUPPORTED_BASIS_ADJUSTMENT"


_REPAIR_RECOMMENDATIONS = {
    CorporateActionReconciliationFindingType.BASIS_MISMATCH: (
        "REVIEW_CORPORATE_ACTION_BASIS_ALLOCATION"
    ),
    CorporateActionReconciliationFindingType.INSUFFICIENT_CASH_BASIS: (
        "COMPLETE_CASH_CONSIDERATION_BASIS"
    ),
    CorporateActionReconciliationFindingType.INSUFFICIENT_LEGS: (
        "COMPLETE_CORPORATE_ACTION_LEG_LINKAGE"
    ),
    CorporateActionReconciliationFindingType.INVALID_BASIS_ALLOCATION: (
        "REPAIR_FRACTIONAL_BASIS_ALLOCATION"
    ),
    CorporateActionReconciliationFindingType.MISSING_DEPENDENCY: (
        "RESTORE_CORPORATE_ACTION_DEPENDENCY"
    ),
    CorporateActionReconciliationFindingType.LEG_LINKAGE_MISMATCH: (
        "REPAIR_CORPORATE_ACTION_LEG_LINKAGE"
    ),
    CorporateActionReconciliationFindingType.UNSUPPORTED_ADJUSTMENT: (
        "REBOOK_WITH_SUPPORTED_CORPORATE_ACTION_BASIS_LEGS"
    ),
}


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
        tenant_id: str,
        correlation_id: str | None,
    ) -> CorporateActionReconciliationEvidence | None:
        """Persist and observe evidence when the transaction identifies a new complete group."""

        key = _reconciliation_key(processed_transaction, tenant_id=tenant_id)
        if key is None or key in self._reconciled_groups:
            return None

        group_transactions = await self._repository.load_group(key)
        reconciliation = reconcile_corporate_action_basis(
            group_transactions,
            basis_tolerance=self._basis_tolerance,
        )
        available_transaction_ids = {
            transaction.transaction_id for transaction in group_transactions
        }
        missing_dependencies = tuple(
            sorted(
                {
                    reference
                    for transaction in group_transactions
                    for reference in missing_corporate_action_dependencies(
                        transaction,
                        available_transaction_ids,
                    )
                }
            )
        )
        linkage_findings = reconcile_corporate_action_leg_linkage(group_transactions)
        evidence = build_corporate_action_reconciliation_evidence(
            tenant_id=key.tenant_id,
            processed_transaction=processed_transaction,
            input_transactions=group_transactions,
            linked_transaction_group_id=key.linked_transaction_group_id,
            parent_event_reference=key.parent_event_reference,
            reconciliation=reconciliation,
            missing_dependency_reference_ids=missing_dependencies,
            linkage_findings=linkage_findings,
            reconciliation_type=_reconciliation_type(group_transactions),
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
                    linkage_findings=linkage_findings,
                    evidence=evidence,
                )
            )
        self._reconciled_groups.add(key)
        return evidence


def _reconciliation_key(
    transaction: BookedTransaction,
    *,
    tenant_id: str,
) -> CorporateActionReconciliationKey | None:
    if not is_reconcilable_corporate_action(transaction.transaction_type):
        return None
    linked_group = (transaction.linked_transaction_group_id or "").strip()
    parent_reference = (transaction.parent_event_reference or "").strip()
    if not linked_group or not parent_reference:
        return None
    return CorporateActionReconciliationKey(
        tenant_id=tenant_id,
        portfolio_id=transaction.portfolio_id,
        linked_transaction_group_id=linked_group,
        parent_event_reference=parent_reference,
    )


def _reconciliation_type(transactions: Sequence[BookedTransaction]) -> str:
    transaction_types = {
        normalize_corporate_action_transaction_type(transaction.transaction_type)
        for transaction in transactions
    }
    return (
        CORPORATE_ACTION_QUANTITY_TRANSFER_RECONCILIATION_TYPE
        if transaction_types
        & (SOURCE_QUANTITY_TRANSFER_TRANSACTION_TYPES | TARGET_QUANTITY_TRANSFER_TRANSACTION_TYPES)
        else CORPORATE_ACTION_BUNDLE_A_RECONCILIATION_TYPE
    )


def _observation(
    *,
    key: CorporateActionReconciliationKey,
    processed_transaction: BookedTransaction,
    reconciliation: CorporateActionBasisReconciliation,
    missing_dependencies: tuple[str, ...],
    linkage_findings: tuple[CorporateActionLegLinkageFinding, ...],
    evidence: CorporateActionReconciliationEvidence,
) -> CorporateActionReconciliationObservation:
    return CorporateActionReconciliationObservation(
        key=key,
        processed_transaction=processed_transaction,
        reconciliation_status=reconciliation.status,
        source_leg_count=reconciliation.source_leg_count,
        target_leg_count=reconciliation.target_leg_count,
        cash_consideration_count=reconciliation.cash_consideration_count,
        fractional_cash_leg_count=reconciliation.fractional_cash_leg_count,
        source_basis_out_local=reconciliation.source_basis_out_local,
        target_basis_in_local=reconciliation.target_basis_in_local,
        target_basis_retained_local=reconciliation.target_basis_retained_local,
        cash_basis_local=reconciliation.cash_basis_local,
        cash_consideration_basis_local=reconciliation.cash_consideration_basis_local,
        fractional_basis_local=reconciliation.fractional_basis_local,
        missing_cash_basis_count=reconciliation.missing_cash_basis_count,
        excluded_cash_settlement_adjustment_count=(
            reconciliation.excluded_cash_settlement_adjustment_count
        ),
        unsupported_adjustment_count=reconciliation.unsupported_adjustment_count,
        net_basis_delta_local=reconciliation.net_basis_delta_local,
        basis_tolerance=reconciliation.basis_tolerance,
        missing_dependency_reference_ids=missing_dependencies,
        linkage_finding_count=len(linkage_findings),
        finding_severities=tuple(finding.severity for finding in evidence.findings),
    )


def build_corporate_action_reconciliation_evidence(
    *,
    tenant_id: str,
    processed_transaction: BookedTransaction,
    input_transactions: Sequence[BookedTransaction],
    linked_transaction_group_id: str,
    parent_event_reference: str,
    reconciliation: CorporateActionBasisReconciliation,
    missing_dependency_reference_ids: Sequence[str],
    linkage_findings: Sequence[CorporateActionLegLinkageFinding] = (),
    correlation_id: str | None,
    completed_at: datetime,
    reconciliation_type: str = CORPORATE_ACTION_BUNDLE_A_RECONCILIATION_TYPE,
) -> CorporateActionReconciliationEvidence:
    """Build stable run and finding evidence without persistence or telemetry concerns."""

    tenant_id = TenantId(tenant_id).value
    missing_dependencies = tuple(sorted(set(missing_dependency_reference_ids)))
    input_lineage = _canonical_input_lineage(input_transactions)
    evidence_transaction = _canonical_evidence_transaction(input_transactions)
    canonical_linkage_findings = tuple(
        sorted(
            linkage_findings,
            key=lambda finding: (
                finding.source_transaction_id,
                finding.target_transaction_id,
                finding.finding_type,
                finding.field,
                finding.expected_value,
                finding.observed_value or "",
            ),
        )
    )
    evidence_signature = _stable_digest(
        {
            "tenant_id": tenant_id,
            "portfolio_id": evidence_transaction.portfolio_id,
            "linked_transaction_group_id": linked_transaction_group_id,
            "parent_event_reference": parent_event_reference,
            "status": reconciliation.status,
            "source_basis_out_local": str(reconciliation.source_basis_out_local),
            "target_basis_in_local": str(reconciliation.target_basis_in_local),
            "target_basis_retained_local": str(reconciliation.target_basis_retained_local),
            "cash_basis_local": str(reconciliation.cash_basis_local),
            "missing_cash_basis_count": reconciliation.missing_cash_basis_count,
            "net_basis_delta_local": str(reconciliation.net_basis_delta_local),
            "basis_tolerance": str(reconciliation.basis_tolerance),
            "reconciliation_policy_id": CORPORATE_ACTION_RECONCILIATION_POLICY_ID,
            "reconciliation_policy_version": CORPORATE_ACTION_RECONCILIATION_POLICY_VERSION,
            "input_lineage": input_lineage,
            "missing_dependency_reference_ids": list(missing_dependencies),
            "linkage_findings": [asdict(finding) for finding in canonical_linkage_findings],
        }
    )
    run_id = f"recon-{reconciliation_type}-{evidence_signature}"
    findings = _findings(
        run_id=run_id,
        evidence_signature=evidence_signature,
        processed_transaction=evidence_transaction,
        linked_transaction_group_id=linked_transaction_group_id,
        parent_event_reference=parent_event_reference,
        reconciliation=reconciliation,
        missing_dependencies=missing_dependencies,
        linkage_findings=canonical_linkage_findings,
        reconciliation_type=reconciliation_type,
    )
    run = CorporateActionReconciliationRunEvidence(
        run_id=run_id,
        reconciliation_type=reconciliation_type,
        portfolio_id=evidence_transaction.portfolio_id,
        business_date=evidence_transaction.transaction_date.date(),
        epoch=evidence_transaction.epoch,
        status="COMPLETED",
        requested_by=CORPORATE_ACTION_RECONCILIATION_REQUEST_OWNER,
        dedupe_key=f"auto:{reconciliation_type}:{evidence_signature}",
        correlation_id=correlation_id,
        tolerance=reconciliation.basis_tolerance,
        summary={
            **_summary(
                reconciliation,
                missing_dependencies,
                canonical_linkage_findings,
                findings,
            ),
            "linked_transaction_group_id": linked_transaction_group_id,
            "parent_event_reference": parent_event_reference,
            "reconciliation_policy_id": CORPORATE_ACTION_RECONCILIATION_POLICY_ID,
            "reconciliation_policy_version": CORPORATE_ACTION_RECONCILIATION_POLICY_VERSION,
            "input_lineage": input_lineage,
        },
        failure_reason=None,
        completed_at=completed_at,
    )
    return CorporateActionReconciliationEvidence(
        tenant_id=tenant_id,
        run=run,
        findings=findings,
    )


def _stable_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _canonical_input_lineage(
    transactions: Sequence[BookedTransaction],
) -> list[dict[str, object]]:
    lineage: list[dict[str, object]] = []
    for transaction in transactions:
        semantic_identity = build_transaction_semantic_identity(transaction)
        lineage.append(
            {
                "transaction_id": transaction.transaction_id.strip(),
                "semantic_key": semantic_identity.semantic_key,
                "payload_fingerprint": semantic_identity.payload_fingerprint,
                "transaction_type": transaction.transaction_type.strip().upper(),
                "instrument_id": transaction.instrument_id.strip(),
                "security_id": transaction.security_id.strip(),
                "source_transaction_reference": _normalized_text(
                    transaction.source_transaction_reference
                ),
                "target_transaction_reference": _normalized_text(
                    transaction.target_transaction_reference
                ),
                "source_instrument_id": _normalized_text(transaction.source_instrument_id),
                "target_instrument_id": _normalized_text(transaction.target_instrument_id),
                "quantity": _canonical_decimal(transaction.quantity),
                "price": _canonical_decimal(transaction.price),
                "gross_transaction_amount": _canonical_decimal(
                    transaction.gross_transaction_amount
                ),
                "net_cost_local": _canonical_decimal(transaction.net_cost_local),
                "allocated_cost_basis_local": _canonical_decimal(
                    transaction.allocated_cost_basis_local
                ),
                "allocated_cost_basis_base": _canonical_decimal(
                    transaction.allocated_cost_basis_base
                ),
                "calculation_policy_id": _normalized_text(transaction.calculation_policy_id),
                "calculation_policy_version": _normalized_text(
                    transaction.calculation_policy_version
                ),
                "epoch": transaction.epoch,
            }
        )
    return sorted(
        lineage,
        key=lambda item: (
            str(item["transaction_id"]),
            str(item["semantic_key"]),
            str(item["payload_fingerprint"]),
        ),
    )


def _canonical_evidence_transaction(
    transactions: Sequence[BookedTransaction],
) -> BookedTransaction:
    if not transactions:
        raise ValueError("Corporate-action reconciliation requires input transactions")
    return min(
        transactions,
        key=lambda transaction: (
            transaction.transaction_id.strip(),
            build_transaction_semantic_identity(transaction).payload_fingerprint,
        ),
    )


def _canonical_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _normalized_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _summary(
    reconciliation: CorporateActionBasisReconciliation,
    missing_dependencies: tuple[str, ...],
    linkage_findings: Sequence[CorporateActionLegLinkageFinding],
    findings: Sequence[CorporateActionReconciliationFindingEvidence],
) -> dict[str, object]:
    finding_count = len(findings)
    return {
        "examined_count": (
            reconciliation.source_leg_count
            + reconciliation.target_leg_count
            + reconciliation.cash_consideration_count
            + reconciliation.fractional_cash_leg_count
        ),
        "finding_count": finding_count,
        "error_count": finding_count,
        "warning_count": 0,
        "passed": finding_count == 0,
        "reconciliation_status": reconciliation.status,
        "source_leg_count": reconciliation.source_leg_count,
        "target_leg_count": reconciliation.target_leg_count,
        "cash_consideration_count": reconciliation.cash_consideration_count,
        "fractional_cash_leg_count": reconciliation.fractional_cash_leg_count,
        "source_basis_out_local": str(reconciliation.source_basis_out_local),
        "target_basis_in_local": str(reconciliation.target_basis_in_local),
        "target_basis_retained_local": str(reconciliation.target_basis_retained_local),
        "cash_basis_local": str(reconciliation.cash_basis_local),
        "cash_consideration_basis_local": str(reconciliation.cash_consideration_basis_local),
        "fractional_basis_local": str(reconciliation.fractional_basis_local),
        "net_basis_delta_local": str(reconciliation.net_basis_delta_local),
        "missing_cash_basis_count": reconciliation.missing_cash_basis_count,
        "excluded_cash_settlement_adjustment_count": (
            reconciliation.excluded_cash_settlement_adjustment_count
        ),
        "unsupported_adjustment_count": reconciliation.unsupported_adjustment_count,
        "governed_adjustment_basis_local": "0",
        "missing_dependency_count": len(missing_dependencies),
        "linkage_finding_count": len(linkage_findings),
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
    linkage_findings: tuple[CorporateActionLegLinkageFinding, ...],
    reconciliation_type: str,
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
                    "target_basis_retained_local": str(reconciliation.target_basis_retained_local),
                    "cash_basis_local": str(reconciliation.cash_basis_local),
                    "net_basis_delta_local": str(reconciliation.net_basis_delta_local),
                },
                reconciliation_type=reconciliation_type,
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
                reconciliation_type=reconciliation_type,
            )
        )
    elif status is CorporateActionBasisReconciliationStatus.INVALID_BASIS_ALLOCATION:
        findings.append(
            _finding(
                run_id=run_id,
                evidence_signature=evidence_signature,
                finding_type=CorporateActionReconciliationFindingType.INVALID_BASIS_ALLOCATION,
                reason_code=CorporateActionReconciliationReasonCode.INVALID_BASIS_ALLOCATION,
                processed_transaction=processed_transaction,
                linked_transaction_group_id=linked_transaction_group_id,
                parent_event_reference=parent_event_reference,
                reconciliation=reconciliation,
                expected_value={"target_basis_retained_local": ">= 0"},
                observed_value={
                    "target_basis_in_local": str(reconciliation.target_basis_in_local),
                    "fractional_basis_local": str(reconciliation.fractional_basis_local),
                    "target_basis_retained_local": str(reconciliation.target_basis_retained_local),
                },
                reconciliation_type=reconciliation_type,
            )
        )
    if reconciliation.missing_cash_basis_count > 0:
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
                reconciliation_type=reconciliation_type,
            )
        )
    if reconciliation.unsupported_adjustment_count > 0:
        findings.append(
            _finding(
                run_id=run_id,
                evidence_signature=evidence_signature,
                finding_type=CorporateActionReconciliationFindingType.UNSUPPORTED_ADJUSTMENT,
                reason_code=CorporateActionReconciliationReasonCode.UNSUPPORTED_ADJUSTMENT,
                processed_transaction=processed_transaction,
                linked_transaction_group_id=linked_transaction_group_id,
                parent_event_reference=parent_event_reference,
                reconciliation=reconciliation,
                expected_value={"unsupported_adjustment_count": 0},
                observed_value={
                    "unsupported_adjustment_count": reconciliation.unsupported_adjustment_count
                },
                reconciliation_type=reconciliation_type,
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
                expected_value={"dependency_reference_ids": "present in linked action group"},
                observed_value={"missing_dependency_reference_ids": list(missing_dependencies)},
                extra_detail={"missing_dependency_reference_ids": list(missing_dependencies)},
                reconciliation_type=reconciliation_type,
            )
        )
    for ordinal, linkage_finding in enumerate(linkage_findings):
        findings.append(
            _finding(
                run_id=run_id,
                evidence_signature=evidence_signature,
                finding_type=CorporateActionReconciliationFindingType.LEG_LINKAGE_MISMATCH,
                reason_code=CorporateActionReconciliationReasonCode.LEG_LINKAGE_MISMATCH,
                processed_transaction=processed_transaction,
                linked_transaction_group_id=linked_transaction_group_id,
                parent_event_reference=parent_event_reference,
                reconciliation=reconciliation,
                expected_value={
                    "field": linkage_finding.field,
                    "value": linkage_finding.expected_value,
                },
                observed_value={
                    "field": linkage_finding.field,
                    "value": linkage_finding.observed_value,
                },
                extra_detail={
                    "linkage_finding_type": linkage_finding.finding_type,
                    "source_transaction_id": linkage_finding.source_transaction_id,
                    "target_transaction_id": linkage_finding.target_transaction_id,
                },
                finding_discriminator=f"linkage-{ordinal}",
                reconciliation_type=reconciliation_type,
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
    finding_discriminator: str | None = None,
    reconciliation_type: str = CORPORATE_ACTION_BUNDLE_A_RECONCILIATION_TYPE,
) -> CorporateActionReconciliationFindingEvidence:
    detail = {
        "reason_code": reason_code,
        "linked_transaction_group_id": linked_transaction_group_id,
        "parent_event_reference": parent_event_reference,
        "reconciliation_status": reconciliation.status,
        "source_leg_count": reconciliation.source_leg_count,
        "target_leg_count": reconciliation.target_leg_count,
        "target_basis_retained_local": str(reconciliation.target_basis_retained_local),
        "cash_consideration_count": reconciliation.cash_consideration_count,
        "fractional_cash_leg_count": reconciliation.fractional_cash_leg_count,
        "cash_basis_local": str(reconciliation.cash_basis_local),
        "cash_consideration_basis_local": str(reconciliation.cash_consideration_basis_local),
        "fractional_basis_local": str(reconciliation.fractional_basis_local),
        "missing_cash_basis_count": reconciliation.missing_cash_basis_count,
        "excluded_cash_settlement_adjustment_count": (
            reconciliation.excluded_cash_settlement_adjustment_count
        ),
        "unsupported_adjustment_count": reconciliation.unsupported_adjustment_count,
        "basis_tolerance": str(reconciliation.basis_tolerance),
        **(extra_detail or {}),
    }
    return CorporateActionReconciliationFindingEvidence(
        finding_id=(
            f"finding-{finding_type}-{evidence_signature}"
            + (f"-{finding_discriminator}" if finding_discriminator else "")
        ),
        run_id=run_id,
        reconciliation_type=reconciliation_type,
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
        owner=CORPORATE_ACTION_FINDING_OWNER,
        resolution_state="OPEN",
        tolerance=reconciliation.basis_tolerance,
        observed_delta=(
            reconciliation.net_basis_delta_local
            if finding_type is CorporateActionReconciliationFindingType.BASIS_MISMATCH
            else None
        ),
        repair_recommendation=_REPAIR_RECOMMENDATIONS[finding_type],
    )
