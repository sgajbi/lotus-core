"""Application tests for governed benchmark return series windows."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.services.query_control_plane_service.app.application.benchmark_return_series import (
    BenchmarkReturnSeriesService,
    build_benchmark_return_series_response,
)
from src.services.query_control_plane_service.app.contracts.benchmark_return_series import (
    BenchmarkReturnSeriesRequest,
    IntegrationWindow,
)
from src.services.query_control_plane_service.app.domain.benchmark_return_series import (
    BenchmarkReturnEvidence,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)
REQUEST = BenchmarkReturnSeriesRequest(
    as_of_date=date(2026, 4, 10),
    window=IntegrationWindow(start_date=date(2026, 4, 9), end_date=date(2026, 4, 10)),
    frequency="daily",
)


def _return(series_date: date, *, quality_status: str = "accepted") -> BenchmarkReturnEvidence:
    return BenchmarkReturnEvidence(
        series_id="vendor-benchmark-return",
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        series_date=series_date,
        benchmark_return=Decimal("0.0019"),
        return_period="1d",
        return_convention="total_return_index",
        series_currency="USD",
        quality_status=quality_status,
        observed_at=EVIDENCE_AT,
        source_vendor="provider",
        source_record_id=f"return:{series_date.isoformat()}",
        created_at=EVIDENCE_AT,
        updated_at=EVIDENCE_AT,
    )


def test_complete_window_is_current_and_deterministic() -> None:
    rows = [_return(date(2026, 4, 9)), _return(date(2026, 4, 10))]

    first = build_benchmark_return_series_response(
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        request=REQUEST,
        rows=rows,
        generated_at=GENERATED_AT,
    )
    second = build_benchmark_return_series_response(
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        request=REQUEST,
        rows=rows,
        generated_at=datetime(2026, 4, 10, 13, tzinfo=UTC),
    )

    assert first.product_name == "BenchmarkReturnSeriesWindow"
    assert first.completeness_status == "COMPLETE"
    assert first.source_evidence_current is True
    assert first.source_batch_fingerprint == first.content_hash == first.source_digest
    assert first.content_hash == second.content_hash
    assert first.points[0].benchmark_return == Decimal("0.0019")


def test_stale_partial_window_is_not_current() -> None:
    response = build_benchmark_return_series_response(
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        request=REQUEST,
        rows=[_return(date(2026, 4, 10), quality_status="stale")],
        generated_at=GENERATED_AT,
    )

    assert response.completeness_status == "PARTIAL"
    assert response.data_quality_status == "PARTIAL"
    assert response.source_evidence_current is False


@pytest.mark.asyncio
async def test_service_passes_window_to_reader() -> None:
    class Reader:
        async def list_returns(self, **kwargs: object) -> list[BenchmarkReturnEvidence]:
            self.kwargs = kwargs
            return [_return(date(2026, 4, 9)), _return(date(2026, 4, 10))]

    reader = Reader()
    response = await BenchmarkReturnSeriesService(
        reader=reader,  # type: ignore[arg-type]
        clock=lambda: GENERATED_AT,
    ).get(benchmark_id="BMK_GLOBAL_BALANCED_60_40", request=REQUEST)

    assert response.record_count == 2
    assert reader.kwargs == {
        "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
        "start_date": date(2026, 4, 9),
        "end_date": date(2026, 4, 10),
    }
