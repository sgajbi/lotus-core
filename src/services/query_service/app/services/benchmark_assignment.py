from __future__ import annotations

from datetime import date
from typing import Any

from ..dtos.reference_integration_dto import BenchmarkAssignmentResponse
from .reference_data_helpers import latest_reference_evidence_timestamp
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date


def build_benchmark_assignment_response(
    *,
    row: Any,
    as_of_date: date,
) -> BenchmarkAssignmentResponse:
    return BenchmarkAssignmentResponse(
        portfolio_id=row.portfolio_id,
        benchmark_id=row.benchmark_id,
        as_of_date=as_of_date,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        assignment_source=row.assignment_source,
        assignment_status=row.assignment_status,
        policy_pack_id=row.policy_pack_id,
        source_system=row.source_system,
        assignment_recorded_at=row.assignment_recorded_at,
        assignment_version=int(row.assignment_version),
        **source_product_runtime_metadata_without_as_of_date(
            as_of_date,
            data_quality_status="COMPLETE",
            latest_evidence_timestamp=latest_reference_evidence_timestamp([row]),
        ),
    )
