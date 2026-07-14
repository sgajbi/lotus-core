"""Validate and persist one foreign-exchange transaction component."""

from dataclasses import dataclass

from ...domain.transaction import BookedTransaction
from ...domain.transaction.fx import (
    FxContractInstrument,
    assert_fx_processed_transaction_valid,
    build_fx_contract_instrument,
    build_fx_processed_transaction,
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
    await transaction_persistence.upsert_booked_transaction(processed_transaction)
    return ForeignExchangeBookingResult(
        transaction=processed_transaction,
        contract_instrument=build_fx_contract_instrument(processed_transaction),
    )
