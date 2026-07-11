"""Application policy for DPM price and FX coverage evidence."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from portfolio_common.currency_codes import normalize_currency_code

from ...contracts.market_data_coverage import (
    MarketDataCoverageRequest,
    MarketDataCoverageSupportability,
    MarketDataCoverageWindowResponse,
    MarketDataFxCoverageRecord,
    MarketDataPriceCoverageRecord,
)
from ...domain.dpm_source_readiness import FxRateEvidence, MarketPriceEvidence
from ...ports.dpm_source_readiness import DpmReferenceDataReader
from .metadata import dpm_source_runtime_metadata

MarketDataSupportabilityState = Literal["READY", "DEGRADED", "INCOMPLETE", "UNAVAILABLE"]


@dataclass(frozen=True, slots=True)
class MarketDataCoverageScope:
    """Normalized response order and deduplicated persistence read scope."""

    instrument_ids: tuple[str, ...]
    unique_instrument_ids: tuple[str, ...]
    valuation_currency: str | None
    fx_pairs: tuple[tuple[str, str], ...]
    unique_fx_pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class MarketDataCoverageRecords:
    """Mapped coverage records and supportability diagnostics."""

    prices: tuple[MarketDataPriceCoverageRecord, ...]
    fx_rates: tuple[MarketDataFxCoverageRecord, ...]
    missing_instrument_ids: tuple[str, ...]
    stale_instrument_ids: tuple[str, ...]
    missing_currency_pairs: tuple[str, ...]
    stale_currency_pairs: tuple[str, ...]


@dataclass(slots=True)
class MarketDataCoverageService:
    """Resolve latest market observations and assess DPM valuation coverage."""

    reader: DpmReferenceDataReader
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def resolve(self, request: MarketDataCoverageRequest) -> MarketDataCoverageWindowResponse:
        scope = market_data_coverage_scope(request)
        prices = await self.reader.list_latest_market_prices(
            security_ids=list(scope.unique_instrument_ids),
            as_of_date=request.as_of_date,
        )
        fx_rates = await self.reader.list_latest_fx_rates(
            currency_pairs=list(scope.unique_fx_pairs),
            as_of_date=request.as_of_date,
        )
        return build_market_data_coverage_response(
            request=request,
            scope=scope,
            prices=prices,
            fx_rates=fx_rates,
            generated_at=self.clock(),
        )


def market_data_coverage_scope(request: MarketDataCoverageRequest) -> MarketDataCoverageScope:
    """Normalize identifiers while preserving requested response order."""

    instrument_ids = tuple(value.strip() for value in request.instrument_ids)
    fx_pairs = tuple(
        (normalize_currency_code(pair.from_currency), normalize_currency_code(pair.to_currency))
        for pair in request.currency_pairs
    )
    valuation_currency = (
        normalize_currency_code(request.valuation_currency)
        if request.valuation_currency is not None
        else None
    )
    return MarketDataCoverageScope(
        instrument_ids=instrument_ids,
        unique_instrument_ids=tuple(dict.fromkeys(instrument_ids)),
        valuation_currency=valuation_currency,
        fx_pairs=fx_pairs,
        unique_fx_pairs=tuple(dict.fromkeys(fx_pairs)),
    )


def build_market_data_coverage_response(
    *,
    request: MarketDataCoverageRequest,
    scope: MarketDataCoverageScope,
    prices: list[MarketPriceEvidence],
    fx_rates: list[FxRateEvidence],
    generated_at: datetime,
) -> MarketDataCoverageWindowResponse:
    """Map latest observations and derive missing/stale supportability."""

    records = _coverage_records(
        request=request,
        scope=scope,
        prices=prices,
        fx_rates=fx_rates,
    )
    state = _supportability_state(records)
    supportability = MarketDataCoverageSupportability(
        state=state,
        reason={
            "READY": "MARKET_DATA_READY",
            "DEGRADED": "MARKET_DATA_STALE",
            "INCOMPLETE": "MARKET_DATA_MISSING",
            "UNAVAILABLE": "MARKET_DATA_MISSING",
        }[state],
        requested_price_count=len(scope.instrument_ids),
        resolved_price_count=sum(record.found for record in records.prices),
        requested_fx_count=len(scope.fx_pairs),
        resolved_fx_count=sum(record.found for record in records.fx_rates),
        missing_instrument_ids=list(records.missing_instrument_ids),
        stale_instrument_ids=list(records.stale_instrument_ids),
        missing_currency_pairs=list(records.missing_currency_pairs),
        stale_currency_pairs=list(records.stale_currency_pairs),
    )
    lineage = {
        "source_system": "market_prices+fx_rates",
        "contract_version": "rfc_087_v1",
    }
    content_payload = {
        "as_of_date": request.as_of_date,
        "valuation_currency": scope.valuation_currency,
        "price_coverage": [record.model_dump(mode="json") for record in records.prices],
        "fx_coverage": [record.model_dump(mode="json") for record in records.fx_rates],
        "supportability": supportability.model_dump(mode="json"),
        "lineage": lineage,
    }
    return MarketDataCoverageWindowResponse(
        valuation_currency=scope.valuation_currency,
        price_coverage=list(records.prices),
        fx_coverage=list(records.fx_rates),
        supportability=supportability,
        lineage=lineage,
        **dpm_source_runtime_metadata(
            product_name="MarketDataCoverageWindow",
            source_key="market-data",
            as_of_date=request.as_of_date,
            generated_at=generated_at,
            tenant_id=request.tenant_id,
            data_quality_status="COMPLETE" if state == "READY" else "PARTIAL",
            latest_evidence_timestamp=_latest_evidence_timestamp(prices, fx_rates),
            content_payload=content_payload,
            lineage=lineage,
        ),
    )


def _coverage_records(
    *,
    request: MarketDataCoverageRequest,
    scope: MarketDataCoverageScope,
    prices: list[MarketPriceEvidence],
    fx_rates: list[FxRateEvidence],
) -> MarketDataCoverageRecords:
    price_by_id = {row.security_id.strip(): row for row in prices}
    price_records: list[MarketDataPriceCoverageRecord] = []
    missing_instruments: list[str] = []
    stale_instruments: list[str] = []
    for instrument_id in scope.instrument_ids:
        evidence = price_by_id.get(instrument_id)
        if evidence is None:
            missing_instruments.append(instrument_id)
            price_records.append(
                MarketDataPriceCoverageRecord(
                    instrument_id=instrument_id,
                    found=False,
                    quality_status="MISSING",
                )
            )
            continue
        age_days = (request.as_of_date - evidence.price_date).days
        quality_status = "STALE" if age_days > request.max_staleness_days else "READY"
        if quality_status == "STALE":
            stale_instruments.append(instrument_id)
        price_records.append(
            MarketDataPriceCoverageRecord(
                instrument_id=instrument_id,
                found=True,
                price_date=evidence.price_date,
                price=evidence.price,
                currency=evidence.currency,
                age_days=age_days,
                quality_status=quality_status,
            )
        )

    fx_by_pair = {(row.from_currency, row.to_currency): row for row in fx_rates}
    fx_records: list[MarketDataFxCoverageRecord] = []
    missing_pairs: list[str] = []
    stale_pairs: list[str] = []
    for from_currency, to_currency in scope.fx_pairs:
        pair_label = f"{from_currency}/{to_currency}"
        evidence = fx_by_pair.get((from_currency, to_currency))
        if evidence is None:
            missing_pairs.append(pair_label)
            fx_records.append(
                MarketDataFxCoverageRecord(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    found=False,
                    quality_status="MISSING",
                )
            )
            continue
        age_days = (request.as_of_date - evidence.rate_date).days
        quality_status = "STALE" if age_days > request.max_staleness_days else "READY"
        if quality_status == "STALE":
            stale_pairs.append(pair_label)
        fx_records.append(
            MarketDataFxCoverageRecord(
                from_currency=from_currency,
                to_currency=to_currency,
                found=True,
                rate_date=evidence.rate_date,
                rate=evidence.rate,
                age_days=age_days,
                quality_status=quality_status,
            )
        )
    return MarketDataCoverageRecords(
        prices=tuple(price_records),
        fx_rates=tuple(fx_records),
        missing_instrument_ids=tuple(missing_instruments),
        stale_instrument_ids=tuple(stale_instruments),
        missing_currency_pairs=tuple(missing_pairs),
        stale_currency_pairs=tuple(stale_pairs),
    )


def _supportability_state(records: MarketDataCoverageRecords) -> MarketDataSupportabilityState:
    if records.missing_instrument_ids or records.missing_currency_pairs:
        return "INCOMPLETE"
    if records.stale_instrument_ids or records.stale_currency_pairs:
        return "DEGRADED"
    return "READY"


def _latest_evidence_timestamp(
    prices: list[MarketPriceEvidence],
    fx_rates: list[FxRateEvidence],
) -> datetime | None:
    timestamps = [
        timestamp
        for row in (*prices, *fx_rates)
        for timestamp in (row.updated_at, row.created_at)
        if timestamp is not None
    ]
    return max(timestamps) if timestamps else None
