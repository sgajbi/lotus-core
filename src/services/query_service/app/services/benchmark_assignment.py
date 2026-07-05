from __future__ import annotations

from datetime import date
from typing import Any

from ..dtos.reference_integration_dto import BenchmarkAssignmentResponse
from ..dtos.source_data_product_identity import stable_content_hash
from .reference_data_helpers import latest_reference_evidence_timestamp
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date


def build_benchmark_assignment_response(
    *,
    row: Any,
    as_of_date: date,
) -> BenchmarkAssignmentResponse:
    content_hash = stable_content_hash(
        {
            "product_name": "BenchmarkAssignment",
            "product_version": "v1",
            "portfolio_id": row.portfolio_id,
            "benchmark_id": row.benchmark_id,
            "as_of_date": as_of_date,
            "effective_from": row.effective_from,
            "effective_to": row.effective_to,
            "assignment_source": row.assignment_source,
            "assignment_status": row.assignment_status,
            "policy_pack_id": row.policy_pack_id,
            "source_system": row.source_system,
            "assignment_recorded_at": row.assignment_recorded_at,
            "assignment_version": int(row.assignment_version),
            "latest_evidence_timestamp": latest_reference_evidence_timestamp([row]),
        }
    )
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
            content_hash=content_hash,
            source_refs=[
                "lotus-core://source/BenchmarkAssignment/"
                f"{row.portfolio_id}/{as_of_date.isoformat()}"
            ],
            lineage={
                "source_owner": "lotus-core",
                "source_product": "BenchmarkAssignment",
                "benchmark_id": row.benchmark_id,
                "assignment_version": str(int(row.assignment_version)),
            },
            use_content_hash_as_source_batch_fingerprint=True,
        ),
    )
