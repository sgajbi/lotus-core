"""Validate and persist one foreign-exchange transaction component."""

from dataclasses import dataclass

from portfolio_common.domain.calculation_lineage import calculation_lineage_binds_output

from ...domain.transaction import BookedTransaction
from ...domain.transaction.fx import (
    FxContractInstrument,
    assert_fx_processed_transaction_valid,
    build_fx_contract_instrument,
    build_fx_processed_transaction,
    fx_booked_transaction_output_payload,
)
from ...ports.foreign_exchange import ForeignExchangeTransactionPersistencePort


@dataclass(frozen=True, slots=True)
class ForeignExchangeBookingResult:
    """Return the processed transaction and optional synthetic contract instrument."""

    transaction: BookedTransaction
    contract_instrument: FxContractInstrument | None


async def book_foreign_exchange_transaction(
    *,
    transaction: BookedTransaction,
    transaction_persistence: ForeignExchangeTransactionPersistencePort,
) -> ForeignExchangeBookingResult:
    """Apply baseline FX policy, validate, persist, and derive contract identity."""

    processed_transaction = build_fx_processed_transaction(transaction)
    assert_fx_processed_transaction_valid(processed_transaction)
    persisted_transaction = await transaction_persistence.upsert_booked_transaction(
        processed_transaction
    )
    rebound_transaction = build_fx_processed_transaction(persisted_transaction)
    assert_fx_processed_transaction_valid(rebound_transaction)
    if rebound_transaction.calculation_lineage != persisted_transaction.calculation_lineage:
        persisted_transaction = await transaction_persistence.upsert_booked_transaction(
            rebound_transaction
        )
    if not calculation_lineage_binds_output(
        persisted_transaction.calculation_lineage,
        output_payload=fx_booked_transaction_output_payload(persisted_transaction),
    ):
        raise RuntimeError(
            "Persisted FX calculation lineage does not bind the final durable transaction row."
        )
    return ForeignExchangeBookingResult(
        transaction=persisted_transaction,
        contract_instrument=build_fx_contract_instrument(persisted_transaction),
    )
