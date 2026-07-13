"""Resolve the economic processing type for a booked transaction component."""

from __future__ import annotations

from typing import Protocol

from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code


class ProcessingTypeSource(Protocol):
    """Structural transaction fields required by processing-type policies."""

    transaction_type: str
    component_type: str | None


FX_COMPONENT_PROCESSING_TYPES = {
    "FX_CONTRACT_OPEN",
    "FX_CONTRACT_CLOSE",
    "FX_CASH_SETTLEMENT_BUY",
    "FX_CASH_SETTLEMENT_SELL",
}
NON_CASHFLOW_PROCESSING_TYPES = {"FX_CONTRACT_OPEN", "FX_CONTRACT_CLOSE"}


def normalize_processing_type(value: str | None) -> str:
    return normalize_transaction_control_code(value)


def resolve_effective_processing_transaction_type(transaction: ProcessingTypeSource) -> str:
    """
    Returns the concrete processing type for a persisted transaction row.

    For most transactions this is simply transaction_type.
    For FX, transaction_type remains the business deal type while component_type
    identifies the concrete row behavior required by downstream processors.
    """
    component_type = normalize_processing_type(transaction.component_type)
    if component_type in FX_COMPONENT_PROCESSING_TYPES:
        return component_type
    return normalize_processing_type(transaction.transaction_type)


def requires_cashflow_processing(transaction: ProcessingTypeSource) -> bool:
    """
    Return whether the concrete transaction row is expected to emit a cashflow.

    FX contract open/close rows carry position exposure only; their settlement cash
    movements are represented by separate FX cash settlement rows.
    """
    return (
        resolve_effective_processing_transaction_type(transaction)
        not in NON_CASHFLOW_PROCESSING_TYPES
    )
