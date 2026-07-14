"""Prepare framework-neutral booked transactions for canonical cost processing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from portfolio_common.domain.cost_basis_method import CostBasisMethod, normalize_cost_basis_method
from portfolio_common.domain.transaction_control_codes import (
    normalize_transaction_control_code,
)

from ...domain import BookedTransaction
from ...domain.transaction import enrich_booking_metadata
from ...domain.transaction.corporate_action import (
    assert_bundle_a_corporate_action_valid,
    is_bundle_a_corporate_action,
)
from ...domain.transaction.fx import (
    FX_BUSINESS_TRANSACTION_TYPES,
    enrich_fx_transaction_metadata,
)

_INSTRUMENT_REFERENCE_OPTIONAL_TRANSACTION_TYPES = {
    "ADJUSTMENT",
    *FX_BUSINESS_TRANSACTION_TYPES,
}


class CostProcessingRoute(str, Enum):
    """Identify the domain calculation path for a booked transaction."""

    COST_BASIS = "cost_basis"
    FOREIGN_EXCHANGE = "foreign_exchange"


@dataclass(frozen=True, slots=True)
class PreparedCostTransaction:
    """Carry normalized transaction and portfolio policy into cost processing."""

    transaction: BookedTransaction
    transaction_type: str
    cost_basis_method: CostBasisMethod
    route: CostProcessingRoute


class InstrumentReferenceUnavailableError(Exception):
    """Report a product transaction whose instrument reference is unavailable."""

    def __init__(self, transaction: BookedTransaction) -> None:
        self.portfolio_id = transaction.portfolio_id
        self.transaction_id = transaction.transaction_id
        self.security_id = transaction.security_id
        super().__init__(
            f"Instrument reference {transaction.security_id} not found for transaction "
            f"{transaction.transaction_id}. Retrying until instrument master data is available."
        )


def prepare_cost_transaction(
    transaction: BookedTransaction,
    *,
    cost_basis_method: str | CostBasisMethod,
    instrument_reference_available: bool,
) -> PreparedCostTransaction:
    """Apply deterministic booking policy and select the canonical cost-processing route."""

    resolved_method = normalize_cost_basis_method(cost_basis_method)
    prepared_transaction = enrich_booking_metadata(
        transaction,
        cost_basis_method=resolved_method,
    )
    prepared_transaction = enrich_fx_transaction_metadata(prepared_transaction)
    transaction_type = normalize_transaction_control_code(prepared_transaction.transaction_type)

    if is_bundle_a_corporate_action(transaction_type):
        assert_bundle_a_corporate_action_valid(prepared_transaction)
    if (
        transaction_type not in _INSTRUMENT_REFERENCE_OPTIONAL_TRANSACTION_TYPES
        and not instrument_reference_available
    ):
        raise InstrumentReferenceUnavailableError(prepared_transaction)

    route = (
        CostProcessingRoute.FOREIGN_EXCHANGE
        if transaction_type in FX_BUSINESS_TRANSACTION_TYPES
        else CostProcessingRoute.COST_BASIS
    )
    return PreparedCostTransaction(
        transaction=prepared_transaction,
        transaction_type=transaction_type,
        cost_basis_method=resolved_method,
        route=route,
    )
