"""Calculate the settlement cash leg generated for a booked product transaction."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, localcontext

from portfolio_common.domain.calculation_lineage import build_calculation_lineage
from portfolio_common.domain.transaction.fee_components import TRANSACTION_FEE_COMPONENT_FIELDS
from portfolio_common.domain.transaction.numeric_policy import (
    TRANSACTION_COST_LEDGER_OUTPUT_V1,
    TRANSACTION_PERSISTENCE_PRECISION_V1,
)
from portfolio_common.domain.transaction.type_registry import (
    production_transaction_types_for_generated_cash_legs,
    production_transaction_types_for_lifecycle_families,
)
from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..booked import BookedTransaction
from .cash_entry import CashEntryMode, resolve_cash_entry_mode
from .cash_movement import calculate_settlement_cash_movement

ADJUSTMENT_TRANSACTION_TYPE = "ADJUSTMENT"


@dataclass(frozen=True, slots=True)
class GeneratedCashLegError(ValueError):
    """Describe why a product transaction cannot produce a settlement cash leg."""

    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


def should_generate_settlement_cash_leg(transaction: BookedTransaction) -> bool:
    """Return whether Core must generate a settlement cash leg for the transaction."""

    if transaction.cash_entry_mode is None:
        return False
    mode = resolve_cash_entry_mode(transaction.cash_entry_mode)
    transaction_type = normalize_transaction_control_code(transaction.transaction_type)
    should_generate = (
        mode is CashEntryMode.AUTO_GENERATE
        and transaction_type in GENERATED_CASH_LEG_TRANSACTION_TYPES
        and bool((transaction.settlement_cash_account_id or "").strip())
    )
    if not should_generate:
        return False
    if transaction_type in REDEMPTION_SETTLEMENT_TRANSACTION_TYPES:
        return bool(calculate_settlement_cash_movement(transaction).signed_amount != 0)
    return True


def build_generated_settlement_cash_leg(
    transaction: BookedTransaction,
) -> BookedTransaction:
    """Build the equal-and-linked cash movement for a supported product transaction."""

    _require_generated_cash_leg(transaction)
    persisted_fx_rate = _generated_cash_persisted_rate(transaction.transaction_fx_rate)
    cash_instrument_id = _resolve_cash_instrument_id(transaction)
    settlement_cash = calculate_settlement_cash_movement(transaction)
    transaction_type = normalize_transaction_control_code(transaction.transaction_type)
    economic_event_id, linked_group_id = _resolve_generated_linkage(
        transaction,
        transaction_type,
    )
    settlement_at = transaction.settlement_date or transaction.transaction_date
    net_cost_local = TRANSACTION_COST_LEDGER_OUTPUT_V1.normalize(
        settlement_cash.signed_amount,
        field_name="generated_cash_net_cost_local",
    )
    net_cost = (
        TRANSACTION_COST_LEDGER_OUTPUT_V1.multiply(
            net_cost_local,
            transaction.transaction_fx_rate,
            field_name="generated_cash_net_cost",
        )
        if transaction.transaction_fx_rate is not None
        else None
    )
    cash_leg = BookedTransaction(
        transaction_id=f"{transaction.transaction_id}-CASHLEG",
        portfolio_id=transaction.portfolio_id,
        tenant_id=transaction.tenant_id,
        instrument_id=cash_instrument_id,
        security_id=cash_instrument_id,
        transaction_date=settlement_at,
        settlement_date=settlement_at,
        transaction_type=ADJUSTMENT_TRANSACTION_TYPE,
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=settlement_cash.amount,
        trade_currency=transaction.trade_currency,
        currency=transaction.currency,
        transaction_fx_rate=persisted_fx_rate,
        transaction_fx_rate_origin=transaction.transaction_fx_rate_origin,
        trade_fee=Decimal(0),
        gross_cost=net_cost,
        net_cost=net_cost,
        net_cost_local=net_cost_local,
        economic_event_id=economic_event_id,
        linked_transaction_group_id=linked_group_id,
        calculation_policy_id=transaction.calculation_policy_id,
        calculation_policy_version=transaction.calculation_policy_version,
        source_system=transaction.source_system,
        cash_entry_mode=CashEntryMode.AUTO_GENERATE.value,
        settlement_cash_account_id=transaction.settlement_cash_account_id,
        settlement_cash_instrument_id=transaction.settlement_cash_instrument_id,
        movement_direction=settlement_cash.movement_direction,
        originating_transaction_id=transaction.transaction_id,
        originating_transaction_type=transaction_type,
        adjustment_reason=settlement_cash.adjustment_reason,
        link_type=f"{transaction_type}_TO_CASH",
        reconciliation_key=transaction.reconciliation_key,
    )
    lineage = build_calculation_lineage(
        algorithm_id="generated-settlement-cash",
        algorithm_version=2,
        intermediate_precision=TRANSACTION_COST_LEDGER_OUTPUT_V1.working_precision,
        input_payload=_generated_cash_lineage_input(
            transaction=transaction,
            transaction_type=transaction_type,
            settlement_at=settlement_at.isoformat(),
            signed_settlement_amount=settlement_cash.signed_amount,
        ),
        output_payload=_generated_cash_lineage_output(cash_leg),
        numeric_output_policy=TRANSACTION_COST_LEDGER_OUTPUT_V1.lineage_identity(),
    )
    return replace(cash_leg, calculation_lineage=lineage)


def _generated_cash_persisted_rate(rate: Decimal | None) -> Decimal | None:
    """Represent an exact admitted rate as the ledger will, before receipt creation."""

    if rate is None:
        return None
    policy = TRANSACTION_PERSISTENCE_PRECISION_V1
    policy.require_exact(rate, field_name="transaction_fx_rate")
    if policy.scale is None or policy.precision is None:
        raise RuntimeError("Generated cash requires a bounded transaction persistence policy")
    with localcontext() as context:
        context.prec = max(policy.precision, TRANSACTION_COST_LEDGER_OUTPUT_V1.working_precision)
        quantum = Decimal(1).scaleb(-policy.scale)
        return rate.quantize(quantum)


def _generated_cash_lineage_input(
    *,
    transaction: BookedTransaction,
    transaction_type: str,
    settlement_at: str,
    signed_settlement_amount: Decimal,
) -> dict[str, object]:
    """Bind every source and resolved authority that can change generated cash economics."""

    return {
        "source_transaction_id": transaction.transaction_id,
        "source_transaction_type": transaction_type,
        "source_transaction_date": transaction.transaction_date.isoformat(),
        "source_settlement_date": (
            transaction.settlement_date.isoformat()
            if transaction.settlement_date is not None
            else None
        ),
        "effective_settlement_at": settlement_at,
        "tenant_id": transaction.tenant_id,
        "portfolio_id": transaction.portfolio_id,
        "gross_transaction_amount": transaction.gross_transaction_amount,
        "quantity": transaction.quantity,
        "price": transaction.price,
        "fee_components": {
            field: getattr(transaction, field) for field in TRANSACTION_FEE_COMPONENT_FIELDS
        },
        "withholding_tax_amount": transaction.withholding_tax_amount,
        "other_interest_deductions_amount": transaction.other_interest_deductions_amount,
        "net_interest_amount": transaction.net_interest_amount,
        "interest_direction": transaction.interest_direction,
        "principal_proceeds_local": transaction.principal_proceeds_local,
        "accrued_interest_proceeds_local": transaction.accrued_interest_proceeds_local,
        "embedded_fee_amount_local": transaction.embedded_fee_amount_local,
        "embedded_tax_amount_local": transaction.embedded_tax_amount_local,
        "trade_currency": transaction.trade_currency,
        "currency": transaction.currency,
        "transaction_fx_rate": transaction.transaction_fx_rate,
        "transaction_fx_rate_origin": transaction.transaction_fx_rate_origin,
        "settlement_cash_account_id": transaction.settlement_cash_account_id,
        "resolved_settlement_cash_instrument_id": transaction.settlement_cash_instrument_id,
        "economic_event_id": transaction.economic_event_id,
        "linked_transaction_group_id": transaction.linked_transaction_group_id,
        "source_calculation_lineage": (
            transaction.calculation_lineage.lineage_payload()
            if transaction.calculation_lineage is not None
            else None
        ),
        "signed_settlement_amount": signed_settlement_amount,
    }


def _generated_cash_lineage_output(cash_leg: BookedTransaction) -> dict[str, object]:
    """Return the complete persisted generated-cash projection bound by the receipt."""

    return {
        "transaction_id": cash_leg.transaction_id,
        "portfolio_id": cash_leg.portfolio_id,
        "tenant_id": cash_leg.tenant_id,
        "security_id": cash_leg.security_id,
        "transaction_date": cash_leg.transaction_date.isoformat(),
        "settlement_date": (
            cash_leg.settlement_date.isoformat() if cash_leg.settlement_date is not None else None
        ),
        "gross_transaction_amount": cash_leg.gross_transaction_amount,
        "gross_cost": cash_leg.gross_cost,
        "net_cost": cash_leg.net_cost,
        "net_cost_local": cash_leg.net_cost_local,
        "trade_currency": cash_leg.trade_currency,
        "currency": cash_leg.currency,
        "transaction_fx_rate": cash_leg.transaction_fx_rate,
        "transaction_fx_rate_origin": cash_leg.transaction_fx_rate_origin,
        "settlement_cash_account_id": cash_leg.settlement_cash_account_id,
        "settlement_cash_instrument_id": cash_leg.settlement_cash_instrument_id,
        "movement_direction": cash_leg.movement_direction,
        "adjustment_reason": cash_leg.adjustment_reason,
        "economic_event_id": cash_leg.economic_event_id,
        "linked_transaction_group_id": cash_leg.linked_transaction_group_id,
        "originating_transaction_id": cash_leg.originating_transaction_id,
        "originating_transaction_type": cash_leg.originating_transaction_type,
    }


def _require_generated_cash_leg(transaction: BookedTransaction) -> None:
    if should_generate_settlement_cash_leg(transaction):
        return
    raise GeneratedCashLegError(
        "cash_entry_mode",
        "Event is not configured for AUTO_GENERATE adjustment cash-leg creation.",
    )


def _resolve_cash_instrument_id(transaction: BookedTransaction) -> str:
    cash_instrument_id = (
        transaction.settlement_cash_instrument_id or transaction.settlement_cash_account_id
    )
    if cash_instrument_id:
        return str(cash_instrument_id)
    raise GeneratedCashLegError(
        "settlement_cash_instrument_id",
        "Unable to resolve settlement cash instrument identifier.",
    )


def _resolve_generated_linkage(
    transaction: BookedTransaction,
    transaction_type: str,
) -> tuple[str, str]:
    economic_event_id = transaction.economic_event_id or (
        f"EVT-{transaction_type}-{transaction.portfolio_id}-{transaction.transaction_id}"
    )
    linked_group_id = transaction.linked_transaction_group_id or (
        f"LTG-{transaction_type}-{transaction.portfolio_id}-{transaction.transaction_id}"
    )
    return economic_event_id, linked_group_id


GENERATED_CASH_LEG_TRANSACTION_TYPES = production_transaction_types_for_generated_cash_legs()
REDEMPTION_SETTLEMENT_TRANSACTION_TYPES = production_transaction_types_for_lifecycle_families(
    "redemption"
)
