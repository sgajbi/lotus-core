"""Application tests for effective benchmark assignment evidence."""

from datetime import UTC, date, datetime

import pytest

from src.services.query_control_plane_service.app.application.benchmark_assignment import (
    BenchmarkAssignmentService,
    build_benchmark_assignment_response,
)
from src.services.query_control_plane_service.app.contracts.benchmark_assignment import (
    BenchmarkAssignmentPolicyContext,
    BenchmarkAssignmentRequest,
)
from src.services.query_control_plane_service.app.domain.benchmark_assignment import (
    BenchmarkAssignmentEvidence,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)


def _evidence() -> BenchmarkAssignmentEvidence:
    return BenchmarkAssignmentEvidence(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        assignment_source="benchmark_policy_engine",
        assignment_status="active",
        policy_pack_id="policy_pack_wm_v1",
        source_system="lotus-manage",
        assignment_recorded_at=datetime(2026, 4, 10, 9, tzinfo=UTC),
        assignment_version=3,
        created_at=datetime(2026, 4, 10, 8, tzinfo=UTC),
        updated_at=EVIDENCE_AT,
    )


def _request() -> BenchmarkAssignmentRequest:
    return BenchmarkAssignmentRequest(
        as_of_date=date(2026, 4, 10),
        reporting_currency="SGD",
        policy_context=BenchmarkAssignmentPolicyContext(tenant_id="tenant-sg"),
    )


def test_response_exposes_current_deterministic_source_proof() -> None:
    response = build_benchmark_assignment_response(
        evidence=_evidence(),
        request=_request(),
        generated_at=GENERATED_AT,
    )

    assert response.product_name == "BenchmarkAssignment"
    assert response.tenant_id == "tenant-sg"
    assert response.latest_evidence_timestamp == EVIDENCE_AT
    assert response.source_evidence_current is True
    assert response.freshness_status == "CURRENT"
    assert response.source_batch_fingerprint == response.content_hash == response.source_digest
    assert response.source_refs == [
        "lotus-core://source/BenchmarkAssignment/PB_SG_GLOBAL_BAL_001/2026-04-10"
    ]
    assert response.source_lineage["assignment_version"] == "3"


def test_content_hash_excludes_generated_at() -> None:
    first = build_benchmark_assignment_response(
        evidence=_evidence(), request=_request(), generated_at=GENERATED_AT
    )
    second = build_benchmark_assignment_response(
        evidence=_evidence(),
        request=_request(),
        generated_at=datetime(2026, 4, 10, 13, tzinfo=UTC),
    )

    assert first.generated_at != second.generated_at
    assert first.content_hash == second.content_hash


@pytest.mark.asyncio
async def test_service_resolves_via_port_and_preserves_request_scope() -> None:
    class Reader:
        async def resolve(self, **kwargs: object) -> BenchmarkAssignmentEvidence:
            self.kwargs = kwargs
            return _evidence()

    reader = Reader()
    response = await BenchmarkAssignmentService(
        reader=reader,  # type: ignore[arg-type]
        clock=lambda: GENERATED_AT,
    ).resolve(portfolio_id="PB_SG_GLOBAL_BAL_001", request=_request())

    assert reader.kwargs == {
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "as_of_date": date(2026, 4, 10),
    }
    assert response is not None
    assert response.benchmark_id == "BMK_GLOBAL_BALANCED_60_40"
