"""Read source-owned instrument enrichment through the snapshot source port."""

from __future__ import annotations

from typing import cast

from ...contracts.instrument_enrichment import InstrumentEnrichmentRecord
from ...ports.core_snapshot import CoreSnapshotSourceReader
from .errors import CoreSnapshotBadRequestError
from .instrument_enrichment import (
    instrument_enrichment_records,
    requested_instrument_security_ids,
)


class CoreSnapshotInstrumentEnrichmentReader:
    def __init__(self, *, source_reader: CoreSnapshotSourceReader) -> None:
        self._source_reader = source_reader

    async def get_instrument_enrichment_bulk(
        self,
        security_ids: list[str],
    ) -> list[InstrumentEnrichmentRecord]:
        requested_ids = requested_instrument_security_ids(security_ids)
        if not requested_ids:
            raise CoreSnapshotBadRequestError("security_ids must contain at least one identifier")
        instruments = await self._source_reader.get_instruments(requested_ids)
        return cast(
            list[InstrumentEnrichmentRecord],
            instrument_enrichment_records(
                requested_ids=requested_ids,
                instruments=instruments,
            ),
        )
