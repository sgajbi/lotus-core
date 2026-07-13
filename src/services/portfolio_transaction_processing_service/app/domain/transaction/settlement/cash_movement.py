"""Calculate signed settlement cash movements for ordinary booked transactions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from portfolio_common.domain.transaction.fee_components import (
    TRANSACTION_FEE_COMPONENT_FIELDS,
    resolve_transaction_trade_fee,
)
from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..booked import BookedTransaction
from .interest import calculate_interest_settlement_economics
from .reason_codes import SettlementCashRejectionReasonCode


@dataclass(frozen=True, slots=True)
class SettlementCashValidationError(ValueError):
    """Describe a deterministic rejection of invalid settlement cash economics."""

    reason_code: SettlementCashRejectionReasonCode
    field: str
    message: str
    available_proceeds: Decimal
    fee_amount: Decimal
    net_settlement_amount: Decimal

    def __str__(self) -> str:
        return f"{self.reason_code.value}: {self.field}: {self.message}"


@dataclass(frozen=True, slots=True)
class SettlementCashMovement:
    """Carry one non-zero settlement amount signed from the portfolio perspective."""

    signed_amount: Decimal
    fee_amount: Decimal
    adjustment_reason: str

    @property
    def amount(self) -> Decimal:
        """Return the posting magnitude after the signed direction is validated."""

        return abs(self.signed_amount)

    @property
    def movement_direction(self) -> str:
        """Return the ledger direction represented by ``signed_amount``."""

        return "INFLOW" if self.signed_amount > 0 else "OUTFLOW"


SettlementCashResolver = Callable[[BookedTransaction, Decimal], SettlementCashMovement]


def calculate_settlement_cash_movement(
    transaction: BookedTransaction,
) -> SettlementCashMovement:
    """Calculate canonical signed settlement cash for an ordinary transaction."""

    transaction_type = normalize_transaction_control_code(transaction.transaction_type)
    resolver = _SETTLEMENT_CASH_RESOLVERS.get(transaction_type)
    if resolver is None:
        raise ValueError(f"{transaction.transaction_type} has no ordinary settlement cash policy")
    return resolver(transaction, _resolve_fee_amount(transaction))


def _resolve_fee_amount(transaction: BookedTransaction) -> Decimal:
    fee = resolve_transaction_trade_fee(
        transaction.trade_fee,
        {field: getattr(transaction, field) for field in TRANSACTION_FEE_COMPONENT_FIELDS},
    )
    return fee or Decimal(0)


def _calculate_buy_movement(
    transaction: BookedTransaction,
    fee: Decimal,
) -> SettlementCashMovement:
    return SettlementCashMovement(
        signed_amount=-(transaction.gross_transaction_amount + fee),
        fee_amount=fee,
        adjustment_reason="BUY_SETTLEMENT",
    )


def _calculate_sell_movement(
    transaction: BookedTransaction,
    fee: Decimal,
) -> SettlementCashMovement:
    return _calculate_positive_proceeds_movement(
        transaction=transaction,
        available_proceeds=transaction.gross_transaction_amount,
        fee=fee,
        reason_code=SettlementCashRejectionReasonCode.SELL_NON_POSITIVE_NET_SETTLEMENT,
        adjustment_reason="SELL_SETTLEMENT",
    )


def _calculate_dividend_movement(
    transaction: BookedTransaction,
    fee: Decimal,
) -> SettlementCashMovement:
    return _calculate_positive_proceeds_movement(
        transaction=transaction,
        available_proceeds=transaction.gross_transaction_amount,
        fee=fee,
        reason_code=SettlementCashRejectionReasonCode.DIVIDEND_NON_POSITIVE_NET_SETTLEMENT,
        adjustment_reason="DIVIDEND_SETTLEMENT",
    )


def _calculate_interest_movement(
    transaction: BookedTransaction,
    fee: Decimal,
) -> SettlementCashMovement:
    economics = calculate_interest_settlement_economics(transaction)
    direction = normalize_transaction_control_code(transaction.interest_direction or "INCOME")
    if (
        transaction.net_interest_amount is not None
        and transaction.net_interest_amount != economics.expected_net_interest_amount
    ):
        expected_settlement_amount = (
            economics.expected_net_interest_amount + fee
            if direction == "EXPENSE"
            else economics.expected_net_interest_amount - fee
        )
        raise SettlementCashValidationError(
            reason_code=(SettlementCashRejectionReasonCode.INTEREST_NET_RECONCILIATION_MISMATCH),
            field="net_interest_amount",
            message=(
                "net_interest_amount must equal gross_transaction_amount - "
                "withholding_tax_amount - other_interest_deductions_amount "
                "before transaction fees."
            ),
            available_proceeds=economics.expected_net_interest_amount,
            fee_amount=fee,
            net_settlement_amount=expected_settlement_amount,
        )
    settlement_amount = economics.settlement_cash_amount
    if settlement_amount <= 0:
        raise SettlementCashValidationError(
            reason_code=(SettlementCashRejectionReasonCode.INTEREST_NON_POSITIVE_NET_SETTLEMENT),
            field="trade_fee",
            message=(
                "INTEREST settlement cash must remain greater than zero after "
                "deductions and transaction fees."
            ),
            available_proceeds=economics.net_interest_amount,
            fee_amount=fee,
            net_settlement_amount=settlement_amount,
        )
    signed_amount = -settlement_amount if direction == "EXPENSE" else settlement_amount
    return SettlementCashMovement(
        signed_amount=signed_amount,
        fee_amount=fee,
        adjustment_reason=(
            "INTEREST_CHARGE_SETTLEMENT" if direction == "EXPENSE" else "INTEREST_SETTLEMENT"
        ),
    )


def _calculate_positive_proceeds_movement(
    *,
    transaction: BookedTransaction,
    available_proceeds: Decimal,
    fee: Decimal,
    reason_code: SettlementCashRejectionReasonCode,
    adjustment_reason: str,
) -> SettlementCashMovement:
    net_settlement = available_proceeds - fee
    if net_settlement <= 0:
        transaction_type = normalize_transaction_control_code(transaction.transaction_type)
        raise SettlementCashValidationError(
            reason_code=reason_code,
            field="trade_fee",
            message=(
                f"{transaction_type} settlement cash must remain greater than zero "
                "after transaction fees."
            ),
            available_proceeds=available_proceeds,
            fee_amount=fee,
            net_settlement_amount=net_settlement,
        )
    return SettlementCashMovement(
        signed_amount=net_settlement,
        fee_amount=fee,
        adjustment_reason=adjustment_reason,
    )


_SETTLEMENT_CASH_RESOLVERS: dict[str, SettlementCashResolver] = {
    "BUY": _calculate_buy_movement,
    "SELL": _calculate_sell_movement,
    "DIVIDEND": _calculate_dividend_movement,
    "INTEREST": _calculate_interest_movement,
}

ORDINARY_SETTLEMENT_TRANSACTION_TYPES = frozenset(_SETTLEMENT_CASH_RESOLVERS)
