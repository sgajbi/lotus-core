from __future__ import annotations

from typing import Any, cast

from ..dtos.integration_dto import InstrumentEnrichmentRecord
from .core_snapshot_errors import CoreSnapshotBadRequestError
from .core_snapshot_instrument_enrichment import (
    instrument_enrichment_records,
    requested_instrument_security_ids,
)


class CoreSnapshotInstrumentEnrichmentReader:
    def __init__(self, *, instrument_repo: Any) -> None:
        self._instrument_repo = instrument_repo

    async def get_instrument_enrichment_bulk(
        self,
        security_ids: list[str],
    ) -> list[InstrumentEnrichmentRecord]:
        requested_ids = requested_instrument_security_ids(security_ids)
        if not requested_ids:
            raise CoreSnapshotBadRequestError("security_ids must contain at least one identifier")
        instruments = await self._instrument_repo.get_by_security_ids(requested_ids)
        return cast(
            list[InstrumentEnrichmentRecord],
            instrument_enrichment_records(
                requested_ids=requested_ids,
                instruments=instruments,
            ),
        )
