"""Pure request, paging, FX-context, and evidence-read policy for market windows."""

from dataclasses import dataclass
from typing import Any, Mapping

from portfolio_common.request_fingerprints import request_fingerprint

from ...contracts.benchmark_market_series import BenchmarkMarketSeriesRequest


@dataclass(frozen=True, slots=True)
class BenchmarkMarketSeriesRequestScope:
    """Stable request identity and cursor state for one component page."""

    request_fingerprint: str
    requested_fields: frozenset[str]
    page_size: int
    cursor_index_id: str | None


@dataclass(frozen=True, slots=True)
class BenchmarkMarketSeriesIndexPage:
    """One stable index-id page selected from an ordered candidate window."""

    index_ids: tuple[str, ...]
    has_more: bool


@dataclass(frozen=True, slots=True)
class BenchmarkMarketSeriesFxContext:
    """Required benchmark-to-target FX read and normalization status."""

    source_currency: str | None
    target_currency: str | None
    should_read_fx_rates: bool
    initial_normalization_status: str


@dataclass(frozen=True, slots=True)
class BenchmarkMarketSeriesEvidencePlan:
    """Conditional source reads required by the requested response fields."""

    include_index_prices: bool
    include_index_returns: bool
    include_benchmark_returns: bool
    include_fx_rates: bool

    def read_names(self) -> tuple[str, ...]:
        """Return source-read names in deterministic, session-safe order."""

        reads = ["components"]
        if self.include_index_prices:
            reads.append("index_prices")
        if self.include_index_returns:
            reads.append("index_returns")
        if self.include_benchmark_returns:
            reads.append("benchmark_returns")
        if self.include_fx_rates:
            reads.append("fx_rates")
        return tuple(reads)


def resolve_request_scope(
    *,
    benchmark_id: str,
    request: BenchmarkMarketSeriesRequest,
    cursor: Mapping[str, Any],
) -> BenchmarkMarketSeriesRequestScope:
    """Bind a decoded cursor to the exact market-series request identity."""

    fingerprint = request_fingerprint(
        {
            "benchmark_id": benchmark_id,
            "as_of_date": request.as_of_date.isoformat(),
            "window": request.window.model_dump(mode="json"),
            "frequency": request.frequency,
            "target_currency": request.target_currency,
            "series_fields": sorted(request.series_fields),
            "page_size": request.page.page_size,
        }
    )
    token_scope = cursor.get("scope_fingerprint")
    if token_scope and token_scope != fingerprint:
        raise ValueError("Benchmark market series page token does not match request scope.")
    return BenchmarkMarketSeriesRequestScope(
        request_fingerprint=fingerprint,
        requested_fields=frozenset(request.series_fields),
        page_size=request.page.page_size,
        cursor_index_id=cursor.get("last_index_id"),
    )


def select_index_page(
    *, candidate_index_ids: list[str], page_size: int
) -> BenchmarkMarketSeriesIndexPage:
    """Select one page from already ordered index identifiers."""

    return BenchmarkMarketSeriesIndexPage(
        index_ids=tuple(candidate_index_ids[:page_size]),
        has_more=len(candidate_index_ids) > page_size,
    )


def next_page_token_payload(
    *, request_scope: BenchmarkMarketSeriesRequestScope, index_page: BenchmarkMarketSeriesIndexPage
) -> dict[str, str] | None:
    """Build the stable cursor payload without coupling policy to token encoding."""

    if not index_page.has_more or not index_page.index_ids:
        return None
    return {
        "scope_fingerprint": request_scope.request_fingerprint,
        "last_index_id": index_page.index_ids[-1],
    }


def resolve_fx_context(
    *,
    benchmark_currency: str,
    target_currency: str | None,
    requested_fields: frozenset[str],
) -> BenchmarkMarketSeriesFxContext:
    """Determine whether benchmark-to-target FX context must be read."""

    if target_currency is None:
        return BenchmarkMarketSeriesFxContext(
            source_currency=None,
            target_currency=None,
            should_read_fx_rates=False,
            initial_normalization_status="native_component_series_only",
        )
    if benchmark_currency != target_currency and "fx_rate" in requested_fields:
        return BenchmarkMarketSeriesFxContext(
            source_currency=benchmark_currency,
            target_currency=target_currency,
            should_read_fx_rates=True,
            initial_normalization_status="native_component_series_only",
        )
    status = (
        "native_component_series_with_identity_benchmark_to_target_fx_context"
        if benchmark_currency == target_currency
        else "native_component_series_without_fx_context_request"
    )
    return BenchmarkMarketSeriesFxContext(
        source_currency=benchmark_currency,
        target_currency=target_currency,
        should_read_fx_rates=False,
        initial_normalization_status=status,
    )


def build_evidence_plan(
    *, requested_fields: frozenset[str], fx_context: BenchmarkMarketSeriesFxContext
) -> BenchmarkMarketSeriesEvidencePlan:
    """Map public response fields to the minimum required source reads."""

    return BenchmarkMarketSeriesEvidencePlan(
        include_index_prices="index_price" in requested_fields,
        include_index_returns="index_return" in requested_fields,
        include_benchmark_returns="benchmark_return" in requested_fields,
        include_fx_rates=fx_context.should_read_fx_rates,
    )
