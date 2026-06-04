from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..dtos.reference_integration_dto import (
    MarketDataCoverageRequest,
    MarketDataCoverageSupportability,
    MarketDataCoverageWindowResponse,
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
    price_by_instrument = {normalize_security_id(row.security_id): row for row in price_rows}
    fx_by_pair = {(row.from_currency, row.to_currency): row for row in fx_rows}

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

    supportability_state: Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"] = "READY"
    supportability_reason = "MARKET_DATA_READY"
    if missing_instrument_ids or missing_currency_pairs:
        supportability_state = "INCOMPLETE"
        supportability_reason = "MARKET_DATA_MISSING"
    elif stale_instrument_ids or stale_currency_pairs:
        supportability_state = "DEGRADED"
        supportability_reason = "MARKET_DATA_STALE"

    return MarketDataCoverageWindowResponse(
        as_of_date=request.as_of_date,
        valuation_currency=read_scope.valuation_currency,
        price_coverage=price_coverage,
        fx_coverage=fx_coverage,
        supportability=MarketDataCoverageSupportability(
            state=supportability_state,
            reason=supportability_reason,
            requested_price_count=len(read_scope.instrument_ids),
            resolved_price_count=sum(1 for record in price_coverage if record.found),
            requested_fx_count=len(read_scope.fx_pairs),
            resolved_fx_count=sum(1 for record in fx_coverage if record.found),
            missing_instrument_ids=missing_instrument_ids,
            stale_instrument_ids=stale_instrument_ids,
            missing_currency_pairs=missing_currency_pairs,
            stale_currency_pairs=stale_currency_pairs,
        ),
        lineage={
            "source_system": "market_prices+fx_rates",
            "contract_version": "rfc_087_v1",
        },
        **source_product_runtime_metadata_without_as_of_date(
            request.as_of_date,
            data_quality_status=("COMPLETE" if supportability_state == "READY" else "PARTIAL"),
            latest_evidence_timestamp=latest_reference_evidence_timestamp(price_rows, fx_rows),
        ),
    )
