from portfolio_common.events import TransactionEvent
from portfolio_common.transaction_type_registry import (
    production_transaction_types_for_lifecycle_families,
)

from .cash_entry_mode import AUTO_GENERATE_CASH_ENTRY_MODE, normalize_cash_entry_mode
from .control_code_normalization import normalize_transaction_control_code

PORTFOLIO_FLOW_NO_AUTO_GENERATE_TRANSACTION_TYPES = (
    production_transaction_types_for_lifecycle_families("cash_movement", "expense", "transfer")
)


def is_portfolio_flow_no_auto_generate_transaction_type(transaction_type: str | None) -> bool:
    normalized_type = normalize_transaction_control_code(transaction_type)
    return normalized_type in PORTFOLIO_FLOW_NO_AUTO_GENERATE_TRANSACTION_TYPES


def assert_portfolio_flow_cash_entry_mode_allowed(event: TransactionEvent) -> None:
    if event.cash_entry_mode is None:
        return

    if not is_portfolio_flow_no_auto_generate_transaction_type(event.transaction_type):
        return

    if normalize_cash_entry_mode(event.cash_entry_mode) == AUTO_GENERATE_CASH_ENTRY_MODE:
        supported_types = ", ".join(sorted(PORTFOLIO_FLOW_NO_AUTO_GENERATE_TRANSACTION_TYPES))
        raise ValueError(
            "AUTO_GENERATE cash_entry_mode is not supported for portfolio-level flow "
            f"transaction types ({supported_types})."
        )
