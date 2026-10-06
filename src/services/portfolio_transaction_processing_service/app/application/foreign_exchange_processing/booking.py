"""Validate and persist one foreign-exchange transaction component."""

from dataclasses import dataclass

from portfolio_common.domain.transaction.fx_source_presence import FX_ORIGINAL_PNL_FIELDS

from ...domain.transaction import BookedTransaction
from ...domain.transaction.fx import (
    FxContractInstrument,
    assert_fx_processed_transaction_valid,
    build_fx_contract_instrument,
    build_fx_processed_transaction,
)
from ...domain.transaction.fx.persisted_return import (
    FxBookingContext,
    qualify_final_fx_return,
    qualify_first_fx_return,
    qualify_fx_booking_source,
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
    booking_context: FxBookingContext | None = None,
) -> ForeignExchangeBookingResult:
    """Apply baseline FX policy, validate, persist, and derive contract identity."""

    witness = booking_context.retention_witness if booking_context is not None else None
    if witness is None:
        witness = await transaction_persistence.load_fx_retention_witness(transaction)
    original = qualify_fx_booking_source(transaction, witness, booking_context)
    source_pnl = dict(zip(FX_ORIGINAL_PNL_FIELDS, original, strict=True))
    processed_transaction = build_fx_processed_transaction(transaction, original_pnl=source_pnl)
    assert_fx_processed_transaction_valid(processed_transaction)
    persisted_transaction = await transaction_persistence.upsert_booked_transaction(
        processed_transaction
    )
    qualify_first_fx_return(processed_transaction, persisted_transaction, witness)
    rebound_transaction = build_fx_processed_transaction(
        persisted_transaction, original_pnl=source_pnl
    )
    assert_fx_processed_transaction_valid(rebound_transaction)
    if rebound_transaction.calculation_lineage != persisted_transaction.calculation_lineage:
        persisted_transaction = await transaction_persistence.upsert_booked_transaction(
            rebound_transaction
        )
    qualify_final_fx_return(rebound_transaction, persisted_transaction)
    return ForeignExchangeBookingResult(
        transaction=persisted_transaction,
        contract_instrument=build_fx_contract_instrument(persisted_transaction),
    )
