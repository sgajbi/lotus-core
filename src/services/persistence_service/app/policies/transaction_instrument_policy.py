"""Instrument-reference policy for raw transaction persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RAW_TRANSACTION_INSTRUMENT_POLICY_ID = "raw_transaction_instrument_reference_policy_v1"
MISSING_INSTRUMENT_REASON_CODE = "TRANSACTION_INSTRUMENT_REFERENCE_PENDING"

InstrumentReferenceStatus = Literal["validated", "provisional_raw_landing"]


@dataclass(frozen=True)
class TransactionInstrumentReferenceDecision:
    policy_id: str
    security_id: str
    instrument_exists: bool
    status: InstrumentReferenceStatus
    reason_code: str | None
    allow_raw_persistence: bool
    downstream_lifecycle_blocked: bool


def decide_transaction_instrument_reference(
    *,
    security_id: str,
    instrument_exists: bool,
) -> TransactionInstrumentReferenceDecision:
    normalized_security_id = security_id.strip()
    if instrument_exists:
        return TransactionInstrumentReferenceDecision(
            policy_id=RAW_TRANSACTION_INSTRUMENT_POLICY_ID,
            security_id=normalized_security_id,
            instrument_exists=True,
            status="validated",
            reason_code=None,
            allow_raw_persistence=True,
            downstream_lifecycle_blocked=False,
        )
    return TransactionInstrumentReferenceDecision(
        policy_id=RAW_TRANSACTION_INSTRUMENT_POLICY_ID,
        security_id=normalized_security_id,
        instrument_exists=False,
        status="provisional_raw_landing",
        reason_code=MISSING_INSTRUMENT_REASON_CODE,
        allow_raw_persistence=True,
        downstream_lifecycle_blocked=True,
    )
