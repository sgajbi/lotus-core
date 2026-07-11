"""Quality, freshness, lineage, and deterministic proof for benchmark market windows."""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import cast

from portfolio_common.source_data_product_metadata import stable_content_hash

from ...contracts.benchmark_market_series import BenchmarkMarketSeriesRequest
from ...domain.benchmark_definition import (
    BenchmarkComponentEvidence,
    BenchmarkDefinitionEvidence,
)
from ...domain.benchmark_return_series import BenchmarkReturnEvidence
from ...domain.index_series import IndexPriceEvidence, IndexReturnEvidence
from ...domain.market_fx import FxRateEvidence
from .policy import BenchmarkMarketSeriesFxContext

ACCEPTED_QUALITY_STATUSES = frozenset({"ACCEPTED", "COMPLETE"})


def data_quality_status(
    *,
    definition: BenchmarkDefinitionEvidence | None,
    index_ids: tuple[str, ...],
    requested_fields: frozenset[str],
    components: list[BenchmarkComponentEvidence],
    index_prices: list[IndexPriceEvidence],
    index_returns: list[IndexReturnEvidence],
    benchmark_returns: list[BenchmarkReturnEvidence],
    fx_rates: list[FxRateEvidence],
    fx_context: BenchmarkMarketSeriesFxContext,
    has_more: bool,
) -> str:
    """Classify page evidence without overstating incomplete or unavailable data."""

    if not index_ids:
        return "EMPTY"
    quality_statuses = [row.quality_status for row in components]
    quality_statuses.extend(row.quality_status for row in index_prices)
    quality_statuses.extend(row.quality_status for row in index_returns)
    quality_statuses.extend(row.quality_status for row in benchmark_returns)
    if definition is not None:
        quality_statuses.append(definition.quality_status)
    evidence_complete = definition is not None and _requested_evidence_present(
        index_ids=index_ids,
        requested_fields=requested_fields,
        components=components,
        index_prices=index_prices,
        index_returns=index_returns,
        benchmark_returns=benchmark_returns,
        fx_rates=fx_rates,
        fx_context=fx_context,
    )
    accepted = bool(quality_statuses) and all(
        status.strip().upper() in ACCEPTED_QUALITY_STATUSES for status in quality_statuses
    )
    return "COMPLETE" if evidence_complete and accepted and not has_more else "PARTIAL"


def latest_evidence_timestamp(
    *,
    definition: BenchmarkDefinitionEvidence | None,
    components: list[BenchmarkComponentEvidence],
    index_prices: list[IndexPriceEvidence],
    index_returns: list[IndexReturnEvidence],
    benchmark_returns: list[BenchmarkReturnEvidence],
    fx_rates: list[FxRateEvidence],
) -> datetime | None:
    """Return the latest timestamp from every typed source family used by the page."""

    timestamps: list[datetime] = []
    if definition is not None:
        timestamps.extend(
            timestamp
            for timestamp in (
                definition.source_timestamp,
                definition.updated_at,
                definition.created_at,
            )
            if timestamp is not None
        )
    for row in components:
        timestamps.extend(
            timestamp
            for timestamp in (row.source_timestamp, row.updated_at, row.created_at)
            if timestamp is not None
        )
    for row in [*index_prices, *index_returns, *benchmark_returns]:
        timestamps.extend(
            timestamp
            for timestamp in (row.observed_at, row.updated_at, row.created_at)
            if timestamp is not None
        )
    for row in fx_rates:
        timestamps.extend(
            timestamp for timestamp in (row.updated_at, row.created_at) if timestamp is not None
        )
    normalized = [_as_utc(timestamp) for timestamp in timestamps]
    return max(normalized) if normalized else None


def content_hash(
    *,
    benchmark_id: str,
    request: BenchmarkMarketSeriesRequest,
    definition: BenchmarkDefinitionEvidence | None,
    request_fingerprint: str,
    index_ids: tuple[str, ...],
    has_more: bool,
    components: list[BenchmarkComponentEvidence],
    index_prices: list[IndexPriceEvidence],
    index_returns: list[IndexReturnEvidence],
    benchmark_returns: list[BenchmarkReturnEvidence],
    fx_rates: list[FxRateEvidence],
    resolved_data_quality_status: str,
    latest_evidence: datetime | None,
) -> str:
    """Hash stable request, page, source evidence, and quality state."""

    return cast(
        str,
        stable_content_hash(
            {
                "product_name": "MarketDataWindow",
                "product_version": "v1",
                "benchmark_id": benchmark_id,
                "request": {
                    "as_of_date": request.as_of_date,
                    "window": request.window.model_dump(mode="json"),
                    "frequency": request.frequency,
                    "target_currency": request.target_currency,
                    "series_fields": sorted(request.series_fields),
                    "page_size": request.page.page_size,
                },
                "request_fingerprint": request_fingerprint,
                "page": {"index_ids": index_ids, "has_more": has_more},
                "definition": asdict(definition) if definition is not None else None,
                "components": [asdict(row) for row in _sorted_components(components)],
                "index_prices": [asdict(row) for row in _sorted_prices(index_prices)],
                "index_returns": [asdict(row) for row in _sorted_index_returns(index_returns)],
                "benchmark_returns": [
                    asdict(row)
                    for row in sorted(benchmark_returns, key=lambda row: row.series_date)
                ],
                "fx_rates": [
                    asdict(row) for row in sorted(fx_rates, key=lambda row: row.rate_date)
                ],
                "data_quality_status": resolved_data_quality_status,
                "latest_evidence_timestamp": latest_evidence,
            }
        ),
    )


def source_refs(
    *,
    benchmark_id: str,
    request: BenchmarkMarketSeriesRequest,
    index_ids: tuple[str, ...],
    fx_context: BenchmarkMarketSeriesFxContext,
) -> list[str]:
    """Return deterministic authoritative source-product references for the page."""

    window = f"{request.window.start_date.isoformat()}/{request.window.end_date.isoformat()}"
    refs = {
        f"lotus-core://source/BenchmarkDefinition/{benchmark_id}/{request.as_of_date.isoformat()}",
        f"lotus-core://source/BenchmarkConstituentWindow/{benchmark_id}/{window}",
        f"lotus-core://source/MarketDataWindow/{benchmark_id}/{window}",
    }
    refs.update(
        f"lotus-core://source/IndexSeriesWindow/{index_id}/{window}" for index_id in index_ids
    )
    if "benchmark_return" in request.series_fields:
        refs.add(f"lotus-core://source/BenchmarkReturnSeriesWindow/{benchmark_id}/{window}")
    if fx_context.should_read_fx_rates:
        refs.add(
            "lotus-core://source/FxRateWindow/"
            f"{fx_context.source_currency}/{fx_context.target_currency}/{window}"
        )
    return sorted(refs)


def _requested_evidence_present(
    *,
    index_ids: tuple[str, ...],
    requested_fields: frozenset[str],
    components: list[BenchmarkComponentEvidence],
    index_prices: list[IndexPriceEvidence],
    index_returns: list[IndexReturnEvidence],
    benchmark_returns: list[BenchmarkReturnEvidence],
    fx_rates: list[FxRateEvidence],
    fx_context: BenchmarkMarketSeriesFxContext,
) -> bool:
    expected_ids = set(index_ids)
    checks = [expected_ids <= {row.index_id for row in components}]
    if "index_price" in requested_fields:
        checks.append(expected_ids <= {row.index_id for row in index_prices})
    if "index_return" in requested_fields:
        checks.append(expected_ids <= {row.index_id for row in index_returns})
    if "benchmark_return" in requested_fields:
        checks.append(bool(benchmark_returns))
    if "fx_rate" in requested_fields and fx_context.should_read_fx_rates:
        checks.append(bool(fx_rates))
    return all(checks)


def _sorted_components(
    rows: list[BenchmarkComponentEvidence],
) -> list[BenchmarkComponentEvidence]:
    return sorted(rows, key=lambda row: (row.index_id, row.composition_effective_from))


def _sorted_prices(rows: list[IndexPriceEvidence]) -> list[IndexPriceEvidence]:
    return sorted(rows, key=lambda row: (row.index_id, row.series_date, row.series_id))


def _sorted_index_returns(rows: list[IndexReturnEvidence]) -> list[IndexReturnEvidence]:
    return sorted(rows, key=lambda row: (row.index_id, row.series_date, row.series_id))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
