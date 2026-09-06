"""Build the canonical income component embedded in a redemption settlement."""

from dataclasses import replace
from decimal import Decimal

from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..booked import BookedTransaction
from .economics import REDEMPTION_TRANSACTION_TYPES

REDEMPTION_ACCRUED_INTEREST_COMPONENT = "REDEMPTION_ACCRUED_INTEREST"


def redemption_accrued_interest_transaction_id(redemption_transaction_id: str) -> str:
    """Return the stable identity used across booking, correction, and replay."""

    return f"{redemption_transaction_id.strip()}-ACCRUED-INTEREST"


def build_redemption_accrued_interest_component(
    redemption: BookedTransaction,
    *,
    include_zero: bool = False,
) -> BookedTransaction | None:
    """Return the independently reportable interest embedded in a redemption.

    A positive component normally shares an existing net settlement cash leg. When the
    canonical net settlement is exactly zero, the component remains valid income evidence but
    must not fabricate a cash leg merely to satisfy linkage metadata.
    """

    transaction_type = normalize_transaction_control_code(redemption.transaction_type)
    if transaction_type not in REDEMPTION_TRANSACTION_TYPES:
        return None
    accrued_interest = redemption.accrued_interest_proceeds_local
    if accrued_interest is None:
        accrued_interest = Decimal(0)
    _require_nonnegative_finite_accrued_interest(accrued_interest)
    if accrued_interest == 0 and not include_zero:
        return None
    canonical_net_settlement = _canonical_net_settlement_amount(redemption)
    linked_cash_transaction_id = (redemption.external_cash_transaction_id or "").strip() or None
    if canonical_net_settlement != 0 and linked_cash_transaction_id is None:
        raise ValueError(
            "Embedded redemption interest requires a linked settlement cash transaction."
        )
    transaction_id = redemption_accrued_interest_transaction_id(redemption.transaction_id)
    component_id = f"{transaction_id}:v1"
    lineage = build_calculation_lineage(
        algorithm_id="redemption-accrued-interest-component",
        algorithm_version=1,
        intermediate_precision=64,
        input_payload={
            "source_transaction_id": redemption.transaction_id,
            "source_transaction_type": transaction_type,
            "source_calculation_lineage": (
                redemption.calculation_lineage.lineage_payload()
                if redemption.calculation_lineage is not None
                else None
            ),
            "accrued_interest_proceeds_local": accrued_interest,
            "canonical_net_settlement_amount": canonical_net_settlement,
            "linked_cash_transaction_id": linked_cash_transaction_id,
        },
        output_payload={
            "transaction_id": transaction_id,
            "component_id": component_id,
            "component_type": REDEMPTION_ACCRUED_INTEREST_COMPONENT,
            "amount": accrued_interest,
            "currency": redemption.currency,
        },
    )
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id=redemption.portfolio_id,
        tenant_id=redemption.tenant_id,
        instrument_id=redemption.instrument_id,
        security_id=redemption.security_id,
        transaction_date=redemption.transaction_date,
        settlement_date=redemption.settlement_date,
        transaction_type="INTEREST",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=accrued_interest,
        trade_currency=redemption.trade_currency,
        currency=redemption.currency,
        trade_fee=Decimal(0),
        economic_event_id=redemption.economic_event_id,
        linked_transaction_group_id=redemption.linked_transaction_group_id,
        calculation_policy_id=redemption.calculation_policy_id,
        calculation_policy_version=redemption.calculation_policy_version,
        source_system=redemption.source_system,
        cash_entry_mode=None,
        external_cash_transaction_id=linked_cash_transaction_id,
        movement_direction="INFLOW",
        originating_transaction_id=redemption.transaction_id,
        originating_transaction_type=transaction_type,
        adjustment_reason=REDEMPTION_ACCRUED_INTEREST_COMPONENT,
        link_type="REDEMPTION_TO_ACCRUED_INTEREST",
        interest_direction="INCOME",
        withholding_tax_amount=Decimal(0),
        other_interest_deductions_amount=Decimal(0),
        net_interest_amount=accrued_interest,
        component_type=REDEMPTION_ACCRUED_INTEREST_COMPONENT,
        component_id=component_id,
        linked_component_ids=(linked_cash_transaction_id,) if linked_cash_transaction_id else None,
        parent_transaction_reference=redemption.transaction_id,
        parent_event_reference=redemption.parent_event_reference,
        epoch=redemption.epoch,
        calculation_lineage=lineage,
    )


def _canonical_net_settlement_amount(redemption: BookedTransaction) -> Decimal:
    """Resolve the source-owned net amount without introducing an import cycle."""

    # Redemption is imported by the settlement package during module initialization. Importing
    # the sibling policy lazily keeps that dependency acyclic while retaining one cash authority.
    from ..settlement.cash_movement import calculate_settlement_cash_movement

    return calculate_settlement_cash_movement(redemption).signed_amount


def _require_nonnegative_finite_accrued_interest(accrued_interest: Decimal) -> None:
    """Fail closed before comparisons or lineage hashing receive invalid monetary evidence."""

    if not isinstance(accrued_interest, Decimal) or not accrued_interest.is_finite():
        raise ValueError("accrued_interest_proceeds_local must be a non-negative finite decimal.")
    if accrued_interest < 0:
        raise ValueError("accrued_interest_proceeds_local must be a non-negative finite decimal.")


def is_generated_redemption_accrued_interest(
    transaction: BookedTransaction,
) -> bool:
    """Return whether a transaction is Core's canonical redemption income component."""

    origin_id = (transaction.originating_transaction_id or "").strip()
    expected_transaction_id = redemption_accrued_interest_transaction_id(origin_id)
    return (
        normalize_transaction_control_code(transaction.transaction_type) == "INTEREST"
        and normalize_transaction_control_code(transaction.component_type)
        == REDEMPTION_ACCRUED_INTEREST_COMPONENT
        and bool(origin_id)
        and transaction.transaction_id.strip() == expected_transaction_id
        and transaction.component_id == f"{expected_transaction_id}:v1"
        and normalize_transaction_control_code(transaction.originating_transaction_type)
        in REDEMPTION_TRANSACTION_TYPES
    )


def neutralize_generated_redemption_accrued_interest(
    prior_component: BookedTransaction,
    *,
    corrected_source: BookedTransaction,
) -> BookedTransaction:
    """Return zero-valued evidence that supersedes an obsolete generated income child."""

    if (
        corrected_source.transaction_id != prior_component.originating_transaction_id
        or not is_generated_redemption_accrued_interest(prior_component)
    ):
        raise ValueError("Prior accrued-interest child is not canonical generated evidence.")
    lineage = build_calculation_lineage(
        algorithm_id="redemption-accrued-interest-neutralization",
        algorithm_version=1,
        intermediate_precision=64,
        input_payload={
            "source_transaction_id": corrected_source.transaction_id,
            "corrected_source_transaction_type": normalize_transaction_control_code(
                corrected_source.transaction_type
            ),
            "corrected_source_calculation_lineage": (
                corrected_source.calculation_lineage.lineage_payload()
                if corrected_source.calculation_lineage is not None
                else None
            ),
            "prior_component_calculation_lineage": (
                prior_component.calculation_lineage.lineage_payload()
                if prior_component.calculation_lineage is not None
                else None
            ),
        },
        output_payload={
            "transaction_id": prior_component.transaction_id,
            "component_id": prior_component.component_id,
            "component_type": REDEMPTION_ACCRUED_INTEREST_COMPONENT,
            "amount": Decimal(0),
            "currency": prior_component.currency,
        },
    )
    return replace(
        prior_component,
        gross_transaction_amount=Decimal(0),
        economic_event_id=corrected_source.economic_event_id,
        linked_transaction_group_id=corrected_source.linked_transaction_group_id,
        external_cash_transaction_id=None,
        linked_component_ids=None,
        withholding_tax_amount=Decimal(0),
        other_interest_deductions_amount=Decimal(0),
        net_interest_amount=Decimal(0),
        parent_event_reference=corrected_source.parent_event_reference,
        epoch=corrected_source.epoch,
        calculation_lineage=lineage,
    )
