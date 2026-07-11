from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from ..dtos.reference_integration_dto import (
    BenchmarkComponentResponse,
    BenchmarkDefinitionResponse,
    BenchmarkReturnSeriesPoint,
    CioModelChangeAffectedMandate,
    ClassificationTaxonomyEntry,
    ComponentSeriesResponse,
    DpmPortfolioUniverseCandidate,
    IndexDefinitionResponse,
    IndexPriceSeriesPoint,
    IndexReturnSeriesPoint,
    InstrumentEligibilityRecord,
    MarketDataFxCoverageRecord,
    MarketDataPriceCoverageRecord,
    ModelPortfolioTargetRow,
    PortfolioManagerBookMember,
    PortfolioTaxLotRecord,
    RiskFreeSeriesPoint,
    SeriesPoint,
)
from ..read_models import PortfolioTaxLotReadRecord
from ..repositories.identifier_normalization import normalize_security_id
from .integration_value_normalization import (
    as_decimal,
    as_optional_decimal,
    control_code,
)


def benchmark_component_response(row: Any) -> BenchmarkComponentResponse:
    return BenchmarkComponentResponse(
        index_id=row.index_id,
        composition_weight=as_decimal(row.composition_weight),
        composition_effective_from=row.composition_effective_from,
        composition_effective_to=row.composition_effective_to,
        rebalance_event_id=row.rebalance_event_id,
    )


def benchmark_definition_response(
    row: Any,
    *,
    components: list[Any] | None = None,
) -> BenchmarkDefinitionResponse:
    return BenchmarkDefinitionResponse(
        benchmark_id=row.benchmark_id,
        benchmark_name=row.benchmark_name,
        benchmark_type=row.benchmark_type,
        benchmark_currency=row.benchmark_currency,
        return_convention=row.return_convention,
        benchmark_status=row.benchmark_status,
        benchmark_family=row.benchmark_family,
        benchmark_provider=row.benchmark_provider,
        rebalance_frequency=row.rebalance_frequency,
        classification_set_id=row.classification_set_id,
        classification_labels=dict(row.classification_labels or {}),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        quality_status=row.quality_status,
        source_timestamp=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
        components=[benchmark_component_response(component) for component in components or []],
    )


def index_definition_response(row: Any) -> IndexDefinitionResponse:
    return IndexDefinitionResponse(
        index_id=row.index_id,
        index_name=row.index_name,
        index_currency=row.index_currency,
        index_type=row.index_type,
        index_status=row.index_status,
        index_provider=row.index_provider,
        index_market=row.index_market,
        classification_set_id=row.classification_set_id,
        classification_labels=dict(row.classification_labels or {}),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        quality_status=row.quality_status,
        source_timestamp=row.source_timestamp,
        source_vendor=row.source_vendor,
        source_record_id=row.source_record_id,
    )


def model_portfolio_target_row(row: Any) -> ModelPortfolioTargetRow:
    return ModelPortfolioTargetRow(
        instrument_id=row.instrument_id,
        target_weight=as_decimal(row.target_weight),
        min_weight=as_optional_decimal(row.min_weight),
        max_weight=as_optional_decimal(row.max_weight),
        target_status=row.target_status,
        quality_status=row.quality_status,
        source_record_id=row.source_record_id,
    )


def portfolio_manager_book_member(row: Any) -> PortfolioManagerBookMember:
    return PortfolioManagerBookMember(
        portfolio_id=row.portfolio_id,
        client_id=row.client_id,
        booking_center_code=row.booking_center_code,
        portfolio_type=row.portfolio_type,
        status=row.status,
        open_date=row.open_date,
        close_date=row.close_date,
        base_currency=row.base_currency,
        source_record_id=f"portfolio:{row.portfolio_id}",
    )


def cio_model_change_affected_mandate(row: Any) -> CioModelChangeAffectedMandate:
    return CioModelChangeAffectedMandate(
        portfolio_id=row.portfolio_id,
        mandate_id=row.mandate_id,
        client_id=row.client_id,
        booking_center_code=row.booking_center_code,
        jurisdiction_code=row.jurisdiction_code,
        discretionary_authority_status=row.discretionary_authority_status,
        model_portfolio_id=row.model_portfolio_id,
        policy_pack_id=row.policy_pack_id,
        risk_profile=row.risk_profile,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        binding_version=int(row.binding_version),
        source_record_id=row.source_record_id,
    )


def dpm_portfolio_universe_candidate(row: Any) -> DpmPortfolioUniverseCandidate:
    return DpmPortfolioUniverseCandidate(
        portfolio_id=row.portfolio_id,
        mandate_id=row.mandate_id,
        client_id=row.client_id,
        booking_center_code=row.booking_center_code,
        jurisdiction_code=row.jurisdiction_code,
        discretionary_authority_status=row.discretionary_authority_status,
        model_portfolio_id=row.model_portfolio_id,
        policy_pack_id=row.policy_pack_id,
        mandate_objective=row.mandate_objective,
        risk_profile=row.risk_profile,
        investment_horizon=row.investment_horizon,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        binding_version=int(row.binding_version),
        source_record_id=row.source_record_id,
    )


def missing_instrument_eligibility_record(security_id: str) -> InstrumentEligibilityRecord:
    return InstrumentEligibilityRecord(
        security_id=normalize_security_id(security_id),
        found=False,
        eligibility_status="UNKNOWN",
        product_shelf_status="UNKNOWN",
        buy_allowed=False,
        sell_allowed=False,
        restriction_reason_codes=["ELIGIBILITY_PROFILE_MISSING"],
        settlement_days=None,
        settlement_calendar_id=None,
        liquidity_tier=None,
        issuer_id=None,
        issuer_name=None,
        ultimate_parent_issuer_id=None,
        ultimate_parent_issuer_name=None,
        asset_class=None,
        country_of_risk=None,
        effective_from=None,
        effective_to=None,
        quality_status="MISSING",
        source_record_id=None,
    )


def instrument_eligibility_record(row: Any) -> InstrumentEligibilityRecord:
    return InstrumentEligibilityRecord(
        security_id=normalize_security_id(row.security_id),
        found=True,
        eligibility_status=control_code(row.eligibility_status, default="UNKNOWN"),
        product_shelf_status=control_code(row.product_shelf_status, default="UNKNOWN"),
        buy_allowed=bool(row.buy_allowed),
        sell_allowed=bool(row.sell_allowed),
        restriction_reason_codes=list(row.restriction_reason_codes or []),
        settlement_days=int(row.settlement_days),
        settlement_calendar_id=row.settlement_calendar_id,
        liquidity_tier=row.liquidity_tier,
        issuer_id=row.issuer_id,
        issuer_name=row.issuer_name,
        ultimate_parent_issuer_id=row.ultimate_parent_issuer_id,
        ultimate_parent_issuer_name=row.ultimate_parent_issuer_name,
        asset_class=row.asset_class,
        country_of_risk=row.country_of_risk,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        quality_status=control_code(row.quality_status, default="UNKNOWN"),
        source_record_id=row.source_record_id,
    )


def portfolio_tax_lot_record(row: PortfolioTaxLotReadRecord) -> PortfolioTaxLotRecord:
    open_quantity = as_decimal(row.open_quantity)
    return PortfolioTaxLotRecord(
        portfolio_id=row.portfolio_id,
        security_id=normalize_security_id(row.security_id),
        instrument_id=normalize_security_id(row.instrument_id),
        lot_id=row.lot_id,
        open_quantity=open_quantity,
        original_quantity=as_decimal(row.original_quantity),
        acquisition_date=row.acquisition_date,
        cost_basis_base=as_decimal(row.lot_cost_base),
        cost_basis_local=as_decimal(row.lot_cost_local),
        local_currency=row.local_currency,
        tax_lot_status="OPEN" if open_quantity > Decimal("0") else "CLOSED",
        source_transaction_id=row.source_transaction_id,
        source_lineage={
            "source_system": row.source_system or "position_lot_state",
            "source_transaction_id": row.source_transaction_id,
            "calculation_policy_id": row.calculation_policy_id or "UNKNOWN",
            "calculation_policy_version": row.calculation_policy_version or "UNKNOWN",
        },
    )


def missing_market_data_price_coverage_record(
    instrument_id: str,
) -> MarketDataPriceCoverageRecord:
    return MarketDataPriceCoverageRecord(
        instrument_id=normalize_security_id(instrument_id),
        found=False,
        quality_status="MISSING",
    )


def market_data_price_coverage_record(
    row: Any,
    *,
    instrument_id: str,
    as_of_date: Any,
    max_staleness_days: int,
) -> MarketDataPriceCoverageRecord:
    age_days = (as_of_date - row.price_date).days
    quality_status = "STALE" if age_days > max_staleness_days else "READY"
    return MarketDataPriceCoverageRecord(
        instrument_id=normalize_security_id(instrument_id),
        found=True,
        price_date=row.price_date,
        price=as_decimal(row.price),
        currency=row.currency,
        age_days=age_days,
        quality_status=quality_status,
    )


def missing_market_data_fx_coverage_record(
    *,
    from_currency: str,
    to_currency: str,
) -> MarketDataFxCoverageRecord:
    return MarketDataFxCoverageRecord(
        from_currency=from_currency,
        to_currency=to_currency,
        found=False,
        quality_status="MISSING",
    )


def market_data_fx_coverage_record(
    row: Any,
    *,
    from_currency: str,
    to_currency: str,
    as_of_date: Any,
    max_staleness_days: int,
) -> MarketDataFxCoverageRecord:
    age_days = (as_of_date - row.rate_date).days
    quality_status = "STALE" if age_days > max_staleness_days else "READY"
    return MarketDataFxCoverageRecord(
        from_currency=from_currency,
        to_currency=to_currency,
        found=True,
        rate_date=row.rate_date,
        rate=as_decimal(row.rate),
        age_days=age_days,
        quality_status=quality_status,
    )


def index_price_series_point(row: Any) -> IndexPriceSeriesPoint:
    return IndexPriceSeriesPoint(
        series_date=row.series_date,
        index_price=as_decimal(row.index_price),
        series_currency=row.series_currency,
        value_convention=row.value_convention,
        quality_status=row.quality_status,
    )


def index_return_series_point(row: Any) -> IndexReturnSeriesPoint:
    return IndexReturnSeriesPoint(
        series_date=row.series_date,
        index_return=as_decimal(row.index_return),
        return_period=row.return_period,
        return_convention=row.return_convention,
        series_currency=row.series_currency,
        quality_status=row.quality_status,
    )


def benchmark_return_series_point(row: Any) -> BenchmarkReturnSeriesPoint:
    return BenchmarkReturnSeriesPoint(
        series_date=row.series_date,
        benchmark_return=as_decimal(row.benchmark_return),
        return_period=row.return_period,
        return_convention=row.return_convention,
        series_currency=row.series_currency,
        quality_status=row.quality_status,
    )


def benchmark_market_series_point(
    *,
    series_date: Any,
    requested_fields: set[str],
    price_row: Any | None,
    return_row: Any | None,
    benchmark_return_row: Any | None,
    component_weight: Decimal | None,
    fx_rate: Decimal | None,
) -> SeriesPoint:
    return SeriesPoint(
        series_date=series_date,
        series_currency=_first_market_series_value(
            "series_currency",
            price_row,
            return_row,
            benchmark_return_row,
        ),
        index_price=_requested_row_decimal(
            requested_fields,
            "index_price",
            price_row,
            "index_price",
        ),
        index_return=_requested_row_decimal(
            requested_fields,
            "index_return",
            return_row,
            "index_return",
        ),
        benchmark_return=_requested_row_decimal(
            requested_fields,
            "benchmark_return",
            benchmark_return_row,
            "benchmark_return",
        ),
        component_weight=_requested_value(requested_fields, "component_weight", component_weight),
        fx_rate=_requested_value(requested_fields, "fx_rate", fx_rate),
        quality_status=_first_market_series_value(
            "quality_status",
            price_row,
            return_row,
            benchmark_return_row,
        ),
    )


def _first_market_series_value(field_name: str, *rows: Any | None) -> Any | None:
    for row in rows:
        if row is not None and (value := getattr(row, field_name, None)):
            return value
    return None


def _requested_row_decimal(
    requested_fields: set[str],
    response_field: str,
    row: Any | None,
    row_field: str,
) -> Decimal | None:
    if row is None or response_field not in requested_fields:
        return None
    return cast(Decimal, as_decimal(getattr(row, row_field)))


def _requested_value(
    requested_fields: set[str],
    response_field: str,
    value: Decimal | None,
) -> Decimal | None:
    return value if response_field in requested_fields else None


def benchmark_component_series_response(
    *,
    index_id: str,
    points: list[SeriesPoint],
) -> ComponentSeriesResponse:
    return ComponentSeriesResponse(index_id=index_id, points=points)


def risk_free_series_point(row: Any) -> RiskFreeSeriesPoint:
    return RiskFreeSeriesPoint(
        series_date=row.series_date,
        value=as_decimal(row.value),
        value_convention=row.value_convention,
        day_count_convention=row.day_count_convention,
        compounding_convention=row.compounding_convention,
        series_currency=row.series_currency,
        quality_status=row.quality_status,
    )


def classification_taxonomy_entry(row: Any) -> ClassificationTaxonomyEntry:
    return ClassificationTaxonomyEntry(
        classification_set_id=row.classification_set_id,
        taxonomy_scope=row.taxonomy_scope,
        dimension_name=row.dimension_name,
        dimension_value=row.dimension_value,
        dimension_description=row.dimension_description,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        quality_status=row.quality_status,
    )
