from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.query_service.app.services.core_snapshot_errors import (
    CoreSnapshotBadRequestError,
)
from src.services.query_service.app.services.core_snapshot_instrument_enrichment_reader import (
    CoreSnapshotInstrumentEnrichmentReader,
)

pytestmark = pytest.mark.asyncio


def _instrument(security_id: str):
    return SimpleNamespace(
        security_id=security_id,
        issuer_id=f"ISSUER_{security_id}",
        issuer_name=f"{security_id} issuer",
        ultimate_parent_issuer_id=f"PARENT_{security_id}",
        ultimate_parent_issuer_name=f"{security_id} parent",
        liquidity_tier="L2",
    )


async def test_instrument_enrichment_reader_preserves_order_and_unknowns() -> None:
    instrument_repo = AsyncMock()
    instrument_repo.get_by_security_ids.return_value = [
        _instrument("SEC_MSFT_US"),
        _instrument("SEC_AAPL_US"),
    ]
    reader = CoreSnapshotInstrumentEnrichmentReader(instrument_repo=instrument_repo)

    records = await reader.get_instrument_enrichment_bulk(
        ["SEC_AAPL_US", "SEC_UNKNOWN", "SEC_MSFT_US"]
    )

    assert [record.security_id for record in records] == [
        "SEC_AAPL_US",
        "SEC_UNKNOWN",
        "SEC_MSFT_US",
    ]
    assert records[0].issuer_id == "ISSUER_SEC_AAPL_US"
    assert records[0].liquidity_tier == "L2"
    assert records[1].issuer_id is None
    assert records[1].liquidity_tier is None
    assert records[2].issuer_id == "ISSUER_SEC_MSFT_US"
    assert records[2].liquidity_tier == "L2"


async def test_instrument_enrichment_reader_normalizes_returned_security_ids() -> None:
    instrument_repo = AsyncMock()
    instrument_repo.get_by_security_ids.return_value = [_instrument(" SEC_AAPL_US ")]
    reader = CoreSnapshotInstrumentEnrichmentReader(instrument_repo=instrument_repo)

    records = await reader.get_instrument_enrichment_bulk([" SEC_AAPL_US "])

    assert records[0].security_id == "SEC_AAPL_US"
    assert records[0].issuer_id == "ISSUER_ SEC_AAPL_US "
    instrument_repo.get_by_security_ids.assert_awaited_once_with(["SEC_AAPL_US"])


async def test_instrument_enrichment_reader_rejects_empty_request() -> None:
    instrument_repo = AsyncMock()
    reader = CoreSnapshotInstrumentEnrichmentReader(instrument_repo=instrument_repo)

    with pytest.raises(
        CoreSnapshotBadRequestError,
        match="security_ids must contain at least one identifier",
    ):
        await reader.get_instrument_enrichment_bulk(["", "  "])

    instrument_repo.get_by_security_ids.assert_not_awaited()
