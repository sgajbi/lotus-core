from __future__ import annotations

from typing import Any

from ..dtos.reference_integration_dto import (
    ExternalHedgePolicyRequest,
    ExternalHedgePolicyResponse,
    ExternalHedgePolicySupportability,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from .request_fingerprint import request_fingerprint

EXTERNAL_HEDGE_POLICY_MISSING_FAMILIES = ["external_hedge_policy"]

EXTERNAL_HEDGE_POLICY_BLOCKED_CAPABILITIES = [
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
]


async def resolve_external_hedge_policy_response(
    *,
    repository: Any,
    portfolio_id: str,
    request: ExternalHedgePolicyRequest,
) -> ExternalHedgePolicyResponse | None:
    binding = await repository.resolve_discretionary_mandate_binding(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        mandate_id=request.mandate_id,
    )
    if binding is None:
        return None

    return build_external_hedge_policy_response(
        portfolio_id=portfolio_id,
        binding=binding,
        request=request,
    )


def build_external_hedge_policy_response(
    *,
    portfolio_id: str,
    binding: Any,
    request: ExternalHedgePolicyRequest,
) -> ExternalHedgePolicyResponse:
    return ExternalHedgePolicyResponse(
        portfolio_id=portfolio_id,
        client_id=binding.client_id,
        mandate_id=binding.mandate_id,
        reporting_currency=request.reporting_currency,
        exposure_currencies=request.exposure_currencies,
        policy_rules=[],
        supportability=ExternalHedgePolicySupportability(
            policy_rule_count=0,
            missing_data_families=EXTERNAL_HEDGE_POLICY_MISSING_FAMILIES,
            blocked_capabilities=EXTERNAL_HEDGE_POLICY_BLOCKED_CAPABILITIES,
        ),
        lineage={
            "source_system": "external-bank-treasury",
            "source_table": "not_ingested",
            "contract_version": "rfc_039_external_hedge_policy_v1",
            "integration_status": "not_ingested",
            "runtime_posture": "fail_closed",
            "non_claims": ",".join(EXTERNAL_HEDGE_POLICY_BLOCKED_CAPABILITIES),
        },
        **source_data_product_runtime_metadata(
            as_of_date=request.as_of_date,
            tenant_id=request.tenant_id,
            data_quality_status="MISSING",
            latest_evidence_timestamp=None,
            source_batch_fingerprint=None,
            snapshot_id=(
                "external_hedge_policy:"
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
