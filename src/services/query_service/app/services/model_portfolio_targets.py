from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..dtos.reference_integration_dto import (
    ModelPortfolioSupportability,
    ModelPortfolioTargetRequest,
    ModelPortfolioTargetResponse,
)
from .reference_data_helpers import (
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
)
from .reference_data_mappers import model_portfolio_target_row
from .source_data_runtime import source_product_runtime_metadata


async def resolve_model_portfolio_target_response(
    *,
    repository: Any,
    model_portfolio_id: str,
    request: ModelPortfolioTargetRequest,
) -> ModelPortfolioTargetResponse | None:
    definition = await repository.resolve_model_portfolio_definition(
        model_portfolio_id=model_portfolio_id,
        as_of_date=request.as_of_date,
    )
    if definition is None:
        return None

    targets = await repository.list_model_portfolio_targets(
        model_portfolio_id=model_portfolio_id,
        model_portfolio_version=definition.model_portfolio_version,
        as_of_date=request.as_of_date,
        include_inactive_targets=request.include_inactive_targets,
    )
    return build_model_portfolio_target_response(
        definition=definition,
        request=request,
        target_rows=targets,
    )


def build_model_portfolio_target_response(
    *,
    definition: Any,
    request: ModelPortfolioTargetRequest,
    target_rows: list[Any],
) -> ModelPortfolioTargetResponse:
    targets = [model_portfolio_target_row(row) for row in target_rows]
    total_weight = sum((row.target_weight for row in targets), Decimal("0"))

    supportability_state = "READY"
    supportability_reason = "MODEL_TARGETS_READY"
    if not targets:
        supportability_state = "INCOMPLETE"
        supportability_reason = "MODEL_TARGETS_EMPTY"
    elif total_weight != Decimal("1.0000000000"):
        supportability_state = "DEGRADED"
        supportability_reason = "MODEL_TARGET_WEIGHTS_NOT_ONE"

    return ModelPortfolioTargetResponse(
        model_portfolio_id=definition.model_portfolio_id,
        model_portfolio_version=definition.model_portfolio_version,
        display_name=definition.display_name,
        base_currency=definition.base_currency,
        risk_profile=definition.risk_profile,
        mandate_type=definition.mandate_type,
        rebalance_frequency=definition.rebalance_frequency,
        approval_status=definition.approval_status,
        approved_at=definition.approved_at,
        effective_from=definition.effective_from,
        effective_to=definition.effective_to,
        targets=targets,
        supportability=ModelPortfolioSupportability(
            state=supportability_state,
            reason=supportability_reason,
            target_count=len(targets),
            total_target_weight=total_weight,
        ),
        lineage={
            "source_system": definition.source_system or "unknown",
            "source_record_id": definition.source_record_id or "unknown",
            "contract_version": "rfc_087_v1",
        },
        **source_product_runtime_metadata(
            request.as_of_date,
            data_quality_status=market_reference_data_quality_status(
                target_rows,
                required_count=len(targets),
            ),
            latest_evidence_timestamp=latest_reference_evidence_timestamp(
                [definition],
                target_rows,
            ),
        ),
    )
