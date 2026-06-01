from __future__ import annotations

from typing import Any

from ..dtos.reference_integration_dto import (
    ExternalOrderExecutionAcknowledgementRequest,
    ExternalOrderExecutionAcknowledgementResponse,
    ExternalOrderExecutionAcknowledgementSupportability,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from .request_fingerprint import request_fingerprint

EXTERNAL_ORDER_ACK_MISSING_FAMILIES = ["external_oms_order_execution_acknowledgement"]

EXTERNAL_ORDER_ACK_BLOCKED_CAPABILITIES = [
    "order_generation",
    "venue_routing",
    "best_execution",
    "oms_acknowledgement",
    "fills",
    "settlement",
    "execution_status_certification",
    "autonomous_execution_action",
]


async def resolve_external_order_execution_acknowledgement_response(
    *,
    repository: Any,
    portfolio_id: str,
    request: ExternalOrderExecutionAcknowledgementRequest,
) -> ExternalOrderExecutionAcknowledgementResponse | None:
    binding = await repository.resolve_discretionary_mandate_binding(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        mandate_id=request.mandate_id,
    )
    if binding is None:
        return None

    return build_external_order_execution_acknowledgement_response(
        portfolio_id=portfolio_id,
        binding=binding,
        request=request,
    )


def build_external_order_execution_acknowledgement_response(
    *,
    portfolio_id: str,
    binding: Any,
    request: ExternalOrderExecutionAcknowledgementRequest,
) -> ExternalOrderExecutionAcknowledgementResponse:
    return ExternalOrderExecutionAcknowledgementResponse(
        portfolio_id=portfolio_id,
        client_id=binding.client_id,
        mandate_id=binding.mandate_id,
        execution_intent_id=request.execution_intent_id,
        order_reference_ids=request.order_reference_ids,
        acknowledgements=[],
        supportability=ExternalOrderExecutionAcknowledgementSupportability(
            acknowledgement_count=0,
            missing_data_families=EXTERNAL_ORDER_ACK_MISSING_FAMILIES,
            blocked_capabilities=EXTERNAL_ORDER_ACK_BLOCKED_CAPABILITIES,
        ),
        lineage={
            "source_system": "external-bank-oms",
            "source_table": "not_ingested",
            "contract_version": "rfc_042_external_order_execution_acknowledgement_v1",
            "integration_status": "not_ingested",
            "runtime_posture": "fail_closed",
            "non_claims": ",".join(EXTERNAL_ORDER_ACK_BLOCKED_CAPABILITIES),
        },
        **source_data_product_runtime_metadata(
            as_of_date=request.as_of_date,
            tenant_id=request.tenant_id,
            data_quality_status="MISSING",
            latest_evidence_timestamp=None,
            source_batch_fingerprint=request_fingerprint(
                {
                    "product": "ExternalOrderExecutionAcknowledgement",
                    "portfolio_id": portfolio_id,
                    "client_id": binding.client_id,
                    "mandate_id": binding.mandate_id,
                    "as_of_date": request.as_of_date.isoformat(),
                    "execution_intent_id": request.execution_intent_id,
                    "order_reference_ids": sorted(request.order_reference_ids),
                    "integration_status": "not_ingested",
                }
            ),
            snapshot_id=(
                "external_order_execution_acknowledgement:"
                + request_fingerprint(
                    {
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "as_of_date": request.as_of_date.isoformat(),
                        "execution_intent_id": request.execution_intent_id,
                        "order_reference_ids": sorted(request.order_reference_ids),
                        "integration_status": "not_ingested",
                    }
                )
            ),
        ),
    )
