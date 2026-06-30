from __future__ import annotations

from typing import Any, Literal

from ..dtos.reference_integration_dto import (
    ClientIncomeNeedsScheduleRequest,
    ClientIncomeNeedsScheduleResponse,
    ClientIncomeNeedsScheduleSupportability,
)
from ..dtos.source_data_product_identity import source_data_product_runtime_metadata
from .reference_data_helpers import latest_reference_evidence_timestamp
from .reference_data_mappers import client_income_needs_schedule_entry
from .request_fingerprint import request_fingerprint


async def resolve_client_income_needs_schedule_response(
    *,
    repository: Any,
    portfolio_id: str,
    request: ClientIncomeNeedsScheduleRequest,
) -> ClientIncomeNeedsScheduleResponse | None:
    binding = await repository.resolve_discretionary_mandate_binding(
        portfolio_id=portfolio_id,
        as_of_date=request.as_of_date,
        mandate_id=request.mandate_id,
    )
    if binding is None:
        return None

    rows = await repository.list_client_income_needs_schedules(
        portfolio_id=portfolio_id,
        client_id=binding.client_id,
        as_of_date=request.as_of_date,
        mandate_id=binding.mandate_id,
        include_inactive_schedules=request.include_inactive_schedules,
    )
    return build_client_income_needs_schedule_response(
        portfolio_id=portfolio_id,
        binding=binding,
        request=request,
        rows=rows,
    )


def build_client_income_needs_schedule_response(
    *,
    portfolio_id: str,
    binding: Any,
    request: ClientIncomeNeedsScheduleRequest,
    rows: list[Any],
) -> ClientIncomeNeedsScheduleResponse:
    entries = [client_income_needs_schedule_entry(row) for row in rows]
    supportability_state: Literal["READY", "INCOMPLETE", "UNAVAILABLE"] = "READY"
    supportability_reason = "CLIENT_INCOME_NEEDS_SCHEDULE_READY"
    missing_data_families: list[str] = []
    if not rows:
        supportability_state = "INCOMPLETE"
        supportability_reason = "CLIENT_INCOME_NEEDS_SCHEDULE_EMPTY"
        missing_data_families.append("client_income_needs_schedule")

    return ClientIncomeNeedsScheduleResponse(
        portfolio_id=portfolio_id,
        client_id=binding.client_id,
        mandate_id=binding.mandate_id,
        schedules=entries,
        supportability=ClientIncomeNeedsScheduleSupportability(
            state=supportability_state,
            reason=supportability_reason,
            schedule_count=len(entries),
            missing_data_families=missing_data_families,
        ),
        lineage={
            "source_system": "lotus-core-query-service",
            "source_table": "client_income_needs_schedules,portfolio_mandate_bindings",
            "contract_version": "rfc_042_client_income_needs_schedule_v1",
        },
        **source_data_product_runtime_metadata(
            as_of_date=request.as_of_date,
            tenant_id=request.tenant_id,
            data_quality_status=("ACCEPTED" if rows else "MISSING"),
            latest_evidence_timestamp=latest_reference_evidence_timestamp([binding], rows),
            source_batch_fingerprint=None,
            snapshot_id=(
                "client_income_needs_schedule:"
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
