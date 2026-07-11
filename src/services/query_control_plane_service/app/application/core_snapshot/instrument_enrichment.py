"""Map source-owned instrument records to the public enrichment contract."""

from __future__ import annotations

from portfolio_common.identifiers import normalize_lookup_identifier as normalize_security_id

from ...contracts.instrument_enrichment import InstrumentEnrichmentRecord
from ...domain.core_snapshot import CoreSnapshotInstrument


def requested_instrument_security_ids(security_ids: list[str]) -> list[str]:
    return [value.strip() for value in security_ids if value and value.strip()]


def instrument_enrichment_records(
    *,
    requested_ids: list[str],
    instruments: list[CoreSnapshotInstrument],
) -> list[InstrumentEnrichmentRecord]:
    by_security_id = instrument_enrichment_map(instruments)
    return [
        instrument_enrichment_record(
            security_id=security_id,
            instrument=by_security_id.get(security_id),
        )
        for security_id in requested_ids
    ]


def instrument_enrichment_map(
    instruments: list[CoreSnapshotInstrument],
) -> dict[str, CoreSnapshotInstrument]:
    return {
        security_id: item
        for item in instruments
        if (security_id := normalize_security_id(item.security_id))
    }


def instrument_enrichment_record(
    *,
    security_id: str,
    instrument: CoreSnapshotInstrument | None,
) -> InstrumentEnrichmentRecord:
    if instrument is None:
        return InstrumentEnrichmentRecord(security_id=security_id)
    return InstrumentEnrichmentRecord(
        security_id=security_id,
        issuer_id=instrument.issuer_id,
        issuer_name=instrument.issuer_name,
        ultimate_parent_issuer_id=instrument.ultimate_parent_issuer_id,
        ultimate_parent_issuer_name=instrument.ultimate_parent_issuer_name,
        liquidity_tier=instrument.liquidity_tier,
    )
