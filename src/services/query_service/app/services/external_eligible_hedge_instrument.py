from __future__ import annotations

from typing import Any

from ..dtos.reference_integration_dto import (
    ExternalEligibleHedgeInstrumentRequest,
    ExternalEligibleHedgeInstrumentResponse,
    ExternalEligibleHedgeInstrumentSupportability,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from .request_fingerprint import request_fingerprint

EXTERNAL_ELIGIBLE_HEDGE_INSTRUMENT_MISSING_FAMILIES = ["external_eligible_hedge_instrument"]

EXTERNAL_ELIGIBLE_HEDGE_INSTRUMENT_BLOCKED_CAPABILITIES = [
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
]


async def resolve_external_eligible_hedge_instrument_response(
    *,
    repository: Any,
    portfolio_id: str,
    request: ExternalEligibleHedgeInstrumentRequest,
) -> ExternalEligibleHedgeInstrumentResponse | None:
    binding = await repository.resolve_discretionary_mandate_binding(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        mandate_id=request.mandate_id,
    )
    if binding is None:
        return None

    return build_external_eligible_hedge_instrument_response(
        portfolio_id=portfolio_id,
        binding=binding,
        request=request,
    )


def build_external_eligible_hedge_instrument_response(
    *,
    portfolio_id: str,
    binding: Any,
    request: ExternalEligibleHedgeInstrumentRequest,
) -> ExternalEligibleHedgeInstrumentResponse:
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
            missing_data_families=EXTERNAL_ELIGIBLE_HEDGE_INSTRUMENT_MISSING_FAMILIES,
            blocked_capabilities=(EXTERNAL_ELIGIBLE_HEDGE_INSTRUMENT_BLOCKED_CAPABILITIES),
        ),
        lineage={
            "source_system": "external-bank-treasury",
            "source_table": "not_ingested",
            "contract_version": "rfc_039_external_eligible_hedge_instrument_v1",
            "integration_status": "not_ingested",
            "runtime_posture": "fail_closed",
            "non_claims": ",".join(EXTERNAL_ELIGIBLE_HEDGE_INSTRUMENT_BLOCKED_CAPABILITIES),
        },
        **source_data_product_runtime_metadata(
            as_of_date=request.as_of_date,
            tenant_id=request.tenant_id,
            data_quality_status="MISSING",
            latest_evidence_timestamp=None,
            source_batch_fingerprint=request_fingerprint(
                {
                    "product": "ExternalEligibleHedgeInstrument",
                    "portfolio_id": portfolio_id,
                    "client_id": binding.client_id,
                    "mandate_id": binding.mandate_id,
                    "as_of_date": request.as_of_date.isoformat(),
                    "reporting_currency": request.reporting_currency,
                    "exposure_currencies": sorted(request.exposure_currencies),
                    "instrument_types": sorted(request.instrument_types),
                    "integration_status": "not_ingested",
                }
            ),
            snapshot_id=(
                "external_eligible_hedge_instrument:"
                + request_fingerprint(
                    {
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "integration_status": "not_ingested",
                    }
                )
            ),
        ),
    )
