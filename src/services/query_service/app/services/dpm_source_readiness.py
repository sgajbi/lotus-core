from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from ..dtos.reference_integration_dto import (
    DiscretionaryMandateBindingRequest,
    DpmSourceFamilyReadiness,
    DpmSourceFamilyState,
    DpmSourceReadinessRequest,
    DpmSourceReadinessResponse,
    DpmSourceReadinessSupportability,
    InstrumentEligibilityBulkRequest,
    MarketDataCoverageRequest,
    ModelPortfolioTargetRequest,
    PortfolioTaxLotWindowRequest,
)
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date

DpmSourceFamilyName = Literal["mandate", "model_targets", "eligibility", "tax_lots", "market_data"]
TSourceResponse = TypeVar("TSourceResponse")


@dataclass(frozen=True)
class DpmSourceReadinessIdentity:
    mandate_id: str | None
    model_portfolio_id: str | None


@dataclass(frozen=True)
class DpmSourceModelTargetsResolution:
    target_instrument_ids: list[str]
    family: DpmSourceFamilyReadiness


@dataclass(frozen=True)
class DpmSourceMandateResolution:
    identity: DpmSourceReadinessIdentity
    family: DpmSourceFamilyReadiness


async def dpm_source_read_or_none(
    read_source: Callable[[], Awaitable[TSourceResponse]],
) -> TSourceResponse | None:
    try:
        return await read_source()
    except (LookupError, ValueError):
        return None


async def dpm_source_model_targets_read_or_none(
    *,
    model_portfolio_id: str | None,
    read_model_targets: Callable[[str], Awaitable[TSourceResponse]],
) -> TSourceResponse | None:
    if model_portfolio_id is None:
        return None
    return await dpm_source_read_or_none(lambda: read_model_targets(model_portfolio_id))


def dpm_source_family_readiness(
    *,
    family: DpmSourceFamilyName,
    product_name: str,
    state: DpmSourceFamilyState,
    reason: str,
    missing_items: list[str] | None = None,
    stale_items: list[str] | None = None,
    evidence_count: int = 0,
) -> DpmSourceFamilyReadiness:
    return DpmSourceFamilyReadiness(
        family=family,
        product_name=product_name,
        state=state,
        reason=reason,
        missing_items=list(missing_items or []),
        stale_items=list(stale_items or []),
        evidence_count=evidence_count,
    )


def unavailable_dpm_source_family(
    *,
    family: DpmSourceFamilyName,
    product_name: str,
    reason: str,
    missing_items: list[str] | None = None,
) -> DpmSourceFamilyReadiness:
    return dpm_source_family_readiness(
        family=family,
        product_name=product_name,
        state="UNAVAILABLE",
        reason=reason,
        missing_items=missing_items,
    )


def unavailable_mandate_binding_family() -> DpmSourceFamilyReadiness:
    return unavailable_dpm_source_family(
        family="mandate",
        product_name="DiscretionaryMandateBinding",
        reason="MANDATE_BINDING_UNAVAILABLE",
        missing_items=["mandate_binding"],
    )


def unavailable_model_portfolio_id_family() -> DpmSourceFamilyReadiness:
    return unavailable_dpm_source_family(
        family="model_targets",
        product_name="DpmModelPortfolioTarget",
        reason="MODEL_PORTFOLIO_ID_UNAVAILABLE",
        missing_items=["model_portfolio_id"],
    )


def unavailable_model_targets_family(model_portfolio_id: str) -> DpmSourceFamilyReadiness:
    return unavailable_dpm_source_family(
        family="model_targets",
        product_name="DpmModelPortfolioTarget",
        reason="MODEL_TARGETS_UNAVAILABLE",
        missing_items=[model_portfolio_id],
    )


def unavailable_eligibility_family(instrument_ids: list[str]) -> DpmSourceFamilyReadiness:
    return unavailable_dpm_source_family(
        family="eligibility",
        product_name="InstrumentEligibilityProfile",
        reason="INSTRUMENT_ELIGIBILITY_UNAVAILABLE",
        missing_items=instrument_ids[:10],
    )


def empty_instrument_universe_family() -> DpmSourceFamilyReadiness:
    return unavailable_dpm_source_family(
        family="eligibility",
        product_name="InstrumentEligibilityProfile",
        reason="DPM_INSTRUMENT_UNIVERSE_EMPTY",
        missing_items=["instrument_ids"],
    )


def unavailable_tax_lots_family(portfolio_id: str) -> DpmSourceFamilyReadiness:
    return unavailable_dpm_source_family(
        family="tax_lots",
        product_name="PortfolioTaxLotWindow",
        reason="PORTFOLIO_TAX_LOTS_UNAVAILABLE",
        missing_items=[portfolio_id],
    )


def unavailable_market_data_family() -> DpmSourceFamilyReadiness:
    return unavailable_dpm_source_family(
        family="market_data",
        product_name="MarketDataCoverageWindow",
        reason="MARKET_DATA_COVERAGE_UNAVAILABLE",
        missing_items=["market_data_coverage"],
    )


def mandate_source_family_readiness(mandate_response: Any) -> DpmSourceFamilyReadiness:
    return dpm_source_family_readiness(
        family="mandate",
        product_name="DiscretionaryMandateBinding",
        state=mandate_response.supportability.state,
        reason=mandate_response.supportability.reason,
        missing_items=mandate_response.supportability.missing_data_families,
        evidence_count=1,
    )


def model_targets_source_family_readiness(model_response: Any) -> DpmSourceFamilyReadiness:
    return dpm_source_family_readiness(
        family="model_targets",
        product_name="DpmModelPortfolioTarget",
        state=model_response.supportability.state,
        reason=model_response.supportability.reason,
        evidence_count=model_response.supportability.target_count,
    )


def eligibility_source_family_readiness(eligibility_response: Any) -> DpmSourceFamilyReadiness:
    return dpm_source_family_readiness(
        family="eligibility",
        product_name="InstrumentEligibilityProfile",
        state=eligibility_response.supportability.state,
        reason=eligibility_response.supportability.reason,
        missing_items=eligibility_response.supportability.missing_security_ids,
        evidence_count=eligibility_response.supportability.resolved_count,
    )


def tax_lots_source_family_readiness(tax_lot_response: Any) -> DpmSourceFamilyReadiness:
    return dpm_source_family_readiness(
        family="tax_lots",
        product_name="PortfolioTaxLotWindow",
        state=tax_lot_response.supportability.state,
        reason=tax_lot_response.supportability.reason,
        missing_items=tax_lot_response.supportability.missing_security_ids,
        evidence_count=tax_lot_response.supportability.returned_lot_count,
    )


def market_data_source_family_readiness(market_data_response: Any) -> DpmSourceFamilyReadiness:
    return dpm_source_family_readiness(
        family="market_data",
        product_name="MarketDataCoverageWindow",
        state=market_data_response.supportability.state,
        reason=market_data_response.supportability.reason,
        missing_items=[
            *market_data_response.supportability.missing_instrument_ids,
            *market_data_response.supportability.missing_currency_pairs,
        ],
        stale_items=[
            *market_data_response.supportability.stale_instrument_ids,
            *market_data_response.supportability.stale_currency_pairs,
        ],
        evidence_count=(
            market_data_response.supportability.resolved_price_count
            + market_data_response.supportability.resolved_fx_count
        ),
    )


def dpm_source_evaluated_instrument_ids(
    *,
    request_instrument_ids: list[str],
    target_instrument_ids: list[str],
) -> list[str]:
    return sorted({*request_instrument_ids, *target_instrument_ids})


def dpm_source_initial_identity(
    request: DpmSourceReadinessRequest,
) -> DpmSourceReadinessIdentity:
    return DpmSourceReadinessIdentity(
        mandate_id=request.mandate_id,
        model_portfolio_id=request.model_portfolio_id,
    )


def dpm_source_identity_from_mandate(
    *,
    request: DpmSourceReadinessRequest,
    mandate_response: Any,
) -> DpmSourceReadinessIdentity:
    return DpmSourceReadinessIdentity(
        mandate_id=mandate_response.mandate_id,
        model_portfolio_id=request.model_portfolio_id or mandate_response.model_portfolio_id,
    )


def dpm_source_mandate_resolution(
    *,
    request: DpmSourceReadinessRequest,
    mandate_response: Any | None,
) -> DpmSourceMandateResolution:
    if mandate_response is None:
        return DpmSourceMandateResolution(
            identity=dpm_source_initial_identity(request),
            family=unavailable_mandate_binding_family(),
        )
    return DpmSourceMandateResolution(
        identity=dpm_source_identity_from_mandate(
            request=request,
            mandate_response=mandate_response,
        ),
        family=mandate_source_family_readiness(mandate_response),
    )


def dpm_source_model_targets_resolution(
    *,
    model_portfolio_id: str | None,
    model_response: Any | None,
) -> DpmSourceModelTargetsResolution:
    if model_portfolio_id is None:
        return DpmSourceModelTargetsResolution(
            target_instrument_ids=[],
            family=unavailable_model_portfolio_id_family(),
        )
    if model_response is None:
        return DpmSourceModelTargetsResolution(
            target_instrument_ids=[],
            family=unavailable_model_targets_family(model_portfolio_id),
        )
    return DpmSourceModelTargetsResolution(
        target_instrument_ids=[target.instrument_id for target in model_response.targets],
        family=model_targets_source_family_readiness(model_response),
    )


def dpm_source_eligibility_family(
    *,
    evaluated_instrument_ids: list[str],
    eligibility_response: Any | None,
) -> DpmSourceFamilyReadiness:
    if not evaluated_instrument_ids:
        return empty_instrument_universe_family()
    if eligibility_response is None:
        return unavailable_eligibility_family(evaluated_instrument_ids)
    return eligibility_source_family_readiness(eligibility_response)


def dpm_source_tax_lots_family(
    *,
    portfolio_id: str,
    tax_lot_response: Any | None,
) -> DpmSourceFamilyReadiness:
    if tax_lot_response is None:
        return unavailable_tax_lots_family(portfolio_id)
    return tax_lots_source_family_readiness(tax_lot_response)


def dpm_source_market_data_family(
    market_data_response: Any | None,
) -> DpmSourceFamilyReadiness:
    if market_data_response is None:
        return unavailable_market_data_family()
    return market_data_source_family_readiness(market_data_response)


def dpm_mandate_binding_request(
    request: DpmSourceReadinessRequest,
) -> DiscretionaryMandateBindingRequest:
    return DiscretionaryMandateBindingRequest(
        as_of_date=request.as_of_date,
        tenant_id=request.tenant_id,
        mandate_id=request.mandate_id,
        include_policy_pack=True,
    )


def dpm_model_targets_request(
    request: DpmSourceReadinessRequest,
) -> ModelPortfolioTargetRequest:
    return ModelPortfolioTargetRequest(
        as_of_date=request.as_of_date,
        include_inactive_targets=False,
        tenant_id=request.tenant_id,
    )


def dpm_eligibility_request(
    *,
    request: DpmSourceReadinessRequest,
    instrument_ids: list[str],
) -> InstrumentEligibilityBulkRequest:
    return InstrumentEligibilityBulkRequest(
        as_of_date=request.as_of_date,
        security_ids=instrument_ids,
        tenant_id=request.tenant_id,
        include_restricted_rationale=False,
    )


def dpm_tax_lot_window_request(
    *,
    request: DpmSourceReadinessRequest,
    evaluated_instrument_ids: list[str],
) -> PortfolioTaxLotWindowRequest:
    return PortfolioTaxLotWindowRequest(
        as_of_date=request.as_of_date,
        security_ids=evaluated_instrument_ids or None,
        tenant_id=request.tenant_id,
    )


def dpm_market_data_coverage_request(
    *,
    request: DpmSourceReadinessRequest,
    evaluated_instrument_ids: list[str],
) -> MarketDataCoverageRequest:
    return MarketDataCoverageRequest(
        as_of_date=request.as_of_date,
        instrument_ids=evaluated_instrument_ids,
        currency_pairs=request.currency_pairs,
        valuation_currency=request.valuation_currency,
        max_staleness_days=request.max_staleness_days,
        tenant_id=request.tenant_id,
    )


def dpm_source_readiness_supportability(
    families: list[DpmSourceFamilyReadiness],
) -> DpmSourceReadinessSupportability:
    counts: dict[DpmSourceFamilyState, int] = {
        "READY": 0,
        "DEGRADED": 0,
        "INCOMPLETE": 0,
        "UNAVAILABLE": 0,
    }
    for family in families:
        counts[family.state] += 1

    if counts["UNAVAILABLE"]:
        state: DpmSourceFamilyState = "UNAVAILABLE"
        reason = "DPM_SOURCE_READINESS_UNAVAILABLE"
    elif counts["INCOMPLETE"]:
        state = "INCOMPLETE"
        reason = "DPM_SOURCE_READINESS_INCOMPLETE"
    elif counts["DEGRADED"]:
        state = "DEGRADED"
        reason = "DPM_SOURCE_READINESS_DEGRADED"
    else:
        state = "READY"
        reason = "DPM_SOURCE_READINESS_READY"

    return DpmSourceReadinessSupportability(
        state=state,
        reason=reason,
        ready_family_count=counts["READY"],
        degraded_family_count=counts["DEGRADED"],
        incomplete_family_count=counts["INCOMPLETE"],
        unavailable_family_count=counts["UNAVAILABLE"],
    )


def build_dpm_source_readiness_response(
    *,
    portfolio_id: str,
    request: DpmSourceReadinessRequest,
    resolved_mandate_id: str | None,
    resolved_model_portfolio_id: str | None,
    evaluated_instrument_ids: list[str],
    families: list[DpmSourceFamilyReadiness],
) -> DpmSourceReadinessResponse:
    supportability = dpm_source_readiness_supportability(families)
    return DpmSourceReadinessResponse(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        mandate_id=resolved_mandate_id,
        model_portfolio_id=resolved_model_portfolio_id,
        evaluated_instrument_ids=evaluated_instrument_ids,
        families=families,
        supportability=supportability,
        lineage={
            "source_system": "lotus-core",
            "contract_version": "rfc_087_v1",
            "readiness_scope": "dpm_source_family",
        },
        **source_product_runtime_metadata_without_as_of_date(
            request.as_of_date,
            data_quality_status=("COMPLETE" if supportability.state == "READY" else "PARTIAL"),
            latest_evidence_timestamp=None,
        ),
    )
