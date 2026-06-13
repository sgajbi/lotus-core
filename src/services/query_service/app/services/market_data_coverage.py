from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..dtos.reference_integration_dto import (
    MarketDataCoverageRequest,
    MarketDataCoverageSupportability,
    MarketDataCoverageWindowResponse,
    MarketDataFxCoverageRecord,
    MarketDataPriceCoverageRecord,
)
from ..repositories.currency_codes import normalize_currency_code
from ..repositories.identifier_normalization import normalize_security_id
from .reference_data_helpers import latest_reference_evidence_timestamp
from .reference_data_mappers import (
    market_data_fx_coverage_record,
    market_data_price_coverage_record,
    missing_market_data_fx_coverage_record,
    missing_market_data_price_coverage_record,
)
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date


@dataclass(frozen=True)
class MarketDataCoverageReadScope:
    instrument_ids: list[str]
    unique_instrument_ids: list[str]
    valuation_currency: str | None
    fx_pairs: list[tuple[str, str]]
    unique_fx_pairs: list[tuple[str, str]]


@dataclass(frozen=True)
class _MarketDataCoverageRecords:
    price_coverage: list[MarketDataPriceCoverageRecord]
    fx_coverage: list[MarketDataFxCoverageRecord]
    missing_instrument_ids: list[str]
    stale_instrument_ids: list[str]
    missing_currency_pairs: list[str]
    stale_currency_pairs: list[str]


_MarketDataSupportabilityState = Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"]


def market_data_coverage_read_scope(
    request: MarketDataCoverageRequest,
) -> MarketDataCoverageReadScope:
    instrument_ids = [
        normalize_security_id(instrument_id) for instrument_id in request.instrument_ids
    ]
    fx_pairs = [(pair.from_currency, pair.to_currency) for pair in request.currency_pairs]
    valuation_currency = (
        normalize_currency_code(request.valuation_currency)
        if request.valuation_currency is not None
        else None
    )
    return MarketDataCoverageReadScope(
        instrument_ids=instrument_ids,
        unique_instrument_ids=list(dict.fromkeys(instrument_ids)),
        valuation_currency=valuation_currency,
        fx_pairs=fx_pairs,
        unique_fx_pairs=list(dict.fromkeys(fx_pairs)),
    )


async def resolve_market_data_coverage_response(
    *,
    repository: Any,
    request: MarketDataCoverageRequest,
) -> MarketDataCoverageWindowResponse:
    read_scope = market_data_coverage_read_scope(request)
    price_rows = await repository.list_latest_market_prices(
        security_ids=read_scope.unique_instrument_ids,
        as_of_date=request.as_of_date,
    )
    fx_rows = await repository.list_latest_fx_rates(
        currency_pairs=read_scope.unique_fx_pairs,
        as_of_date=request.as_of_date,
    )
    return build_market_data_coverage_response(
        request=request,
        read_scope=read_scope,
        price_rows=price_rows,
        fx_rows=fx_rows,
    )


def build_market_data_coverage_response(
    *,
    request: MarketDataCoverageRequest,
    read_scope: MarketDataCoverageReadScope,
    price_rows: list[Any],
    fx_rows: list[Any],
) -> MarketDataCoverageWindowResponse:
    coverage_records = _market_data_coverage_records(
        request=request,
        read_scope=read_scope,
        price_rows=price_rows,
        fx_rows=fx_rows,
    )
    supportability_state = _market_data_supportability_state(coverage_records)

    return MarketDataCoverageWindowResponse(
        as_of_date=request.as_of_date,
        valuation_currency=read_scope.valuation_currency,
        price_coverage=coverage_records.price_coverage,
        fx_coverage=coverage_records.fx_coverage,
        supportability=_market_data_supportability(
            read_scope=read_scope,
            coverage_records=coverage_records,
            state=supportability_state,
        ),
        lineage=_market_data_coverage_lineage(),
        **source_product_runtime_metadata_without_as_of_date(
            request.as_of_date,
            data_quality_status=_market_data_quality_status(supportability_state),
            latest_evidence_timestamp=latest_reference_evidence_timestamp(price_rows, fx_rows),
        ),
    )


def _market_data_coverage_records(
    *,
    request: MarketDataCoverageRequest,
    read_scope: MarketDataCoverageReadScope,
    price_rows: list[Any],
    fx_rows: list[Any],
) -> _MarketDataCoverageRecords:
    price_coverage, missing_instrument_ids, stale_instrument_ids = (
        _market_data_price_coverage_records(
            request=request,
            read_scope=read_scope,
            price_rows=price_rows,
        )
    )
    fx_coverage, missing_currency_pairs, stale_currency_pairs = _market_data_fx_coverage_records(
        request=request,
        read_scope=read_scope,
        fx_rows=fx_rows,
    )
    return _MarketDataCoverageRecords(
        price_coverage=price_coverage,
        fx_coverage=fx_coverage,
        missing_instrument_ids=missing_instrument_ids,
        stale_instrument_ids=stale_instrument_ids,
        missing_currency_pairs=missing_currency_pairs,
        stale_currency_pairs=stale_currency_pairs,
    )


def _market_data_price_coverage_records(
    *,
    request: MarketDataCoverageRequest,
    read_scope: MarketDataCoverageReadScope,
    price_rows: list[Any],
) -> tuple[list[MarketDataPriceCoverageRecord], list[str], list[str]]:
    price_by_instrument = {normalize_security_id(row.security_id): row for row in price_rows}
    price_coverage = []
    missing_instrument_ids: list[str] = []
    stale_instrument_ids: list[str] = []
    for instrument_id in read_scope.instrument_ids:
        row = price_by_instrument.get(instrument_id)
        if row is None:
            missing_instrument_ids.append(instrument_id)
            price_coverage.append(missing_market_data_price_coverage_record(instrument_id))
            continue

        coverage_record = market_data_price_coverage_record(
            row,
            instrument_id=instrument_id,
            as_of_date=request.as_of_date,
            max_staleness_days=request.max_staleness_days,
        )
        if coverage_record.quality_status == "STALE":
            stale_instrument_ids.append(instrument_id)
        price_coverage.append(coverage_record)
    return price_coverage, missing_instrument_ids, stale_instrument_ids


def _market_data_fx_coverage_records(
    *,
    request: MarketDataCoverageRequest,
    read_scope: MarketDataCoverageReadScope,
    fx_rows: list[Any],
) -> tuple[list[MarketDataFxCoverageRecord], list[str], list[str]]:
    fx_by_pair = {(row.from_currency, row.to_currency): row for row in fx_rows}
    fx_coverage = []
    missing_currency_pairs: list[str] = []
    stale_currency_pairs: list[str] = []
    for from_currency, to_currency in read_scope.fx_pairs:
        pair_label = f"{from_currency}/{to_currency}"
        row = fx_by_pair.get((from_currency, to_currency))
        if row is None:
            missing_currency_pairs.append(pair_label)
            fx_coverage.append(
                missing_market_data_fx_coverage_record(
                    from_currency=from_currency,
                    to_currency=to_currency,
                )
            )
            continue

        coverage_record = market_data_fx_coverage_record(
            row,
            from_currency=from_currency,
            to_currency=to_currency,
            as_of_date=request.as_of_date,
            max_staleness_days=request.max_staleness_days,
        )
        if coverage_record.quality_status == "STALE":
            stale_currency_pairs.append(pair_label)
        fx_coverage.append(coverage_record)
    return fx_coverage, missing_currency_pairs, stale_currency_pairs


def _market_data_supportability_state(
    coverage_records: _MarketDataCoverageRecords,
) -> _MarketDataSupportabilityState:
    if coverage_records.missing_instrument_ids or coverage_records.missing_currency_pairs:
        return "INCOMPLETE"
    if coverage_records.stale_instrument_ids or coverage_records.stale_currency_pairs:
        return "DEGRADED"
    return "READY"


def _market_data_supportability_reason(
    state: _MarketDataSupportabilityState,
) -> str:
    return {
        "READY": "MARKET_DATA_READY",
        "DEGRADED": "MARKET_DATA_STALE",
        "INCOMPLETE": "MARKET_DATA_MISSING",
        "UNAVAILABLE": "MARKET_DATA_MISSING",
    }[state]


def _market_data_supportability(
    *,
    read_scope: MarketDataCoverageReadScope,
    coverage_records: _MarketDataCoverageRecords,
    state: _MarketDataSupportabilityState,
) -> MarketDataCoverageSupportability:
    return MarketDataCoverageSupportability(
        state=state,
        reason=_market_data_supportability_reason(state),
        requested_price_count=len(read_scope.instrument_ids),
        resolved_price_count=sum(1 for record in coverage_records.price_coverage if record.found),
        requested_fx_count=len(read_scope.fx_pairs),
        resolved_fx_count=sum(1 for record in coverage_records.fx_coverage if record.found),
        missing_instrument_ids=coverage_records.missing_instrument_ids,
        stale_instrument_ids=coverage_records.stale_instrument_ids,
        missing_currency_pairs=coverage_records.missing_currency_pairs,
        stale_currency_pairs=coverage_records.stale_currency_pairs,
    )


def _market_data_quality_status(state: _MarketDataSupportabilityState) -> str:
    return "COMPLETE" if state == "READY" else "PARTIAL"


def _market_data_coverage_lineage() -> dict[str, str]:
    return {
        "source_system": "market_prices+fx_rates",
        "contract_version": "rfc_087_v1",
    }
