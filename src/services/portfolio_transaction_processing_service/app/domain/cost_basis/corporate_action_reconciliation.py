"""Reconcile basis conservation across linked corporate-action transactions."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Iterable

from ..transaction import BookedTransaction
from ..transaction.corporate_action import is_bundle_a_corporate_action
from ..transaction.corporate_action.classification import (
    CASH_CONSIDERATION_TRANSACTION_TYPE,
    QUANTITY_TRANSFER_CORPORATE_ACTION_PAIRS,
    SOURCE_BASIS_TRANSFER_TRANSACTION_TYPES,
    SOURCE_QUANTITY_TRANSFER_TRANSACTION_TYPES,
    TARGET_BASIS_TRANSFER_TRANSACTION_TYPES,
    TARGET_QUANTITY_TRANSFER_TRANSACTION_TYPES,
    normalize_corporate_action_transaction_type,
)

DEFAULT_CORPORATE_ACTION_BASIS_TOLERANCE = Decimal("0.01")


class CorporateActionBasisReconciliationStatus(StrEnum):
    """Classify completeness and conservation of one corporate-action group."""

    BALANCED = "balanced"
    BASIS_MISMATCH = "basis_mismatch"
    INSUFFICIENT_CASH_BASIS = "insufficient_cash_basis"
    INSUFFICIENT_LEGS = "insufficient_legs"


class CorporateActionLegLinkageFindingType(StrEnum):
    """Classify defects in a quantity-transfer source/target relationship."""

    MISSING_RECIPROCAL_LEG = "missing_reciprocal_leg"
    TRANSACTION_REFERENCE_MISMATCH = "transaction_reference_mismatch"
    INSTRUMENT_REFERENCE_MISMATCH = "instrument_reference_mismatch"
    UNEXPECTED_RECIPROCAL_TYPE = "unexpected_reciprocal_type"


@dataclass(frozen=True, slots=True)
class CorporateActionLegLinkageFinding:
    """Describe one deterministic reciprocal-leg defect."""

    finding_type: CorporateActionLegLinkageFindingType
    source_transaction_id: str
    target_transaction_id: str
    field: str
    expected_value: str
    observed_value: str | None


@dataclass(frozen=True, slots=True)
class CorporateActionBasisReconciliation:
    """Summarize basis conservation for one linked corporate-action group."""

    status: CorporateActionBasisReconciliationStatus
    source_leg_count: int
    target_leg_count: int
    cash_consideration_count: int
    source_basis_out_local: Decimal
    target_basis_in_local: Decimal
    cash_basis_local: Decimal
    missing_cash_basis_count: int
    net_basis_delta_local: Decimal
    basis_tolerance: Decimal


@dataclass(slots=True)
class _BasisTotals:
    source_leg_count: int = 0
    target_leg_count: int = 0
    cash_consideration_count: int = 0
    source_basis_out_local: Decimal = Decimal(0)
    target_basis_in_local: Decimal = Decimal(0)
    cash_basis_local: Decimal = Decimal(0)
    missing_cash_basis_count: int = 0


def reconcile_corporate_action_basis(
    transactions: Iterable[BookedTransaction],
    *,
    basis_tolerance: Decimal = DEFAULT_CORPORATE_ACTION_BASIS_TOLERANCE,
) -> CorporateActionBasisReconciliation:
    """Evaluate source, target, and cash basis conservation for a linked group."""

    totals = _BasisTotals()
    for transaction in transactions:
        _accumulate(totals, transaction)
    net_basis_delta_local = (
        totals.target_basis_in_local + totals.cash_basis_local - totals.source_basis_out_local
    )
    return CorporateActionBasisReconciliation(
        status=_status(totals, net_basis_delta_local, basis_tolerance),
        source_leg_count=totals.source_leg_count,
        target_leg_count=totals.target_leg_count,
        cash_consideration_count=totals.cash_consideration_count,
        source_basis_out_local=totals.source_basis_out_local,
        target_basis_in_local=totals.target_basis_in_local,
        cash_basis_local=totals.cash_basis_local,
        missing_cash_basis_count=totals.missing_cash_basis_count,
        net_basis_delta_local=net_basis_delta_local,
        basis_tolerance=basis_tolerance,
    )


def missing_corporate_action_dependencies(
    transaction: BookedTransaction,
    available_transaction_ids: set[str],
) -> tuple[str, ...]:
    """Return unresolved dependency references in source order."""

    if not is_bundle_a_corporate_action(transaction.transaction_type):
        return ()
    return tuple(
        reference
        for reference in transaction.dependency_reference_ids or ()
        if reference not in available_transaction_ids
    )


def reconcile_corporate_action_leg_linkage(
    transactions: Iterable[BookedTransaction],
) -> tuple[CorporateActionLegLinkageFinding, ...]:
    """Validate reciprocal quantity-transfer references without relying on arrival order."""

    transaction_by_id = {
        transaction.transaction_id.strip(): transaction
        for transaction in sorted(transactions, key=lambda item: item.transaction_id.strip())
        if transaction.transaction_id.strip()
    }
    findings: list[CorporateActionLegLinkageFinding] = []
    referenced_source_ids: set[str] = set()
    for source in transaction_by_id.values():
        source_type = normalize_corporate_action_transaction_type(source.transaction_type)
        expected_target_type = QUANTITY_TRANSFER_CORPORATE_ACTION_PAIRS.get(source_type)
        if expected_target_type is None:
            continue
        target_id = _normalized_reference(source.target_transaction_reference)
        if target_id is None:
            findings.append(
                _linkage_finding(
                    CorporateActionLegLinkageFindingType.MISSING_RECIPROCAL_LEG,
                    source=source,
                    target_transaction_id="",
                    field="target_transaction_reference",
                    expected_value="persisted target transaction reference",
                    observed_value=None,
                )
            )
            continue
        target = transaction_by_id.get(target_id)
        if target is None:
            findings.append(
                _linkage_finding(
                    CorporateActionLegLinkageFindingType.MISSING_RECIPROCAL_LEG,
                    source=source,
                    target_transaction_id=target_id,
                    field="target_transaction_reference",
                    expected_value=target_id,
                    observed_value=None,
                )
            )
            continue
        referenced_source_ids.add(source.transaction_id.strip())
        target_type = normalize_corporate_action_transaction_type(target.transaction_type)
        if target_type != expected_target_type:
            findings.append(
                _linkage_finding(
                    CorporateActionLegLinkageFindingType.UNEXPECTED_RECIPROCAL_TYPE,
                    source=source,
                    target_transaction_id=target_id,
                    field="transaction_type",
                    expected_value=expected_target_type,
                    observed_value=target_type,
                )
            )
        _compare_linkage_field(
            findings,
            source=source,
            target_transaction_id=target_id,
            field="source_transaction_reference",
            expected_value=source.transaction_id.strip(),
            observed_value=_normalized_reference(target.source_transaction_reference),
            finding_type=CorporateActionLegLinkageFindingType.TRANSACTION_REFERENCE_MISMATCH,
        )
        _compare_linkage_field(
            findings,
            source=source,
            target_transaction_id=target_id,
            field="source_instrument_id",
            expected_value=source.instrument_id.strip(),
            observed_value=_normalized_reference(source.source_instrument_id),
            finding_type=CorporateActionLegLinkageFindingType.INSTRUMENT_REFERENCE_MISMATCH,
        )
        _compare_linkage_field(
            findings,
            source=source,
            target_transaction_id=target_id,
            field="source_instrument_id",
            expected_value=source.instrument_id.strip(),
            observed_value=_normalized_reference(target.source_instrument_id),
            finding_type=CorporateActionLegLinkageFindingType.INSTRUMENT_REFERENCE_MISMATCH,
        )
        _compare_linkage_field(
            findings,
            source=source,
            target_transaction_id=target_id,
            field="target_instrument_id",
            expected_value=target.instrument_id.strip(),
            observed_value=_normalized_reference(source.target_instrument_id),
            finding_type=CorporateActionLegLinkageFindingType.INSTRUMENT_REFERENCE_MISMATCH,
        )
        _compare_linkage_field(
            findings,
            source=source,
            target_transaction_id=target_id,
            field="target_instrument_id",
            expected_value=target.instrument_id.strip(),
            observed_value=_normalized_reference(target.target_instrument_id),
            finding_type=CorporateActionLegLinkageFindingType.INSTRUMENT_REFERENCE_MISMATCH,
        )

    for target in transaction_by_id.values():
        target_type = normalize_corporate_action_transaction_type(target.transaction_type)
        if target_type not in TARGET_QUANTITY_TRANSFER_TRANSACTION_TYPES:
            continue
        source_id = _normalized_reference(target.source_transaction_reference)
        if source_id is None or source_id in referenced_source_ids:
            continue
        source = transaction_by_id.get(source_id)
        findings.append(
            CorporateActionLegLinkageFinding(
                finding_type=(
                    CorporateActionLegLinkageFindingType.MISSING_RECIPROCAL_LEG
                    if source is None
                    else CorporateActionLegLinkageFindingType.TRANSACTION_REFERENCE_MISMATCH
                ),
                source_transaction_id=source_id,
                target_transaction_id=target.transaction_id.strip(),
                field="target_transaction_reference",
                expected_value=target.transaction_id.strip(),
                observed_value=(
                    _normalized_reference(source.target_transaction_reference)
                    if source is not None
                    else None
                ),
            )
        )
    return tuple(findings)


def _compare_linkage_field(
    findings: list[CorporateActionLegLinkageFinding],
    *,
    source: BookedTransaction,
    target_transaction_id: str,
    field: str,
    expected_value: str,
    observed_value: str | None,
    finding_type: CorporateActionLegLinkageFindingType,
) -> None:
    if observed_value == expected_value:
        return
    findings.append(
        _linkage_finding(
            finding_type,
            source=source,
            target_transaction_id=target_transaction_id,
            field=field,
            expected_value=expected_value,
            observed_value=observed_value,
        )
    )


def _linkage_finding(
    finding_type: CorporateActionLegLinkageFindingType,
    *,
    source: BookedTransaction,
    target_transaction_id: str,
    field: str,
    expected_value: str,
    observed_value: str | None,
) -> CorporateActionLegLinkageFinding:
    return CorporateActionLegLinkageFinding(
        finding_type=finding_type,
        source_transaction_id=source.transaction_id.strip(),
        target_transaction_id=target_transaction_id,
        field=field,
        expected_value=expected_value,
        observed_value=observed_value,
    )


def _normalized_reference(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _accumulate(totals: _BasisTotals, transaction: BookedTransaction) -> None:
    transaction_type = normalize_corporate_action_transaction_type(transaction.transaction_type)
    if transaction_type in (
        SOURCE_BASIS_TRANSFER_TRANSACTION_TYPES | SOURCE_QUANTITY_TRANSFER_TRANSACTION_TYPES
    ):
        totals.source_leg_count += 1
        totals.source_basis_out_local += abs(
            transaction.net_cost_local
            if transaction.net_cost_local is not None
            else transaction.gross_transaction_amount
        )
    elif transaction_type in (
        TARGET_BASIS_TRANSFER_TRANSACTION_TYPES | TARGET_QUANTITY_TRANSFER_TRANSACTION_TYPES
    ):
        totals.target_leg_count += 1
        totals.target_basis_in_local += abs(
            transaction.net_cost_local
            if transaction.net_cost_local is not None
            else transaction.gross_transaction_amount
        )
    elif transaction_type == CASH_CONSIDERATION_TRANSACTION_TYPE:
        totals.cash_consideration_count += 1
        if (
            transaction.allocated_cost_basis_local is None
            or transaction.allocated_cost_basis_local < 0
        ):
            totals.missing_cash_basis_count += 1
        else:
            totals.cash_basis_local += transaction.allocated_cost_basis_local


def _status(
    totals: _BasisTotals,
    net_delta: Decimal,
    tolerance: Decimal,
) -> CorporateActionBasisReconciliationStatus:
    if totals.source_leg_count == 0 or totals.target_leg_count == 0:
        return CorporateActionBasisReconciliationStatus.INSUFFICIENT_LEGS
    if totals.missing_cash_basis_count > 0:
        return CorporateActionBasisReconciliationStatus.INSUFFICIENT_CASH_BASIS
    if abs(net_delta) <= tolerance:
        return CorporateActionBasisReconciliationStatus.BALANCED
    return CorporateActionBasisReconciliationStatus.BASIS_MISMATCH
