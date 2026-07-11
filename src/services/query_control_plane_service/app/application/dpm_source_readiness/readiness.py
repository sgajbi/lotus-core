"""Aggregate application policy for DPM source-family readiness."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, TypeVar

from ...contracts.discretionary_mandate_binding import (
    DiscretionaryMandateBindingRequest,
    DiscretionaryMandateBindingResponse,
)
from ...contracts.dpm_source_readiness import (
    DpmSourceFamilyReadiness,
    DpmSourceFamilyState,
    DpmSourceReadinessRequest,
    DpmSourceReadinessResponse,
    DpmSourceReadinessSupportability,
)
from ...contracts.instrument_eligibility import (
    InstrumentEligibilityBulkRequest,
    InstrumentEligibilityBulkResponse,
)
from ...contracts.market_data_coverage import (
    MarketDataCoverageRequest,
    MarketDataCoverageWindowResponse,
)
from ...contracts.model_portfolio_targets import (
    ModelPortfolioTargetRequest,
    ModelPortfolioTargetResponse,
)
from ...contracts.portfolio_tax_lots import (
    PortfolioTaxLotWindowRequest,
    PortfolioTaxLotWindowResponse,
)
from .discretionary_mandate_binding import DiscretionaryMandateBindingService
from .instrument_eligibility import InstrumentEligibilityService
from .market_data_coverage import MarketDataCoverageService
from .metadata import dpm_source_runtime_metadata
from .model_portfolio_targets import ModelPortfolioTargetService
from .portfolio_tax_lots import PortfolioTaxLotService

DpmSourceFamilyName = Literal["mandate", "model_targets", "eligibility", "tax_lots", "market_data"]
SourceResponse = TypeVar("SourceResponse")


@dataclass(frozen=True, slots=True)
class DpmSourceIdentity:
    """Mandate and model identities resolved for readiness assembly."""

    mandate_id: str | None
    model_portfolio_id: str | None


@dataclass(slots=True)
class DpmSourceReadinessService:
    """Coordinate five source products into one fail-closed DPM readiness decision."""

    mandates: DiscretionaryMandateBindingService
    model_targets: ModelPortfolioTargetService
    eligibility: InstrumentEligibilityService
    tax_lots: PortfolioTaxLotService
    market_data: MarketDataCoverageService
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def resolve_model_portfolio_targets(
        self,
        *,
        model_portfolio_id: str,
        request: ModelPortfolioTargetRequest,
    ) -> ModelPortfolioTargetResponse | None:
        """Resolve the model-target constituent through the same capability boundary."""

        return await self.model_targets.resolve(
            model_portfolio_id=model_portfolio_id,
            request=request,
        )

    async def resolve_discretionary_mandate_binding(
        self,
        *,
        portfolio_id: str,
        request: DiscretionaryMandateBindingRequest,
    ) -> DiscretionaryMandateBindingResponse | None:
        """Resolve the mandate-binding constituent through the capability boundary."""

        return await self.mandates.resolve(portfolio_id=portfolio_id, request=request)

    async def resolve_instrument_eligibility_bulk(
        self,
        request: InstrumentEligibilityBulkRequest,
    ) -> InstrumentEligibilityBulkResponse:
        """Resolve the eligibility constituent through the capability boundary."""

        return await self.eligibility.resolve(request)

    async def get_portfolio_tax_lot_window(
        self,
        *,
        portfolio_id: str,
        request: PortfolioTaxLotWindowRequest,
    ) -> PortfolioTaxLotWindowResponse:
        """Resolve the tax-lot constituent through the capability boundary."""

        return await self.tax_lots.resolve(portfolio_id=portfolio_id, request=request)

    async def get_market_data_coverage(
        self,
        request: MarketDataCoverageRequest,
    ) -> MarketDataCoverageWindowResponse:
        """Resolve the market-data constituent through the capability boundary."""

        return await self.market_data.resolve(request)

    async def get_source_readiness(
        self,
        *,
        portfolio_id: str,
        request: DpmSourceReadinessRequest,
    ) -> DpmSourceReadinessResponse:
        """Evaluate aggregate readiness through the capability boundary."""

        return await self.resolve(portfolio_id=portfolio_id, request=request)

    async def resolve(
        self,
        *,
        portfolio_id: str,
        request: DpmSourceReadinessRequest,
    ) -> DpmSourceReadinessResponse:
        mandate = await _read_or_none(
            self.mandates.resolve(
                portfolio_id=portfolio_id,
                request=_mandate_request(request),
            )
        )
        identity = DpmSourceIdentity(
            mandate_id=mandate.mandate_id if mandate else request.mandate_id,
            model_portfolio_id=(
                request.model_portfolio_id
                or (mandate.model_portfolio_id if mandate is not None else None)
            ),
        )
        model = (
            await _read_or_none(
                self.model_targets.resolve(
                    model_portfolio_id=identity.model_portfolio_id,
                    request=_model_target_request(request),
                )
            )
            if identity.model_portfolio_id is not None
            else None
        )
        evaluated_instrument_ids = sorted(
            {
                *request.instrument_ids,
                *(target.instrument_id for target in (model.targets if model is not None else [])),
            }
        )
        eligibility = (
            await _read_or_none(
                self.eligibility.resolve(_eligibility_request(request, evaluated_instrument_ids))
            )
            if evaluated_instrument_ids
            else None
        )
        tax_lots = await _read_or_none(
            self.tax_lots.resolve(
                portfolio_id=portfolio_id,
                request=_tax_lot_request(request, evaluated_instrument_ids),
            )
        )
        market_data = await _read_or_none(
            self.market_data.resolve(_market_data_request(request, evaluated_instrument_ids))
        )
        families = [
            _mandate_family(mandate),
            _model_target_family(identity.model_portfolio_id, model),
            _eligibility_family(evaluated_instrument_ids, eligibility),
            _tax_lot_family(portfolio_id, tax_lots),
            _market_data_family(market_data),
        ]
        return build_dpm_source_readiness_response(
            portfolio_id=portfolio_id,
            request=request,
            identity=identity,
            evaluated_instrument_ids=evaluated_instrument_ids,
            families=families,
            source_responses=(mandate, model, eligibility, tax_lots, market_data),
            generated_at=self.clock(),
        )


async def _read_or_none(awaitable: Awaitable[SourceResponse]) -> SourceResponse | None:
    try:
        return await awaitable
    except (LookupError, ValueError):
        return None


def build_dpm_source_readiness_response(
    *,
    portfolio_id: str,
    request: DpmSourceReadinessRequest,
    identity: DpmSourceIdentity,
    evaluated_instrument_ids: list[str],
    families: list[DpmSourceFamilyReadiness],
    source_responses: tuple[object | None, ...],
    generated_at: datetime,
) -> DpmSourceReadinessResponse:
    """Build aggregate readiness with source-owned deterministic proof metadata."""

    supportability = _aggregate_supportability(families)
    lineage = {
        "source_system": "lotus-core",
        "contract_version": "rfc_087_v1",
        "readiness_scope": "dpm_source_family",
    }
    content_payload = {
        "portfolio_id": portfolio_id,
        "as_of_date": request.as_of_date,
        "mandate_id": identity.mandate_id,
        "model_portfolio_id": identity.model_portfolio_id,
        "evaluated_instrument_ids": evaluated_instrument_ids,
        "families": [family.model_dump(mode="json") for family in families],
        "supportability": supportability.model_dump(mode="json"),
        "lineage": lineage,
    }
    latest_evidence = _latest_constituent_evidence_timestamp(source_responses)
    is_current = supportability.state == "READY" and latest_evidence is not None
    return DpmSourceReadinessResponse(
        portfolio_id=portfolio_id,
        mandate_id=identity.mandate_id,
        model_portfolio_id=identity.model_portfolio_id,
        evaluated_instrument_ids=evaluated_instrument_ids,
        families=families,
        supportability=supportability,
        lineage=lineage,
        **dpm_source_runtime_metadata(
            product_name="DpmSourceReadiness",
            source_key=portfolio_id,
            as_of_date=request.as_of_date,
            generated_at=generated_at,
            tenant_id=request.tenant_id,
            data_quality_status="COMPLETE" if is_current else "PARTIAL",
            latest_evidence_timestamp=latest_evidence,
            content_payload=content_payload,
            lineage=lineage,
            source_evidence_current=is_current,
            freshness_status="CURRENT" if is_current else "PARTIAL",
        ),
    )


def _family(
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
        missing_items=missing_items or [],
        stale_items=stale_items or [],
        evidence_count=evidence_count,
    )


def _unavailable(
    family: DpmSourceFamilyName,
    product_name: str,
    reason: str,
    missing_items: list[str],
) -> DpmSourceFamilyReadiness:
    return _family(
        family=family,
        product_name=product_name,
        state="UNAVAILABLE",
        reason=reason,
        missing_items=missing_items,
    )


def _mandate_family(
    response: DiscretionaryMandateBindingResponse | None,
) -> DpmSourceFamilyReadiness:
    if response is None:
        return _unavailable(
            "mandate",
            "DiscretionaryMandateBinding",
            "MANDATE_BINDING_UNAVAILABLE",
            ["mandate_binding"],
        )
    return _family(
        family="mandate",
        product_name="DiscretionaryMandateBinding",
        state=response.supportability.state,
        reason=response.supportability.reason,
        missing_items=response.supportability.missing_data_families,
        evidence_count=1,
    )


def _model_target_family(
    model_portfolio_id: str | None,
    response: ModelPortfolioTargetResponse | None,
) -> DpmSourceFamilyReadiness:
    if model_portfolio_id is None:
        return _unavailable(
            "model_targets",
            "DpmModelPortfolioTarget",
            "MODEL_PORTFOLIO_ID_UNAVAILABLE",
            ["model_portfolio_id"],
        )
    if response is None:
        return _unavailable(
            "model_targets",
            "DpmModelPortfolioTarget",
            "MODEL_TARGETS_UNAVAILABLE",
            [model_portfolio_id],
        )
    return _family(
        family="model_targets",
        product_name="DpmModelPortfolioTarget",
        state=response.supportability.state,
        reason=response.supportability.reason,
        evidence_count=response.supportability.target_count,
    )


def _eligibility_family(
    instrument_ids: list[str],
    response: InstrumentEligibilityBulkResponse | None,
) -> DpmSourceFamilyReadiness:
    if not instrument_ids:
        return _unavailable(
            "eligibility",
            "InstrumentEligibilityProfile",
            "DPM_INSTRUMENT_UNIVERSE_EMPTY",
            ["instrument_ids"],
        )
    if response is None:
        return _unavailable(
            "eligibility",
            "InstrumentEligibilityProfile",
            "INSTRUMENT_ELIGIBILITY_UNAVAILABLE",
            instrument_ids[:10],
        )
    return _family(
        family="eligibility",
        product_name="InstrumentEligibilityProfile",
        state=response.supportability.state,
        reason=response.supportability.reason,
        missing_items=response.supportability.missing_security_ids,
        evidence_count=response.supportability.resolved_count,
    )


def _tax_lot_family(
    portfolio_id: str,
    response: PortfolioTaxLotWindowResponse | None,
) -> DpmSourceFamilyReadiness:
    if response is None:
        return _unavailable(
            "tax_lots",
            "PortfolioTaxLotWindow",
            "PORTFOLIO_TAX_LOTS_UNAVAILABLE",
            [portfolio_id],
        )
    return _family(
        family="tax_lots",
        product_name="PortfolioTaxLotWindow",
        state=response.supportability.state,
        reason=response.supportability.reason,
        missing_items=response.supportability.missing_security_ids,
        evidence_count=response.supportability.returned_lot_count,
    )


def _market_data_family(
    response: MarketDataCoverageWindowResponse | None,
) -> DpmSourceFamilyReadiness:
    if response is None:
        return _unavailable(
            "market_data",
            "MarketDataCoverageWindow",
            "MARKET_DATA_COVERAGE_UNAVAILABLE",
            ["market_data_coverage"],
        )
    return _family(
        family="market_data",
        product_name="MarketDataCoverageWindow",
        state=response.supportability.state,
        reason=response.supportability.reason,
        missing_items=[
            *response.supportability.missing_instrument_ids,
            *response.supportability.missing_currency_pairs,
        ],
        stale_items=[
            *response.supportability.stale_instrument_ids,
            *response.supportability.stale_currency_pairs,
        ],
        evidence_count=(
            response.supportability.resolved_price_count + response.supportability.resolved_fx_count
        ),
    )


def _aggregate_supportability(
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
    elif counts["INCOMPLETE"]:
        state = "INCOMPLETE"
    elif counts["DEGRADED"]:
        state = "DEGRADED"
    else:
        state = "READY"
    return DpmSourceReadinessSupportability(
        state=state,
        reason=f"DPM_SOURCE_READINESS_{state}",
        ready_family_count=counts["READY"],
        degraded_family_count=counts["DEGRADED"],
        incomplete_family_count=counts["INCOMPLETE"],
        unavailable_family_count=counts["UNAVAILABLE"],
    )


def _mandate_request(request: DpmSourceReadinessRequest) -> DiscretionaryMandateBindingRequest:
    return DiscretionaryMandateBindingRequest(
        as_of_date=request.as_of_date,
        tenant_id=request.tenant_id,
        mandate_id=request.mandate_id,
        include_policy_pack=True,
    )


def _model_target_request(request: DpmSourceReadinessRequest) -> ModelPortfolioTargetRequest:
    return ModelPortfolioTargetRequest(
        as_of_date=request.as_of_date,
        tenant_id=request.tenant_id,
        include_inactive_targets=False,
    )


def _eligibility_request(
    request: DpmSourceReadinessRequest,
    instrument_ids: list[str],
) -> InstrumentEligibilityBulkRequest:
    return InstrumentEligibilityBulkRequest(
        as_of_date=request.as_of_date,
        security_ids=instrument_ids,
        tenant_id=request.tenant_id,
        include_restricted_rationale=False,
    )


def _tax_lot_request(
    request: DpmSourceReadinessRequest,
    instrument_ids: list[str],
) -> PortfolioTaxLotWindowRequest:
    return PortfolioTaxLotWindowRequest(
        as_of_date=request.as_of_date,
        security_ids=instrument_ids or None,
        tenant_id=request.tenant_id,
    )


def _market_data_request(
    request: DpmSourceReadinessRequest,
    instrument_ids: list[str],
) -> MarketDataCoverageRequest:
    return MarketDataCoverageRequest(
        as_of_date=request.as_of_date,
        instrument_ids=instrument_ids,
        currency_pairs=request.currency_pairs,
        valuation_currency=request.valuation_currency,
        max_staleness_days=request.max_staleness_days,
        tenant_id=request.tenant_id,
    )


def _latest_constituent_evidence_timestamp(
    responses: tuple[object | None, ...],
) -> datetime | None:
    timestamps = [
        timestamp
        for response in responses
        if response is not None
        and isinstance(
            timestamp := getattr(response, "latest_evidence_timestamp", None),
            datetime,
        )
    ]
    return max(timestamps) if timestamps else None
