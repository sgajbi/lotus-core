"""Application use case for governed index price and return series windows."""

from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import date, datetime
from typing import Literal, TypeVar

from portfolio_common.request_fingerprints import series_request_fingerprint
from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..contracts.index_series import (
    IndexPriceSeriesPoint,
    IndexPriceSeriesResponse,
    IndexReturnSeriesPoint,
    IndexReturnSeriesResponse,
    IndexSeriesRequest,
)
from ..domain.index_series import IndexPriceEvidence, IndexReturnEvidence
from ..ports.index_series import IndexSeriesReader
from .source_evidence import latest_evidence_timestamp

SeriesCompleteness = Literal["COMPLETE", "PARTIAL", "EMPTY"]
SeriesEvidence = TypeVar("SeriesEvidence", IndexPriceEvidence, IndexReturnEvidence)


class IndexSeriesService:
    """Resolve canonical index series through a persistence-independent read port."""

    def __init__(self, *, reader: IndexSeriesReader, clock: Callable[[], datetime]) -> None:
        self._reader = reader
        self._clock = clock

    async def get_prices(
        self, *, index_id: str, request: IndexSeriesRequest
    ) -> IndexPriceSeriesResponse:
        rows = await self._reader.list_prices(
            index_id=index_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return build_index_price_series_response(
            index_id=index_id, request=request, rows=rows, generated_at=self._clock()
        )

    async def get_returns(
        self, *, index_id: str, request: IndexSeriesRequest
    ) -> IndexReturnSeriesResponse:
        rows = await self._reader.list_returns(
            index_id=index_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return build_index_return_series_response(
            index_id=index_id, request=request, rows=rows, generated_at=self._clock()
        )


def build_index_price_series_response(
    *,
    index_id: str,
    request: IndexSeriesRequest,
    rows: list[IndexPriceEvidence],
    generated_at: datetime,
) -> IndexPriceSeriesResponse:
    """Build a price window with deterministic source proof."""

    metadata = _series_metadata(
        series_kind="index_price_series",
        index_id=index_id,
        request=request,
        rows=rows,
        generated_at=generated_at,
    )
    return IndexPriceSeriesResponse(
        index_id=index_id,
        resolved_window=request.window,
        frequency=request.frequency,
        points=[
            IndexPriceSeriesPoint(
                series_date=row.series_date,
                index_price=row.index_price,
                series_currency=row.series_currency,
                value_convention=row.value_convention,
                quality_status=row.quality_status,
            )
            for row in rows
        ],
        lineage=_compatibility_lineage("index_price_series"),
        **metadata,
    )


def build_index_return_series_response(
    *,
    index_id: str,
    request: IndexSeriesRequest,
    rows: list[IndexReturnEvidence],
    generated_at: datetime,
) -> IndexReturnSeriesResponse:
    """Build a return window with deterministic source proof."""

    metadata = _series_metadata(
        series_kind="index_return_series",
        index_id=index_id,
        request=request,
        rows=rows,
        generated_at=generated_at,
    )
    return IndexReturnSeriesResponse(
        index_id=index_id,
        resolved_window=request.window,
        frequency=request.frequency,
        points=[
            IndexReturnSeriesPoint(
                series_date=row.series_date,
                index_return=row.index_return,
                return_period=row.return_period,
                return_convention=row.return_convention,
                series_currency=row.series_currency,
                quality_status=row.quality_status,
            )
            for row in rows
        ],
        lineage=_compatibility_lineage("index_return_series"),
        **metadata,
    )


def _series_metadata(
    *,
    series_kind: str,
    index_id: str,
    request: IndexSeriesRequest,
    rows: Sequence[SeriesEvidence],
    generated_at: datetime,
) -> dict[str, object]:
    completeness = _completeness(
        rows,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
    )
    latest_evidence = latest_evidence_timestamp(rows)
    request_fingerprint = series_request_fingerprint(
        series_key=series_kind,
        identifier_key="index_id",
        identifier_value=index_id,
        request=request,
    )
    content_hash = stable_content_hash(
        {
            "product_name": "IndexSeriesWindow",
            "product_version": "v1",
            "series_kind": series_kind,
            "index_id": index_id,
            "request": request.model_dump(mode="json"),
            "records": [asdict(row) for row in rows],
            "completeness_status": completeness,
            "latest_evidence_timestamp": latest_evidence,
        }
    )
    current = completeness == "COMPLETE" and latest_evidence is not None
    runtime = source_data_product_runtime_metadata(
        generated_at=generated_at,
        as_of_date=request.as_of_date,
        data_quality_status=(
            "COMPLETE" if completeness == "COMPLETE" else "EMPTY" if not rows else "PARTIAL"
        ),
        latest_evidence_timestamp=latest_evidence,
        content_hash=content_hash,
        source_refs=[
            "lotus-core://source/IndexSeriesWindow/"
            f"{series_kind}/{index_id}/{request.window.start_date.isoformat()}/"
            f"{request.window.end_date.isoformat()}"
        ],
        lineage={
            "source_owner": "lotus-core",
            "source_product": "IndexSeriesWindow",
            "series_kind": series_kind,
        },
        source_evidence_current=current,
        freshness_status="CURRENT" if current else "UNAVAILABLE" if not rows else "PARTIAL",
        use_content_hash_as_source_batch_fingerprint=True,
    )
    return {
        "request_fingerprint": request_fingerprint,
        "record_count": len(rows),
        "completeness_status": completeness,
        **runtime,
    }


def _completeness(
    rows: Sequence[SeriesEvidence], *, start_date: date, end_date: date
) -> SeriesCompleteness:
    if not rows:
        return "EMPTY"
    accepted = all(row.quality_status.strip().upper() in {"ACCEPTED", "COMPLETE"} for row in rows)
    one_currency = len({row.series_currency.strip().upper() for row in rows}) == 1
    covers_boundaries = rows[0].series_date == start_date and rows[-1].series_date == end_date
    return "COMPLETE" if accepted and one_currency and covers_boundaries else "PARTIAL"


def _compatibility_lineage(series_kind: str) -> dict[str, str]:
    return {
        "contract_version": "rfc_062_v1",
        "source_system": "lotus-core-query-control-plane",
        "generated_by": f"integration.{series_kind}",
    }
