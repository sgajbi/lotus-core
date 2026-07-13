"""Map settlement cash domain failures to application rejection contracts."""

from ..domain import BookedTransaction
from ..domain.transaction import SettlementCashValidationError
from .errors import TransactionProcessingRejected


def build_settlement_cash_rejection(
    transaction: BookedTransaction,
    error: SettlementCashValidationError,
) -> TransactionProcessingRejected:
    """Build a non-retryable rejection with source-safe settlement diagnostics."""

    return TransactionProcessingRejected(
        reason_code=error.reason_code.value,
        detail={
            "portfolio_id": transaction.portfolio_id,
            "transaction_id": transaction.transaction_id,
            "transaction_type": transaction.transaction_type.strip().upper(),
            "field": error.field,
            "available_proceeds": str(error.available_proceeds),
            "fee_amount": str(error.fee_amount),
            "net_settlement_amount": str(error.net_settlement_amount),
        },
        retryable=False,
    )
