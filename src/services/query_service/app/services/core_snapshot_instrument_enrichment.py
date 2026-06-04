from __future__ import annotations

from typing import Any

from ..dtos.integration_dto import InstrumentEnrichmentRecord
from ..repositories.identifier_normalization import normalize_security_id


def requested_instrument_security_ids(security_ids: list[str]) -> list[str]:
    return [value.strip() for value in security_ids if value and value.strip()]


def instrument_enrichment_records(
    *,
    requested_ids: list[str],
    instruments: list[Any],
) -> list[InstrumentEnrichmentRecord]:
    by_security_id = instrument_enrichment_map(instruments)
    return [
        instrument_enrichment_record(
            security_id=security_id,
            instrument=by_security_id.get(security_id),
        )
        for security_id in requested_ids
    ]


def instrument_enrichment_map(instruments: list[Any]) -> dict[str, Any]:
    return {
        security_id: item
        for item in instruments
        if (security_id := normalize_security_id(item.security_id))
    }


def instrument_enrichment_record(
    *,
    security_id: str,
    instrument: Any,
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
