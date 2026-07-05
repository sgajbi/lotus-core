from datetime import UTC, date, datetime
from types import SimpleNamespace

from src.services.query_service.app.services.benchmark_assignment import (
    build_benchmark_assignment_response,
)


def test_build_benchmark_assignment_response_maps_assignment_and_runtime_metadata() -> None:
    assignment_recorded_at = datetime(2026, 1, 31, 9, 15, tzinfo=UTC)
    updated_at = datetime(2026, 1, 31, 10, 30, tzinfo=UTC)
    row = SimpleNamespace(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        assignment_source="benchmark_policy_engine",
        assignment_status="active",
        policy_pack_id="policy_pack_wm_v1",
        source_system="lotus-manage",
        assignment_recorded_at=assignment_recorded_at,
        assignment_version="3",
        updated_at=updated_at,
    )

    response = build_benchmark_assignment_response(
        row=row,
        as_of_date=date(2026, 1, 31),
    )

    assert response.product_name == "BenchmarkAssignment"
    assert response.portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert response.benchmark_id == "BMK_GLOBAL_BALANCED_60_40"
    assert response.as_of_date == date(2026, 1, 31)
    assert response.effective_from == date(2026, 1, 1)
    assert response.effective_to is None
    assert response.assignment_source == "benchmark_policy_engine"
    assert response.assignment_status == "active"
    assert response.policy_pack_id == "policy_pack_wm_v1"
    assert response.source_system == "lotus-manage"
    assert response.assignment_recorded_at == assignment_recorded_at
    assert response.assignment_version == 3
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == updated_at
    assert response.content_hash.startswith("sha256:")
    assert response.source_digest == response.content_hash
    assert response.source_refs == [
        "lotus-core://source/BenchmarkAssignment/PB_SG_GLOBAL_BAL_001/2026-01-31"
    ]
    assert response.lineage == {
        "source_owner": "lotus-core",
        "source_product": "BenchmarkAssignment",
        "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
        "assignment_version": "3",
    }
    assert response.source_evidence_current is True

    repeat_response = build_benchmark_assignment_response(
        row=row,
        as_of_date=date(2026, 1, 31),
    )
    assert repeat_response.content_hash == response.content_hash
