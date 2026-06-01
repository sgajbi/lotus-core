from __future__ import annotations

from typing import Any, Literal

from ..dtos.reference_integration_dto import (
    LiquidityReserveRequirementRequest,
    LiquidityReserveRequirementResponse,
    LiquidityReserveRequirementSupportability,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from .reference_data_helpers import latest_reference_evidence_timestamp
from .reference_data_mappers import liquidity_reserve_requirement_entry
from .request_fingerprint import request_fingerprint


def build_liquidity_reserve_requirement_response(
    *,
    portfolio_id: str,
    binding: Any,
    request: LiquidityReserveRequirementRequest,
    rows: list[Any],
) -> LiquidityReserveRequirementResponse:
    entries = [liquidity_reserve_requirement_entry(row) for row in rows]
    supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
    supportability_reason = "LIQUIDITY_RESERVE_REQUIREMENT_READY"
    missing_data_families: list[str] = []
    if not rows:
        supportability_state = "INCOMPLETE"
        supportability_reason = "LIQUIDITY_RESERVE_REQUIREMENT_EMPTY"
        missing_data_families.append("liquidity_reserve_requirement")

    return LiquidityReserveRequirementResponse(
        portfolio_id=portfolio_id,
        client_id=binding.client_id,
        mandate_id=binding.mandate_id,
        requirements=entries,
        supportability=LiquidityReserveRequirementSupportability(
            state=supportability_state,
            reason=supportability_reason,
            requirement_count=len(entries),
            missing_data_families=missing_data_families,
        ),
        lineage={
            "source_system": "lotus-core-query-service",
            "source_table": "liquidity_reserve_requirements,portfolio_mandate_bindings",
            "contract_version": "rfc_042_liquidity_reserve_requirement_v1",
        },
        **source_data_product_runtime_metadata(
            as_of_date=request.as_of_date,
            tenant_id=request.tenant_id,
            data_quality_status=("ACCEPTED" if rows else "MISSING"),
            latest_evidence_timestamp=latest_reference_evidence_timestamp([binding], rows),
            source_batch_fingerprint=request_fingerprint(
                {
                    "product": "LiquidityReserveRequirement",
                    "portfolio_id": portfolio_id,
                    "client_id": binding.client_id,
                    "mandate_id": binding.mandate_id,
                    "as_of_date": request.as_of_date.isoformat(),
                    "row_count": len(rows),
                }
            ),
            snapshot_id=(
                "liquidity_reserve_requirement:"
                + request_fingerprint(
                    {
                        "portfolio_id": portfolio_id,
                        "client_id": binding.client_id,
                        "as_of_date": request.as_of_date.isoformat(),
                    }
                )
            ),
        ),
    )
