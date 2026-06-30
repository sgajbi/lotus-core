from portfolio_common.events import TransactionEvent

from .control_code_normalization import normalize_transaction_control_code

FX_COMPONENT_PROCESSING_TYPES = {
    "FX_CONTRACT_OPEN",
    "FX_CONTRACT_CLOSE",
    "FX_CASH_SETTLEMENT_BUY",
    "FX_CASH_SETTLEMENT_SELL",
}
NON_CASHFLOW_PROCESSING_TYPES = {"FX_CONTRACT_OPEN", "FX_CONTRACT_CLOSE"}


def normalize_processing_type(value: str | None) -> str:
    return normalize_transaction_control_code(value)


def resolve_effective_processing_transaction_type(event: TransactionEvent) -> str:
    """
    Returns the concrete processing type for a persisted transaction row.

    For most transactions this is simply transaction_type.
    For FX, transaction_type remains the business deal type while component_type
    identifies the concrete row behavior required by downstream processors.
    """
    component_type = normalize_processing_type(event.component_type)
    if component_type in FX_COMPONENT_PROCESSING_TYPES:
        return component_type
    return normalize_processing_type(event.transaction_type)


def requires_cashflow_processing(event: TransactionEvent) -> bool:
    """
    Return whether the concrete transaction row is expected to emit a cashflow.

    FX contract open/close rows carry position exposure only; their settlement cash
    movements are represented by separate FX cash settlement rows.
    """
    return resolve_effective_processing_transaction_type(event) not in NON_CASHFLOW_PROCESSING_TYPES
