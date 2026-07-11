"""Application use case for effective portfolio benchmark assignment evidence."""

from collections.abc import Callable
from datetime import datetime

from portfolio_common.source_data_product_metadata import (
    source_data_product_runtime_metadata,
    stable_content_hash,
)

from ..contracts.benchmark_assignment import (
    BenchmarkAssignmentRequest,
    BenchmarkAssignmentResponse,
)
from ..domain.benchmark_assignment import BenchmarkAssignmentEvidence
from ..ports.benchmark_assignment import BenchmarkAssignmentReader


class BenchmarkAssignmentService:
    """Resolve and map benchmark assignments without persistence leakage."""

    def __init__(
        self,
        *,
        reader: BenchmarkAssignmentReader,
        clock: Callable[[], datetime],
    ) -> None:
        self._reader = reader
        self._clock = clock

    async def resolve(
        self,
        *,
        portfolio_id: str,
        request: BenchmarkAssignmentRequest,
    ) -> BenchmarkAssignmentResponse | None:
        evidence = await self._reader.resolve(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
        )
        if evidence is None:
            return None
        return build_benchmark_assignment_response(
            evidence=evidence,
            request=request,
            generated_at=self._clock(),
        )


def build_benchmark_assignment_response(
    *,
    evidence: BenchmarkAssignmentEvidence,
    request: BenchmarkAssignmentRequest,
    generated_at: datetime,
) -> BenchmarkAssignmentResponse:
    """Build deterministic source proof while excluding response-generation time from identity."""

    latest_evidence = max(
        timestamp
        for timestamp in (
            evidence.assignment_recorded_at,
            evidence.updated_at,
            evidence.created_at,
        )
        if timestamp is not None
    )
    content_hash = stable_content_hash(
        {
            "product_name": "BenchmarkAssignment",
            "product_version": "v1",
            "portfolio_id": evidence.portfolio_id,
            "benchmark_id": evidence.benchmark_id,
            "as_of_date": request.as_of_date,
            "effective_from": evidence.effective_from,
            "effective_to": evidence.effective_to,
            "assignment_source": evidence.assignment_source,
            "assignment_status": evidence.assignment_status,
            "policy_pack_id": evidence.policy_pack_id,
            "source_system": evidence.source_system,
            "assignment_recorded_at": evidence.assignment_recorded_at,
            "assignment_version": evidence.assignment_version,
            "latest_evidence_timestamp": latest_evidence,
        }
    )
    metadata = source_data_product_runtime_metadata(
        generated_at=generated_at,
        as_of_date=request.as_of_date,
        tenant_id=request.policy_context.tenant_id if request.policy_context else None,
        data_quality_status="COMPLETE",
        latest_evidence_timestamp=latest_evidence,
        content_hash=content_hash,
        source_refs=[
            "lotus-core://source/BenchmarkAssignment/"
            f"{evidence.portfolio_id}/{request.as_of_date.isoformat()}"
        ],
        lineage={
            "source_owner": "lotus-core",
            "source_product": "BenchmarkAssignment",
            "benchmark_id": evidence.benchmark_id,
            "assignment_version": str(evidence.assignment_version),
        },
        use_content_hash_as_source_batch_fingerprint=True,
    )
    return BenchmarkAssignmentResponse(
        portfolio_id=evidence.portfolio_id,
        benchmark_id=evidence.benchmark_id,
        effective_from=evidence.effective_from,
        effective_to=evidence.effective_to,
        assignment_source=evidence.assignment_source,
        assignment_status=evidence.assignment_status,
        policy_pack_id=evidence.policy_pack_id,
        source_system=evidence.source_system,
        assignment_recorded_at=evidence.assignment_recorded_at,
        assignment_version=evidence.assignment_version,
        **metadata,
    )
