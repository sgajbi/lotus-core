"""Define cash-entry mode and portfolio-level cash-flow policy."""

from __future__ import annotations

from enum import StrEnum

from portfolio_common.domain.transaction.type_registry import (
    get_transaction_type_definition,
    production_transaction_types_for_lifecycle_families,
)
from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ..booked import BookedTransaction
from .cash_movement import calculate_settlement_cash_movement


class CashEntryMode(StrEnum):
    """Identify whether Core or an upstream source supplies a settlement cash leg."""

    AUTO_GENERATE = "AUTO_GENERATE"
    UPSTREAM_PROVIDED = "UPSTREAM_PROVIDED"


PORTFOLIO_LEVEL_CASH_FLOW_TRANSACTION_TYPES = frozenset(
    production_transaction_types_for_lifecycle_families(
        "cash_movement",
        "expense",
        "transfer",
    )
)


def resolve_cash_entry_mode(value: str | None) -> CashEntryMode:
    """Return the canonical cash-entry mode, defaulting to Core generation."""

    normalized = normalize_transaction_control_code(value or CashEntryMode.AUTO_GENERATE)
    try:
        return CashEntryMode(normalized)
    except ValueError as exc:
        raise ValueError(
            "Unsupported cash_entry_mode. Expected AUTO_GENERATE or UPSTREAM_PROVIDED."
        ) from exc


def is_upstream_provided_cash_entry_mode(value: str | None) -> bool:
    """Return whether an upstream source is responsible for the settlement cash leg."""

    return resolve_cash_entry_mode(value) is CashEntryMode.UPSTREAM_PROVIDED


def is_portfolio_level_cash_flow(transaction_type: str | None) -> bool:
    """Return whether a transaction is itself a portfolio-level cash flow."""

    normalized_type = normalize_transaction_control_code(transaction_type)
    return normalized_type in PORTFOLIO_LEVEL_CASH_FLOW_TRANSACTION_TYPES


def assert_cash_entry_mode_supported(transaction: BookedTransaction) -> None:
    """Reject cash-entry modes that cannot satisfy the registry settlement contract."""

    definition = get_transaction_type_definition(transaction.transaction_type)
    default_mode = definition.default_cash_entry_mode if definition is not None else None
    if transaction.cash_entry_mode is None and default_mode is None:
        return
    mode = resolve_cash_entry_mode(transaction.cash_entry_mode or default_mode)
    if is_portfolio_level_cash_flow(transaction.transaction_type):
        if mode is not CashEntryMode.AUTO_GENERATE:
            return
        supported_types = ", ".join(sorted(PORTFOLIO_LEVEL_CASH_FLOW_TRANSACTION_TYPES))
        raise ValueError(
            "AUTO_GENERATE cash_entry_mode is not supported for portfolio-level flow "
            f"transaction types ({supported_types})."
        )
    if (
        definition is not None
        and definition.lifecycle_family == "redemption"
        and default_mode == CashEntryMode.AUTO_GENERATE.value
        and mode is CashEntryMode.AUTO_GENERATE
        and not (transaction.settlement_cash_account_id or "").strip()
    ):
        if (
            calculate_settlement_cash_movement(transaction).signed_amount == 0
        ):
            return
        raise ValueError(
            "settlement_cash_account_id is required when cash_entry_mode is AUTO_GENERATE "
            f"for {transaction.transaction_type.strip().upper()}."
        )
