"""Response orchestration for typed benchmark market-series evidence."""

from datetime import datetime

from portfolio_common.reference_data_paging import ReferencePageMetadata
from portfolio_common.source_data_product_metadata import source_data_product_runtime_metadata

from ...contracts.benchmark_market_series import (
    BenchmarkMarketSeriesRequest,
    BenchmarkMarketSeriesResponse,
)
from ...domain.benchmark_definition import (
    BenchmarkComponentEvidence,
    BenchmarkDefinitionEvidence,
)
from ...domain.benchmark_return_series import BenchmarkReturnEvidence
from ...domain.index_series import IndexPriceEvidence, IndexReturnEvidence
from ...domain.market_fx import FxRateEvidence
from ..benchmark_component_segments import resolve_benchmark_component_segments
from .points import build_component_series, normalization_status, quality_status_summary
from .policy import BenchmarkMarketSeriesFxContext
from .proof import content_hash, data_quality_status, latest_evidence_timestamp, source_refs


def build_benchmark_market_series_response(
    *,
    benchmark_id: str,
    request: BenchmarkMarketSeriesRequest,
    definition: BenchmarkDefinitionEvidence | None,
    request_fingerprint: str,
    page_size: int,
    has_more: bool,
    next_page_token: str | None,
    index_ids: tuple[str, ...],
    components: list[BenchmarkComponentEvidence],
    index_prices: list[IndexPriceEvidence],
    index_returns: list[IndexReturnEvidence],
    benchmark_returns: list[BenchmarkReturnEvidence],
    fx_rates: list[FxRateEvidence],
    fx_context: BenchmarkMarketSeriesFxContext,
    generated_at: datetime,
) -> BenchmarkMarketSeriesResponse:
    """Assemble one deterministic page from persistence-independent source evidence."""

    benchmark_currency = (
        definition.benchmark_currency
        if definition is not None
        else request.target_currency or "UNKNOWN"
    )
    resolved_components = resolve_benchmark_component_segments(
        components,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
    )
    component_series = build_component_series(
        index_ids=index_ids,
        request=request,
        components=resolved_components,
        index_prices=index_prices,
        index_returns=index_returns,
        benchmark_returns=benchmark_returns,
        fx_rates=fx_rates,
        fx_context=fx_context,
    )
    resolved_quality = data_quality_status(
        definition=definition,
        index_ids=index_ids,
        requested_fields=frozenset(request.series_fields),
        components=resolved_components,
        index_prices=index_prices,
        index_returns=index_returns,
        benchmark_returns=benchmark_returns,
        fx_rates=fx_rates,
        fx_context=fx_context,
        has_more=has_more,
    )
    latest_evidence = latest_evidence_timestamp(
        definition=definition,
        components=resolved_components,
        index_prices=index_prices,
        index_returns=index_returns,
        benchmark_returns=benchmark_returns,
        fx_rates=fx_rates,
    )
    current = resolved_quality == "COMPLETE" and latest_evidence is not None
    digest = content_hash(
        benchmark_id=benchmark_id,
        request=request,
        definition=definition,
        request_fingerprint=request_fingerprint,
        index_ids=index_ids,
        has_more=has_more,
        components=resolved_components,
        index_prices=index_prices,
        index_returns=index_returns,
        benchmark_returns=benchmark_returns,
        fx_rates=fx_rates,
        resolved_data_quality_status=resolved_quality,
        latest_evidence=latest_evidence,
    )
    metadata = source_data_product_runtime_metadata(
        generated_at=generated_at,
        as_of_date=request.as_of_date,
        data_quality_status=resolved_quality,
        latest_evidence_timestamp=latest_evidence,
        content_hash=digest,
        source_refs=source_refs(
            benchmark_id=benchmark_id,
            request=request,
            index_ids=index_ids,
            fx_context=fx_context,
        ),
        lineage={
            "source_owner": "lotus-core",
            "source_product": "MarketDataWindow",
            "benchmark_id": benchmark_id,
            "request_fingerprint": request_fingerprint,
            "contract_version": "rfc_062_v1",
        },
        source_evidence_current=current,
        freshness_status=(
            "CURRENT"
            if current
            else "UNAVAILABLE"
            if resolved_quality == "EMPTY"
            else "PARTIAL"
        ),
        use_content_hash_as_source_batch_fingerprint=True,
    )
    return BenchmarkMarketSeriesResponse(
        benchmark_id=benchmark_id,
        benchmark_currency=benchmark_currency,
        target_currency=request.target_currency,
        resolved_window=request.window,
        frequency=request.frequency,
        component_series=component_series,
        quality_status_summary=quality_status_summary(component_series),
        fx_context_source_currency=fx_context.source_currency,
        fx_context_target_currency=fx_context.target_currency,
        normalization_policy="native_component_series_downstream_normalization_required",
        normalization_status=normalization_status(fx_context=fx_context, fx_rates=fx_rates),
        component_metadata_policy="targeted_index_catalog_lookup_required_for_component_metadata",
        request_fingerprint=request_fingerprint,
        page=ReferencePageMetadata(
            page_size=page_size,
            sort_key="index_id:asc",
            returned_component_count=len(component_series),
            request_scope_fingerprint=request_fingerprint,
            next_page_token=next_page_token,
        ),
        lineage={
            "contract_version": "rfc_062_v1",
            "source_system": "lotus-core-query-control-plane",
            "generated_by": "integration.market_series",
        },
        **metadata,
    )
