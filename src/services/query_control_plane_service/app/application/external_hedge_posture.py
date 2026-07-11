"""Fail-closed use cases for unavailable external treasury and OMS sources."""

from collections.abc import Mapping
from datetime import date
from typing import cast

from portfolio_common.request_fingerprints import request_fingerprint
from portfolio_common.runtime_providers import Clock
from portfolio_common.source_data_product_metadata import source_data_product_runtime_metadata

from ..contracts.external_hedge_posture import (
    ExternalCurrencyExposureRequest,
    ExternalCurrencyExposureResponse,
    ExternalCurrencyExposureSupportability,
    ExternalEligibleHedgeInstrumentRequest,
    ExternalEligibleHedgeInstrumentResponse,
    ExternalEligibleHedgeInstrumentSupportability,
    ExternalFXForwardCurveRequest,
    ExternalFXForwardCurveResponse,
    ExternalFXForwardCurveSupportability,
    ExternalHedgeExecutionReadinessRequest,
    ExternalHedgeExecutionReadinessResponse,
    ExternalHedgeExecutionReadinessSupportability,
    ExternalHedgePolicyRequest,
    ExternalHedgePolicyResponse,
    ExternalHedgePolicySupportability,
    ExternalOrderExecutionAcknowledgementRequest,
    ExternalOrderExecutionAcknowledgementResponse,
    ExternalOrderExecutionAcknowledgementSupportability,
)
from ..domain.effective_mandate import EffectiveMandateBinding
from ..ports.effective_mandate import EffectiveMandateReader

TREASURY_SOURCE_SYSTEM = "external-bank-treasury"
OMS_SOURCE_SYSTEM = "external-bank-oms"
NOT_INGESTED = "not_ingested"

CURRENCY_EXPOSURE_MISSING = (
    "external_currency_exposure",
    "external_hedge_policy",
    "external_fx_forward_curve",
    "external_eligible_hedge_instrument",
)
CURRENCY_EXPOSURE_BLOCKED = (
    "fx_attribution",
    "hedge_advice",
    "treasury_instruction",
    "execution_readiness",
    "oms_acknowledgement",
    "fills",
    "settlement",
    "autonomous_treasury_action",
)
HEDGE_POLICY_MISSING = ("external_hedge_policy",)
HEDGE_POLICY_BLOCKED = (
    "hedge_policy_approval",
    "hedge_advice",
    "treasury_instruction",
    "counterparty_selection",
    "order_generation",
    "best_execution",
    "oms_acknowledgement",
    "fills",
    "settlement",
    "autonomous_treasury_action",
)
ELIGIBLE_INSTRUMENT_MISSING = ("external_eligible_hedge_instrument",)
ELIGIBLE_INSTRUMENT_BLOCKED = (
    "eligible_hedge_instrument_selection",
    "hedge_instrument_suitability",
    "product_recommendation",
    "counterparty_selection",
    "treasury_instruction",
    "order_generation",
    "best_execution",
    "oms_acknowledgement",
    "fills",
    "settlement",
    "autonomous_treasury_action",
)
FX_FORWARD_CURVE_MISSING = ("external_fx_forward_curve",)
FX_FORWARD_CURVE_BLOCKED = (
    "forward_pricing",
    "fx_valuation_methodology",
    "hedge_advice",
    "treasury_instruction",
    "counterparty_selection",
    "order_generation",
    "best_execution",
    "venue_routing",
    "oms_acknowledgement",
    "fills",
    "settlement",
    "autonomous_treasury_action",
)
EXECUTION_READINESS_MISSING = (
    "external_currency_exposure",
    "external_hedge_policy",
    "external_fx_forward_curve",
    "external_eligible_hedge_instrument",
    "external_hedge_execution_readiness",
)
EXECUTION_READINESS_BLOCKED = (
    "hedge_advice",
    "forward_pricing",
    "counterparty_selection",
    "best_execution",
    "oms_acknowledgement",
    "fills",
    "settlement",
    "autonomous_treasury_action",
)
ORDER_ACKNOWLEDGEMENT_MISSING = ("external_oms_order_execution_acknowledgement",)
ORDER_ACKNOWLEDGEMENT_BLOCKED = (
    "order_generation",
    "venue_routing",
    "best_execution",
    "oms_acknowledgement",
    "fills",
    "settlement",
    "execution_status_certification",
    "autonomous_execution_action",
)


class ExternalHedgePostureService:
    """Publish unavailable posture until governed external sources are ingested."""

    def __init__(self, *, mandate_reader: EffectiveMandateReader, clock: Clock) -> None:
        self._mandate_reader = mandate_reader
        self._clock = clock

    async def get_external_currency_exposure(
        self, *, portfolio_id: str, request: ExternalCurrencyExposureRequest
    ) -> ExternalCurrencyExposureResponse | None:
        binding = await self._binding(portfolio_id, request.as_of_date, request.mandate_id)
        if binding is None:
            return None
        return ExternalCurrencyExposureResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            reporting_currency=request.reporting_currency,
            exposure_currencies=request.exposure_currencies,
            exposures=[],
            supportability=ExternalCurrencyExposureSupportability(
                exposure_count=0,
                missing_data_families=list(CURRENCY_EXPOSURE_MISSING),
                blocked_capabilities=list(CURRENCY_EXPOSURE_BLOCKED),
            ),
            lineage=_lineage(
                source_system=TREASURY_SOURCE_SYSTEM,
                contract_version="rfc_039_external_currency_exposure_v1",
                blocked_capabilities=CURRENCY_EXPOSURE_BLOCKED,
            ),
            **self._metadata(
                product_key="external_currency_exposure",
                portfolio_id=portfolio_id,
                binding=binding,
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
            ),
        )

    async def get_external_hedge_policy(
        self, *, portfolio_id: str, request: ExternalHedgePolicyRequest
    ) -> ExternalHedgePolicyResponse | None:
        binding = await self._binding(portfolio_id, request.as_of_date, request.mandate_id)
        if binding is None:
            return None
        return ExternalHedgePolicyResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            reporting_currency=request.reporting_currency,
            exposure_currencies=request.exposure_currencies,
            policy_rules=[],
            supportability=ExternalHedgePolicySupportability(
                policy_rule_count=0,
                missing_data_families=list(HEDGE_POLICY_MISSING),
                blocked_capabilities=list(HEDGE_POLICY_BLOCKED),
            ),
            lineage=_lineage(
                source_system=TREASURY_SOURCE_SYSTEM,
                contract_version="rfc_039_external_hedge_policy_v1",
                blocked_capabilities=HEDGE_POLICY_BLOCKED,
            ),
            **self._metadata(
                product_key="external_hedge_policy",
                portfolio_id=portfolio_id,
                binding=binding,
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
            ),
        )

    async def get_external_eligible_hedge_instruments(
        self, *, portfolio_id: str, request: ExternalEligibleHedgeInstrumentRequest
    ) -> ExternalEligibleHedgeInstrumentResponse | None:
        binding = await self._binding(portfolio_id, request.as_of_date, request.mandate_id)
        if binding is None:
            return None
        return ExternalEligibleHedgeInstrumentResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            reporting_currency=request.reporting_currency,
            exposure_currencies=request.exposure_currencies,
            instrument_types=request.instrument_types,
            eligible_instruments=[],
            supportability=ExternalEligibleHedgeInstrumentSupportability(
                instrument_count=0,
                missing_data_families=list(ELIGIBLE_INSTRUMENT_MISSING),
                blocked_capabilities=list(ELIGIBLE_INSTRUMENT_BLOCKED),
            ),
            lineage=_lineage(
                source_system=TREASURY_SOURCE_SYSTEM,
                contract_version="rfc_039_external_eligible_hedge_instrument_v1",
                blocked_capabilities=ELIGIBLE_INSTRUMENT_BLOCKED,
            ),
            **self._metadata(
                product_key="external_eligible_hedge_instrument",
                portfolio_id=portfolio_id,
                binding=binding,
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
            ),
        )

    def get_external_fx_forward_curve(
        self, *, request: ExternalFXForwardCurveRequest
    ) -> ExternalFXForwardCurveResponse:
        identity = {
            "as_of_date": request.as_of_date.isoformat(),
            "currency_pairs": sorted(request.currency_pairs),
            "tenors": sorted(request.tenors),
            "integration_status": NOT_INGESTED,
        }
        return ExternalFXForwardCurveResponse(
            reporting_currency=request.reporting_currency,
            currency_pairs=request.currency_pairs,
            tenors=request.tenors,
            curve_points=[],
            supportability=ExternalFXForwardCurveSupportability(
                curve_point_count=0,
                missing_data_families=list(FX_FORWARD_CURVE_MISSING),
                blocked_capabilities=list(FX_FORWARD_CURVE_BLOCKED),
            ),
            lineage=_lineage(
                source_system=TREASURY_SOURCE_SYSTEM,
                contract_version="rfc_039_external_fx_forward_curve_v1",
                blocked_capabilities=FX_FORWARD_CURVE_BLOCKED,
            ),
            **_runtime_metadata(
                clock=self._clock,
                product_key="external_fx_forward_curve",
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                identity=identity,
            ),
        )

    async def get_external_hedge_execution_readiness(
        self, *, portfolio_id: str, request: ExternalHedgeExecutionReadinessRequest
    ) -> ExternalHedgeExecutionReadinessResponse | None:
        binding = await self._binding(portfolio_id, request.as_of_date, request.mandate_id)
        if binding is None:
            return None
        return ExternalHedgeExecutionReadinessResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            reporting_currency=request.reporting_currency,
            exposure_currencies=request.exposure_currencies,
            readiness_checks=[],
            supportability=ExternalHedgeExecutionReadinessSupportability(
                missing_data_families=list(EXECUTION_READINESS_MISSING),
                blocked_capabilities=list(EXECUTION_READINESS_BLOCKED),
            ),
            lineage=_lineage(
                source_system=TREASURY_SOURCE_SYSTEM,
                contract_version="rfc_039_external_hedge_execution_readiness_v1",
                blocked_capabilities=EXECUTION_READINESS_BLOCKED,
            ),
            **self._metadata(
                product_key="external_hedge_execution_readiness",
                portfolio_id=portfolio_id,
                binding=binding,
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
            ),
        )

    async def get_external_order_execution_acknowledgement(
        self, *, portfolio_id: str, request: ExternalOrderExecutionAcknowledgementRequest
    ) -> ExternalOrderExecutionAcknowledgementResponse | None:
        binding = await self._binding(portfolio_id, request.as_of_date, request.mandate_id)
        if binding is None:
            return None
        identity = self._identity(portfolio_id, binding, request.as_of_date)
        identity.update(
            {
                "execution_intent_id": request.execution_intent_id,
                "order_reference_ids": sorted(request.order_reference_ids),
            }
        )
        return ExternalOrderExecutionAcknowledgementResponse(
            portfolio_id=portfolio_id,
            client_id=binding.client_id,
            mandate_id=binding.mandate_id,
            execution_intent_id=request.execution_intent_id,
            order_reference_ids=request.order_reference_ids,
            acknowledgements=[],
            supportability=ExternalOrderExecutionAcknowledgementSupportability(
                acknowledgement_count=0,
                missing_data_families=list(ORDER_ACKNOWLEDGEMENT_MISSING),
                blocked_capabilities=list(ORDER_ACKNOWLEDGEMENT_BLOCKED),
            ),
            lineage=_lineage(
                source_system=OMS_SOURCE_SYSTEM,
                contract_version="rfc_042_external_order_execution_acknowledgement_v1",
                blocked_capabilities=ORDER_ACKNOWLEDGEMENT_BLOCKED,
            ),
            **_runtime_metadata(
                clock=self._clock,
                product_key="external_order_execution_acknowledgement",
                as_of_date=request.as_of_date,
                tenant_id=request.tenant_id,
                identity=identity,
            ),
        )

    async def _binding(
        self, portfolio_id: str, as_of_date: date, mandate_id: str | None
    ) -> EffectiveMandateBinding | None:
        return await self._mandate_reader.resolve(
            portfolio_id=portfolio_id,
            as_of_date=as_of_date,
            mandate_id=mandate_id,
        )

    def _metadata(
        self,
        *,
        product_key: str,
        portfolio_id: str,
        binding: EffectiveMandateBinding,
        as_of_date: date,
        tenant_id: str | None,
    ) -> dict[str, object]:
        return _runtime_metadata(
            clock=self._clock,
            product_key=product_key,
            as_of_date=as_of_date,
            tenant_id=tenant_id,
            identity=self._identity(portfolio_id, binding, as_of_date),
        )

    @staticmethod
    def _identity(
        portfolio_id: str, binding: EffectiveMandateBinding, as_of_date: date
    ) -> dict[str, object]:
        return {
            "portfolio_id": portfolio_id,
            "client_id": binding.client_id,
            "as_of_date": as_of_date.isoformat(),
            "integration_status": NOT_INGESTED,
        }


def _runtime_metadata(
    *,
    clock: Clock,
    product_key: str,
    as_of_date: date,
    tenant_id: str | None,
    identity: Mapping[str, object],
) -> dict[str, object]:
    return cast(
        dict[str, object],
        source_data_product_runtime_metadata(
            as_of_date=as_of_date,
            generated_at=clock.utc_now(),
            tenant_id=tenant_id,
            data_quality_status="MISSING",
            latest_evidence_timestamp=None,
            source_batch_fingerprint=None,
            snapshot_id=f"{product_key}:{request_fingerprint(identity)}",
        ),
    )


def _lineage(
    *, source_system: str, contract_version: str, blocked_capabilities: tuple[str, ...]
) -> dict[str, str]:
    return {
        "source_system": source_system,
        "source_table": NOT_INGESTED,
        "contract_version": contract_version,
        "integration_status": NOT_INGESTED,
        "runtime_posture": "fail_closed",
        "non_claims": ",".join(blocked_capabilities),
    }
