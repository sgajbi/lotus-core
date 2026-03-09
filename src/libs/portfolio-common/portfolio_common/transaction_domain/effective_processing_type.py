from portfolio_common.events import TransactionEvent

FX_COMPONENT_PROCESSING_TYPES = {
    "FX_CONTRACT_OPEN",
    "FX_CONTRACT_CLOSE",
    "FX_CASH_SETTLEMENT_BUY",
    "FX_CASH_SETTLEMENT_SELL",
}


def resolve_effective_processing_transaction_type(event: TransactionEvent) -> str:
    """
    Returns the concrete processing type for a persisted transaction row.

    For most transactions this is simply transaction_type.
    For FX, transaction_type remains the business deal type while component_type
    identifies the concrete row behavior required by downstream processors.
    """
    component_type = (event.component_type or "").upper()
    if component_type in FX_COMPONENT_PROCESSING_TYPES:
        return component_type
    return event.transaction_type.upper()
