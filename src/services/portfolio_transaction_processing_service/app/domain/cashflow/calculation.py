"""Derive canonical transaction cashflows without framework or persistence dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)
from portfolio_common.domain.transaction.fee_components import (
    TRANSACTION_FEE_COMPONENT_FIELDS,
    resolve_transaction_trade_fee,
)
from portfolio_common.domain.transaction.type_registry import TRANSACTION_TYPE_REGISTRY

from ..transaction.booked import BookedTransaction
from ..transaction.fx import (
    FxValidationError,
    validate_fx_embedded_fee,
    validate_fx_embedded_tax,
)
from ..transaction.processing_type import resolve_effective_processing_transaction_type
from ..transaction.redemption import (
    REDEMPTION_TRANSACTION_TYPES,
)
from ..transaction.settlement import (
    ORDINARY_SETTLEMENT_TRANSACTION_TYPES,
    SettlementCashValidationError,
    calculate_interest_settlement_economics,
    calculate_settlement_cash_movement,
)
from .numeric_policy import CASHFLOW_LEDGER_OUTPUT_V1
from .types import (
    CashflowCalculationContext,
    CashflowCalculationType,
    CashflowClassification,
    CashflowTiming,
)

_TRANSFER_LIFECYCLE_FAMILIES = frozenset({"transfer", "corporate_action", "rights"})
_TRANSFER_INFLOW_CASH_EFFECT_TYPES = frozenset({"RIGHTS_REFUND"})
_TRANSFER_SIGNING_FALLBACK_TYPES = frozenset({"CASH_IN_LIEU"})
_SETTLEMENT_DATED_TRANSACTION_TYPES = (
    frozenset(
        {
            "BUY",
            "SELL",
            "DEPOSIT",
            "WITHDRAWAL",
            "FX_CASH_SETTLEMENT_BUY",
            "FX_CASH_SETTLEMENT_SELL",
        }
    )
    | REDEMPTION_TRANSACTION_TYPES
)
_PAYMENT_DATED_TRANSACTION_TYPES = frozenset({"DIVIDEND", "INTEREST"})
_CLASSIFICATION_SIGN_FACTORS = {
    CashflowClassification.FX_BUY.value: 1,
    CashflowClassification.FX_SELL.value: -1,
    CashflowClassification.INVESTMENT_INFLOW.value: 1,
    CashflowClassification.CORPORATE_ACTION_PROCEEDS.value: 1,
    CashflowClassification.INCOME.value: 1,
    CashflowClassification.CASHFLOW_IN.value: 1,
}
_SYNTHETIC_TRANSFER_CLASSIFICATION_SIGN = {
    "POSITION_TRANSFER_IN": 1,
    "POSITION_TRANSFER_OUT": -1,
    "POSITION_CASH_IN_LIEU_OUT": -1,
}


def _transfer_transaction_types_for_position_effect(position_effect: str) -> frozenset[str]:
    return frozenset(
        code
        for code, definition in TRANSACTION_TYPE_REGISTRY.items()
        if definition.production_booking_allowed
        and definition.lifecycle_family in _TRANSFER_LIFECYCLE_FAMILIES
        and definition.position_effect == position_effect
        and code not in _TRANSFER_SIGNING_FALLBACK_TYPES
    )


TRANSFER_INFLOW_TRANSACTION_TYPES = (
    _transfer_transaction_types_for_position_effect("increase") | _TRANSFER_INFLOW_CASH_EFFECT_TYPES
)
TRANSFER_OUTFLOW_TRANSACTION_TYPES = _transfer_transaction_types_for_position_effect("decrease")


@dataclass(frozen=True, slots=True)
class CashflowRule:
    """Govern classification, timing, and aggregation level for one transaction type."""

    classification: str | CashflowClassification
    timing: str | CashflowTiming
    is_position_flow: bool
    is_portfolio_flow: bool


@dataclass(frozen=True, slots=True)
class CalculatedCashflow:
    """Represent the deterministic cashflow derived from a booked transaction."""

    transaction_id: str
    portfolio_id: str
    security_id: str | None
    cashflow_date: date
    amount: Decimal
    currency: str
    classification: str
    timing: str
    calculation_type: str
    is_position_flow: bool
    is_portfolio_flow: bool
    economic_event_id: str | None
    linked_transaction_group_id: str | None
    epoch: int
    calculation_lineage: CalculationLineage | None = None


@dataclass(frozen=True, slots=True)
class _CashflowEconomics:
    amount: Decimal
    currency: str
    calculation_type: str


@dataclass(frozen=True, slots=True)
class _CashflowLevel:
    is_position_flow: bool
    is_portfolio_flow: bool


def calculate_transaction_cashflow(
    transaction: BookedTransaction,
    rule: CashflowRule,
    *,
    epoch: int | None = 0,
    calculation_context: CashflowCalculationContext = (CashflowCalculationContext.CURRENT_BOOKING),
) -> CalculatedCashflow:
    """Apply the governed cashflow rule to one framework-neutral booked transaction.

    Persisted FX rows retain their business transaction type while ``component_type`` identifies
    the concrete cash leg. Resolve that representation here so every caller receives the same
    component-level economics and validation policy.
    """
    transaction_type = resolve_effective_processing_transaction_type(transaction)
    with CASHFLOW_LEDGER_OUTPUT_V1.arithmetic_context():
        economics = _resolve_cashflow_economics(
            transaction,
            rule,
            transaction_type,
            calculation_context,
        )
        resolved_trade_fee = _resolve_cashflow_trade_fee(transaction)
    level = _resolve_cashflow_level(transaction, rule)
    cashflow_date = _resolve_cashflow_date(transaction, rule, transaction_type)
    amount = CASHFLOW_LEDGER_OUTPUT_V1.normalize(
        economics.amount,
        field_name="cashflows.amount",
    )
    classification = _resolve_cashflow_classification(
        transaction_type=transaction_type,
        configured_classification=rule.classification,
        amount=amount,
    )
    timing = _normalize_code(rule.timing)
    normalized_epoch = epoch or 0
    calculation_lineage = build_calculation_lineage(
        algorithm_id="transaction-cashflow",
        algorithm_version=1,
        intermediate_precision=CASHFLOW_LEDGER_OUTPUT_V1.working_precision,
        input_payload=_cashflow_lineage_input(
            transaction=transaction,
            rule=rule,
            transaction_type=transaction_type,
            calculation_context=calculation_context,
            epoch=normalized_epoch,
            resolved_trade_fee=resolved_trade_fee,
        ),
        output_payload={
            "amount": amount,
            "calculation_type": economics.calculation_type,
            "cashflow_date": cashflow_date,
            "classification": classification,
            "currency": economics.currency,
            "economic_event_id": transaction.economic_event_id,
            "epoch": normalized_epoch,
            "is_portfolio_flow": level.is_portfolio_flow,
            "is_position_flow": level.is_position_flow,
            "linked_transaction_group_id": transaction.linked_transaction_group_id,
            "portfolio_id": transaction.portfolio_id,
            "security_id": transaction.security_id,
            "timing": timing,
            "transaction_id": transaction.transaction_id,
        },
        numeric_output_policy=CASHFLOW_LEDGER_OUTPUT_V1.lineage_identity(),
    )
    return CalculatedCashflow(
        transaction_id=transaction.transaction_id,
        portfolio_id=transaction.portfolio_id,
        security_id=transaction.security_id,
        cashflow_date=cashflow_date,
        amount=amount,
        currency=economics.currency,
        classification=classification,
        timing=timing,
        calculation_type=economics.calculation_type,
        is_position_flow=level.is_position_flow,
        is_portfolio_flow=level.is_portfolio_flow,
        economic_event_id=transaction.economic_event_id,
        linked_transaction_group_id=transaction.linked_transaction_group_id,
        epoch=normalized_epoch,
        calculation_lineage=calculation_lineage,
    )


def _cashflow_lineage_input(
    *,
    transaction: BookedTransaction,
    rule: CashflowRule,
    transaction_type: str,
    calculation_context: CashflowCalculationContext,
    epoch: int,
    resolved_trade_fee: Decimal,
) -> dict[str, object]:
    """Return every source and policy value that can change cashflow economics."""

    return {
        "calculation_context": calculation_context,
        "epoch": epoch,
        "rule": {
            "classification": _normalize_classification(rule.classification),
            "is_portfolio_flow": rule.is_portfolio_flow,
            "is_position_flow": rule.is_position_flow,
            "timing": _normalize_code(rule.timing),
        },
        "transaction": {
            "component_type": transaction.component_type,
            "currency": transaction.currency,
            "economic_event_id": transaction.economic_event_id,
            "fee_components": {
                field: getattr(transaction, field) for field in TRANSACTION_FEE_COMPONENT_FIELDS
            },
            "gross_transaction_amount": transaction.gross_transaction_amount,
            "has_synthetic_flow": transaction.has_synthetic_flow,
            "interest_direction": transaction.interest_direction,
            "linked_transaction_group_id": transaction.linked_transaction_group_id,
            "movement_direction": transaction.movement_direction,
            "net_interest_amount": transaction.net_interest_amount,
            "other_interest_deductions_amount": transaction.other_interest_deductions_amount,
            "price": transaction.price,
            "principal_proceeds_local": transaction.principal_proceeds_local,
            "accrued_interest_proceeds_local": transaction.accrued_interest_proceeds_local,
            "embedded_fee_amount_local": transaction.embedded_fee_amount_local,
            "embedded_tax_amount_local": transaction.embedded_tax_amount_local,
            "originating_transaction_id": transaction.originating_transaction_id,
            "originating_transaction_type": transaction.originating_transaction_type,
            "portfolio_id": transaction.portfolio_id,
            "quantity": transaction.quantity,
            "security_id": transaction.security_id,
            "settlement_date": (
                transaction.settlement_date.isoformat()
                if transaction.settlement_date is not None
                else None
            ),
            "synthetic_flow_amount_local": transaction.synthetic_flow_amount_local,
            "synthetic_flow_classification": transaction.synthetic_flow_classification,
            "synthetic_flow_currency": transaction.synthetic_flow_currency,
            "synthetic_flow_effective_date": transaction.synthetic_flow_effective_date,
            "booked_transaction_type": transaction.transaction_type,
            "resolved_trade_fee": resolved_trade_fee,
            "transaction_date": transaction.transaction_date.isoformat(),
            "transaction_id": transaction.transaction_id,
            "effective_processing_transaction_type": transaction_type,
            "withholding_tax_amount": transaction.withholding_tax_amount,
        },
    }


def _normalize_code(value: object, default: str = "") -> str:
    if isinstance(value, Enum):
        value = value.value
    return str(value or default).strip().upper()


def _normalize_classification(value: str | CashflowClassification) -> str:
    if isinstance(value, CashflowClassification):
        return value.value
    return _normalize_code(value)


def _resolve_cashflow_classification(
    *,
    transaction_type: str,
    configured_classification: str | CashflowClassification,
    amount: Decimal,
) -> str:
    """Keep redemption principal classification consistent with its signed economics.

    A redemption's product cashflow is the principal component after settlement deductions.
    When those deductions exceed principal, the component is an investment outflow even though
    accrued interest can keep the authoritative net settlement positive (or exactly zero).
    """

    if transaction_type in REDEMPTION_TRANSACTION_TYPES and amount < 0:
        return CashflowClassification.INVESTMENT_OUTFLOW.value
    return _normalize_classification(configured_classification)


def _resolve_cashflow_date(
    transaction: BookedTransaction,
    rule: CashflowRule,
    transaction_type: str,
) -> date:
    if transaction.synthetic_flow_effective_date is not None:
        return transaction.synthetic_flow_effective_date
    if transaction_type in (_SETTLEMENT_DATED_TRANSACTION_TYPES | _PAYMENT_DATED_TRANSACTION_TYPES):
        return _settlement_date_or_transaction_date(transaction)
    if _normalize_classification(rule.classification) in {"FX_BUY", "FX_SELL"}:
        return _settlement_date_or_transaction_date(transaction)
    return transaction.transaction_date.date()


def _settlement_date_or_transaction_date(transaction: BookedTransaction) -> date:
    if transaction.settlement_date is not None:
        return transaction.settlement_date.date()
    return transaction.transaction_date.date()


def _resolve_cashflow_trade_fee(transaction: BookedTransaction) -> Decimal:
    trade_fee = resolve_transaction_trade_fee(
        transaction.trade_fee,
        {field: getattr(transaction, field) for field in TRANSACTION_FEE_COMPONENT_FIELDS},
    )
    return trade_fee or Decimal(0)


def _base_cashflow_amount(
    transaction: BookedTransaction,
    transaction_type: str,
) -> Decimal:
    trade_fee = _resolve_cashflow_trade_fee(transaction)
    if transaction_type in {"FX_CASH_SETTLEMENT_BUY", "FX_CASH_SETTLEMENT_SELL"}:
        embedded_charge_issues = [
            issue
            for issue in (
                validate_fx_embedded_fee(trade_fee),
                validate_fx_embedded_tax(transaction.withholding_tax_amount or Decimal(0)),
            )
            if issue is not None
        ]
        if embedded_charge_issues:
            raise FxValidationError(embedded_charge_issues)
    if transaction_type in {"BUY", "FEE"}:
        return transaction.gross_transaction_amount + trade_fee
    return transaction.gross_transaction_amount - trade_fee


def _resolve_cashflow_economics(
    transaction: BookedTransaction,
    rule: CashflowRule,
    transaction_type: str,
    calculation_context: CashflowCalculationContext,
) -> _CashflowEconomics:
    if transaction.has_synthetic_flow:
        return _synthetic_transfer_economics(transaction, rule)
    if transaction_type in REDEMPTION_TRANSACTION_TYPES:
        amount = calculate_settlement_cash_movement(transaction).signed_amount - (
            transaction.accrued_interest_proceeds_local or Decimal(0)
        )
    elif transaction_type in ORDINARY_SETTLEMENT_TRANSACTION_TYPES:
        amount = (
            _historical_rebuild_cashflow_amount(transaction, rule, transaction_type)
            if calculation_context is CashflowCalculationContext.HISTORICAL_REBUILD
            else calculate_settlement_cash_movement(transaction).signed_amount
        )
    else:
        amount = _signed_cashflow_amount(
            transaction,
            rule,
            transaction_type,
            _base_cashflow_amount(transaction, transaction_type),
        )
    return _CashflowEconomics(
        amount=amount,
        currency=transaction.currency,
        calculation_type=CashflowCalculationType.NET.value,
    )


def _historical_rebuild_cashflow_amount(
    transaction: BookedTransaction,
    rule: CashflowRule,
    transaction_type: str,
) -> Decimal:
    """Reproduce pre-policy signing for already accepted history during restatement."""
    if transaction_type in REDEMPTION_TRANSACTION_TYPES:
        return calculate_settlement_cash_movement(transaction).signed_amount - (
            transaction.accrued_interest_proceeds_local or Decimal(0)
        )
    if transaction_type == "DIVIDEND" and (transaction.withholding_tax_amount or Decimal(0)) > 0:
        try:
            return calculate_settlement_cash_movement(transaction).signed_amount
        except SettlementCashValidationError:
            # Rows accepted before settlement fencing may contain economics that current
            # booking rejects. Preserve those rows rather than making a suffix rebuild fail.
            pass
    if transaction_type == "INTEREST":
        amount: Decimal = calculate_interest_settlement_economics(
            transaction
        ).settlement_cash_amount
        direction = _normalize_code(transaction.interest_direction, default="INCOME")
        return -abs(amount) if direction == "EXPENSE" else abs(amount)
    return _signed_cashflow_amount(
        transaction,
        rule,
        transaction_type,
        _base_cashflow_amount(transaction, transaction_type),
    )


def _synthetic_transfer_economics(
    transaction: BookedTransaction,
    rule: CashflowRule,
) -> _CashflowEconomics:
    classification = _normalize_code(transaction.synthetic_flow_classification)
    sign = _SYNTHETIC_TRANSFER_CLASSIFICATION_SIGN.get(classification)
    if _normalize_classification(rule.classification) != CashflowClassification.TRANSFER.value:
        raise ValueError("Synthetic position flow requires TRANSFER cashflow classification")
    if not rule.is_position_flow or rule.is_portfolio_flow:
        raise ValueError("Synthetic position flow must be position-level and non-portfolio")
    if sign is None:
        raise ValueError("Synthetic position flow classification is missing or unsupported")
    if transaction.synthetic_flow_amount_local is None:
        raise ValueError("Synthetic position flow amount is required")
    if not transaction.synthetic_flow_currency:
        raise ValueError("Synthetic position flow currency is required")

    amount = transaction.synthetic_flow_amount_local
    if amount.is_zero() or (amount > 0) != (sign > 0):
        raise ValueError("Synthetic position flow amount sign does not match its classification")
    return _CashflowEconomics(
        amount=amount,
        currency=transaction.synthetic_flow_currency,
        calculation_type=CashflowCalculationType.MVT.value,
    )


def _signed_cashflow_amount(
    transaction: BookedTransaction,
    rule: CashflowRule,
    transaction_type: str,
    amount: Decimal,
) -> Decimal:
    if transaction_type == "ADJUSTMENT":
        return _signed_adjustment_amount(transaction, amount)
    if _normalize_classification(rule.classification) == CashflowClassification.TRANSFER.value:
        return _signed_transfer_amount(transaction, transaction_type, amount)
    return _signed_by_classification(rule.classification, amount)


def _signed_by_classification(
    classification: str | CashflowClassification,
    amount: Decimal,
) -> Decimal:
    sign_factor = _CLASSIFICATION_SIGN_FACTORS.get(_normalize_classification(classification), -1)
    return abs(amount) if sign_factor > 0 else -abs(amount)


def _signed_adjustment_amount(transaction: BookedTransaction, amount: Decimal) -> Decimal:
    direction = _normalize_code(transaction.movement_direction, default="INFLOW")
    return abs(amount) if direction == "INFLOW" else -abs(amount)


def _signed_transfer_amount(
    transaction: BookedTransaction,
    transaction_type: str,
    amount: Decimal,
) -> Decimal:
    if transaction_type in TRANSFER_INFLOW_TRANSACTION_TYPES:
        return abs(amount)
    if transaction_type in TRANSFER_OUTFLOW_TRANSACTION_TYPES:
        return -abs(amount)
    return abs(amount) if transaction.quantity > 0 else -abs(amount)


def _resolve_cashflow_level(
    transaction: BookedTransaction,
    rule: CashflowRule,
) -> _CashflowLevel:
    if _is_duplicate_corporate_action_cash_settlement(transaction):
        return _CashflowLevel(is_position_flow=False, is_portfolio_flow=False)
    return _CashflowLevel(
        is_position_flow=rule.is_position_flow,
        is_portfolio_flow=rule.is_portfolio_flow,
    )


def _is_duplicate_corporate_action_cash_settlement(
    transaction: BookedTransaction,
) -> bool:
    return (
        _normalize_code(transaction.transaction_type) == "ADJUSTMENT"
        and bool((transaction.originating_transaction_id or "").strip())
        and _normalize_code(transaction.originating_transaction_type)
        in {"CASH_CONSIDERATION", "CASH_IN_LIEU"}
    )
