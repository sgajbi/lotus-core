from __future__ import annotations

from ..dtos.reference_integration_dto import (
    ExternalFXForwardCurveRequest,
    ExternalFXForwardCurveResponse,
    ExternalFXForwardCurveSupportability,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from .request_fingerprint import request_fingerprint

EXTERNAL_FX_FORWARD_CURVE_MISSING_FAMILIES = ["external_fx_forward_curve"]

EXTERNAL_FX_FORWARD_CURVE_BLOCKED_CAPABILITIES = [
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
]


def build_external_fx_forward_curve_response(
    *,
    request: ExternalFXForwardCurveRequest,
) -> ExternalFXForwardCurveResponse:
    return ExternalFXForwardCurveResponse(
        reporting_currency=request.reporting_currency,
        currency_pairs=request.currency_pairs,
        tenors=request.tenors,
        curve_points=[],
        supportability=ExternalFXForwardCurveSupportability(
            curve_point_count=0,
            missing_data_families=EXTERNAL_FX_FORWARD_CURVE_MISSING_FAMILIES,
            blocked_capabilities=EXTERNAL_FX_FORWARD_CURVE_BLOCKED_CAPABILITIES,
        ),
        lineage={
            "source_system": "external-bank-treasury",
            "source_table": "not_ingested",
            "contract_version": "rfc_039_external_fx_forward_curve_v1",
            "integration_status": "not_ingested",
            "runtime_posture": "fail_closed",
            "non_claims": ",".join(EXTERNAL_FX_FORWARD_CURVE_BLOCKED_CAPABILITIES),
        },
        **source_data_product_runtime_metadata(
            as_of_date=request.as_of_date,
            tenant_id=request.tenant_id,
            data_quality_status="MISSING",
            latest_evidence_timestamp=None,
            source_batch_fingerprint=request_fingerprint(
                {
                    "product": "ExternalFXForwardCurve",
                    "as_of_date": request.as_of_date.isoformat(),
                    "reporting_currency": request.reporting_currency,
                    "currency_pairs": sorted(request.currency_pairs),
                    "tenors": sorted(request.tenors),
                    "integration_status": "not_ingested",
                }
            ),
            snapshot_id=(
                "external_fx_forward_curve:"
                + request_fingerprint(
                    {
                        "as_of_date": request.as_of_date.isoformat(),
                        "currency_pairs": sorted(request.currency_pairs),
                        "tenors": sorted(request.tenors),
                        "integration_status": "not_ingested",
                    }
                )
            ),
        ),
    )
