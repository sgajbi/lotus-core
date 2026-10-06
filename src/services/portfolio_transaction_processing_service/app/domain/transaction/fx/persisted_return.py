"""Qualify durable FX returns without promoting normalized output to source facts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from decimal import Decimal
from typing import cast

from portfolio_common.domain.calculation_lineage import (
    calculation_lineage_binds_output,
    canonical_content_hash,
)
from portfolio_common.domain.transaction import (
    TRANSACTION_PAYLOAD_MATERIAL_FIELDS,
    transaction_payload_fingerprint,
)
from portfolio_common.domain.transaction.fx_source_presence import (
    FX_ORIGINAL_PNL_FIELDS,
    fx_original_pnl_values,
)
from portfolio_common.domain.transaction.source_evidence_revision import verify_retained_fx_source
from portfolio_common.domain.transaction_control_codes import normalize_transaction_control_code

from ..booked import BookedTransaction
from .baseline_processing import (
    fx_booked_transaction_output_payload,
    fx_persisted_transaction_material,
)


@dataclass(frozen=True, slots=True)
class FxBookingContext:
    """Owning application admission; not an event field or an economic command."""

    initial_publication: bool
    admitted_epoch: int | None
    retention_witness: FxPersistenceWitness | None = None


@dataclass(frozen=True, slots=True)
class FxRawSourceFacts:
    """Detached exact raw projection already qualified by the repository."""

    raw_event_id: int
    raw_payload_hash: str
    original_pnl: tuple[Decimal | None, ...]
    material_fingerprint: str
    transaction_fx_rate: Decimal | None
    transaction_fx_rate_origin: str | None


@dataclass(frozen=True, slots=True)
class FxPersistenceWitness:
    """Pre-write owned row and original facts, retained in the same financial UOW."""

    durable_before: BookedTransaction
    original_pnl: tuple[Decimal | None, ...] | None
    raw_source: FxRawSourceFacts | None
    admitted_epoch: int | None = None


@dataclass(frozen=True, slots=True)
class FxCanonicalSourceLoad:
    """Explicit source load result; retention facts never imply canonical authority."""

    transaction: BookedTransaction | None
    retention_witness: FxPersistenceWitness | None


def original_fx_pnl_values(transaction: BookedTransaction) -> tuple[Decimal | None, ...]:
    return tuple(getattr(transaction, name) for name in FX_ORIGINAL_PNL_FIELDS)


def fx_source_material(transaction: BookedTransaction) -> dict[str, object]:
    """Use the existing raw identity fields, not the P&L-excluding processor hash."""
    names = (
        TRANSACTION_PAYLOAD_MATERIAL_FIELDS
        | set(FX_ORIGINAL_PNL_FIELDS)
        | {"transaction_fx_rate", "transaction_fx_rate_origin"}
    )
    return {
        field.name: getattr(transaction, field.name)
        for field in fields(transaction)
        if field.name in names
    }


def qualify_fx_raw_source(
    *,
    raw: Mapping[str, object],
    transaction: BookedTransaction,
    stored_fingerprint: str,
    raw_event_id: int,
    raw_payload_hash: str,
) -> FxRawSourceFacts:
    """Qualify original receipt when present; initial raw does not need an old receipt."""
    if raw_event_id <= 0 or raw_payload_hash != canonical_content_hash(raw):
        raise ValueError("FX original raw provenance is invalid")
    fingerprint = transaction_payload_fingerprint(raw)
    if transaction.calculation_lineage is None and fingerprint != stored_fingerprint:
        raise ValueError("FX original raw fingerprint is unavailable")
    if raw.get("tenant_id") not in (None, transaction.tenant_id) or any(
        raw.get(name) != getattr(transaction, name)
        for name in ("transaction_id", "portfolio_id", "security_id")
    ):
        raise ValueError("FX original raw ownership is unavailable")
    original = fx_original_pnl_values(raw)
    rate_value = raw.get("transaction_fx_rate")
    if rate_value is not None and not isinstance(rate_value, (str, Decimal)):
        raise ValueError("FX original rate is not exact decimal text")
    rate = Decimal(rate_value) if rate_value is not None else None
    origin = raw.get("transaction_fx_rate_origin")
    if (rate is not None and not rate.is_finite()) or (
        origin is not None and not isinstance(origin, str)
    ):
        raise ValueError("FX original rate or origin is invalid")
    if transaction.calculation_lineage is not None:
        verify_retained_fx_source(
            raw_source=raw,
            ledger_output=fx_persisted_transaction_material(transaction),
            stored_fingerprint=stored_fingerprint,
            receipt_payload=transaction.calculation_lineage.lineage_payload(),
            tenant_id=transaction.tenant_id or "",
        )
    return FxRawSourceFacts(
        raw_event_id=raw_event_id,
        raw_payload_hash=raw_payload_hash,
        original_pnl=tuple(cast(Decimal | None, original[name]) for name in FX_ORIGINAL_PNL_FIELDS),
        material_fingerprint=fingerprint,
        transaction_fx_rate=rate,
        transaction_fx_rate_origin=cast(str | None, origin),
    )


def qualify_fx_booking_source(
    transaction: BookedTransaction,
    witness: FxPersistenceWitness | None,
    context: FxBookingContext | None,
) -> tuple[Decimal | None, ...]:
    """Keep original six values through rebind, including unavailable versus zero."""
    if context is not None and context.admitted_epoch != transaction.epoch:
        raise ValueError("FX admitted epoch changed before booking")
    if witness is None:
        if (
            context is not None
            and normalize_transaction_control_code(transaction.fx_realized_pnl_mode)
            == "UPSTREAM_PROVIDED"
        ):
            raise ValueError("FX durable source witness is unavailable")
        return original_fx_pnl_values(transaction)
    before = witness.durable_before
    if witness.admitted_epoch != transaction.epoch:
        raise ValueError("FX witness belongs to a different admitted epoch")
    if any(
        getattr(before, name) != getattr(transaction, name)
        for name in ("tenant_id", "portfolio_id", "security_id", "transaction_id")
    ):
        raise ValueError("FX durable witness owner mismatch")
    if normalize_transaction_control_code(transaction.fx_realized_pnl_mode) != "UPSTREAM_PROVIDED":
        return original_fx_pnl_values(transaction)
    raw = witness.raw_source
    if raw is None or witness.original_pnl is None:
        raise ValueError("FX original upstream source is unavailable")
    if witness.original_pnl != raw.original_pnl:
        raise ValueError("FX detached source projection differs from original raw facts")
    if before.calculation_lineage is None and (
        context is None or not context.initial_publication or context.admitted_epoch is not None
    ):
        raise ValueError("FX initial raw requires owning first-publication admission")
    allowed_pnl = {raw.original_pnl}
    if before.calculation_lineage is not None:
        allowed_pnl.add(original_fx_pnl_values(before))
    if original_fx_pnl_values(transaction) not in allowed_pnl:
        raise ValueError("FX admitted P&L differs from qualified original or durable output")
    material = fx_source_material(transaction)
    material.update(zip(FX_ORIGINAL_PNL_FIELDS, raw.original_pnl, strict=True))
    if transaction.source_system is None:
        material["source_system"] = before.source_system
    if (
        transaction_payload_fingerprint(material) != raw.material_fingerprint
        or transaction.transaction_fx_rate != raw.transaction_fx_rate
        or transaction.transaction_fx_rate_origin != raw.transaction_fx_rate_origin
    ):
        raise ValueError("FX admitted material differs from original raw source")
    return witness.original_pnl


def qualify_first_fx_return(
    submitted: BookedTransaction,
    persisted: BookedTransaction,
    witness: FxPersistenceWitness | None,
) -> None:
    expected = submitted
    if submitted.source_system is None and persisted.source_system is not None:
        if witness is None or persisted.source_system != witness.durable_before.source_system:
            raise ValueError("FX return invented retained source provenance")
        expected = replace(submitted, source_system=persisted.source_system)
    if (
        persisted.calculation_lineage != submitted.calculation_lineage
        or fx_booked_transaction_output_payload(persisted)
        != fx_booked_transaction_output_payload(expected)
        or persisted.epoch not in (None, submitted.epoch)
    ):
        raise ValueError("FX persistence changed admitted material or original receipt")


def qualify_final_fx_return(submitted: BookedTransaction, persisted: BookedTransaction) -> None:
    if (
        persisted.calculation_lineage != submitted.calculation_lineage
        or fx_booked_transaction_output_payload(persisted)
        != fx_booked_transaction_output_payload(submitted)
        or persisted.epoch not in (None, submitted.epoch)
        or persisted.calculation_lineage is None
        or not calculation_lineage_binds_output(
            persisted.calculation_lineage,
            output_payload=fx_booked_transaction_output_payload(persisted),
        )
    ):
        raise RuntimeError("Persisted FX return differs from the qualified final receipt and row")
