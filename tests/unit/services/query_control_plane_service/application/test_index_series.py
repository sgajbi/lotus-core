"""Application tests for governed index price and return series windows."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application.index_series import (
    IndexSeriesService,
    build_index_price_series_response,
    build_index_return_series_response,
)
from src.services.query_control_plane_service.app.contracts.index_series import (
    IndexSeriesRequest,
    IntegrationWindow,
)
from src.services.query_control_plane_service.app.domain.index_series import (
    IndexPriceEvidence,
    IndexReturnEvidence,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)
REQUEST = IndexSeriesRequest(
    as_of_date=date(2026, 4, 10),
    window=IntegrationWindow(start_date=date(2026, 4, 9), end_date=date(2026, 4, 10)),
    frequency="daily",
)


def _price(series_date: date, *, quality_status: str = "accepted") -> IndexPriceEvidence:
    return IndexPriceEvidence(
        series_id="vendor-price",
        index_id="IDX_MSCI_WORLD_TR",
        series_date=series_date,
        index_price=Decimal("123.45"),
        series_currency="USD",
        value_convention="close_price",
        quality_status=quality_status,
        observed_at=EVIDENCE_AT,
        source_vendor="MSCI",
        source_record_id=f"price:{series_date.isoformat()}",
        created_at=EVIDENCE_AT,
        updated_at=EVIDENCE_AT,
    )


def _return(series_date: date, *, quality_status: str = "accepted") -> IndexReturnEvidence:
    return IndexReturnEvidence(
        series_id="vendor-return",
        index_id="IDX_MSCI_WORLD_TR",
        series_date=series_date,
        index_return=Decimal("0.0012"),
        return_period="1d",
        return_convention="total_return_index",
        series_currency="USD",
        quality_status=quality_status,
        observed_at=EVIDENCE_AT,
        source_vendor="MSCI",
        source_record_id=f"return:{series_date.isoformat()}",
        created_at=EVIDENCE_AT,
        updated_at=EVIDENCE_AT,
    )


def test_complete_price_window_is_current_and_content_hash_is_deterministic() -> None:
    rows = [_price(date(2026, 4, 9)), _price(date(2026, 4, 10))]

    first = build_index_price_series_response(
        index_id="IDX_MSCI_WORLD_TR", request=REQUEST, rows=rows, generated_at=GENERATED_AT
    )
    second = build_index_price_series_response(
        index_id="IDX_MSCI_WORLD_TR",
        request=REQUEST,
        rows=rows,
        generated_at=datetime(2026, 4, 10, 13, tzinfo=UTC),
    )

    assert first.completeness_status == "COMPLETE"
    assert first.record_count == 2
    assert first.source_evidence_current is True
    assert first.freshness_status == "CURRENT"
    assert first.source_batch_fingerprint == first.content_hash == first.source_digest
    assert first.content_hash == second.content_hash
    assert first.generated_at != second.generated_at


def test_partial_return_window_is_not_claimed_current() -> None:
    response = build_index_return_series_response(
        index_id="IDX_MSCI_WORLD_TR",
        request=REQUEST,
        rows=[_return(date(2026, 4, 10), quality_status="stale")],
        generated_at=GENERATED_AT,
    )

    assert response.completeness_status == "PARTIAL"
    assert response.record_count == 1
    assert response.data_quality_status == "PARTIAL"
    assert response.source_evidence_current is False
    assert response.request_fingerprint


def test_empty_price_window_is_explicitly_unavailable() -> None:
    response = build_index_price_series_response(
        index_id="IDX_MSCI_WORLD_TR", request=REQUEST, rows=[], generated_at=GENERATED_AT
    )

    assert response.completeness_status == "EMPTY"
    assert response.record_count == 0
    assert response.freshness_status == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_service_passes_window_to_typed_reader() -> None:
    class Reader:
        async def list_prices(self, **kwargs: object) -> list[IndexPriceEvidence]:
            self.price_kwargs = kwargs
            return [_price(date(2026, 4, 9)), _price(date(2026, 4, 10))]

        async def list_returns(self, **kwargs: object) -> list[IndexReturnEvidence]:
            self.return_kwargs = kwargs
            return [_return(date(2026, 4, 9)), _return(date(2026, 4, 10))]

    reader = Reader()
    service = IndexSeriesService(reader=reader, clock=lambda: GENERATED_AT)  # type: ignore[arg-type]

    await service.get_prices(index_id="IDX_MSCI_WORLD_TR", request=REQUEST)
    await service.get_returns(index_id="IDX_MSCI_WORLD_TR", request=REQUEST)

    expected = {
        "index_id": "IDX_MSCI_WORLD_TR",
        "start_date": date(2026, 4, 9),
        "end_date": date(2026, 4, 10),
    }
    assert reader.price_kwargs == expected
    assert reader.return_kwargs == expected
