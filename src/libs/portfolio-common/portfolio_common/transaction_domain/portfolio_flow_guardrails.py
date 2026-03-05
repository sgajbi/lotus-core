from portfolio_common.events import TransactionEvent

from .cash_entry_mode import AUTO_GENERATE_CASH_ENTRY_MODE, normalize_cash_entry_mode

PORTFOLIO_FLOW_NO_AUTO_GENERATE_TRANSACTION_TYPES = {
    "FEE",
    "TAX",
    "DEPOSIT",
    "WITHDRAWAL",
    "TRANSFER_IN",
    "TRANSFER_OUT",
}


def is_portfolio_flow_no_auto_generate_transaction_type(transaction_type: str | None) -> bool:
    return (transaction_type or "").upper() in PORTFOLIO_FLOW_NO_AUTO_GENERATE_TRANSACTION_TYPES


def assert_portfolio_flow_cash_entry_mode_allowed(event: TransactionEvent) -> None:
    if event.cash_entry_mode is None:
        return

    if not is_portfolio_flow_no_auto_generate_transaction_type(event.transaction_type):
        return

    if normalize_cash_entry_mode(event.cash_entry_mode) == AUTO_GENERATE_CASH_ENTRY_MODE:
        raise ValueError(
            "AUTO_GENERATE cash_entry_mode is not supported for portfolio-level flow "
            "transaction types (FEE, TAX, DEPOSIT, WITHDRAWAL, TRANSFER_IN, TRANSFER_OUT)."
        )
