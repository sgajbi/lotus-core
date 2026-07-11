"""SQL adapter tests for benchmark assignment evidence."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.query_control_plane_service.app.infrastructure import benchmark_assignment_sources


@pytest.mark.asyncio
async def test_reader_applies_effective_date_and_deterministic_tie_breaking() -> None:
    row = SimpleNamespace(
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
        updated_at=datetime(2026, 4, 10, 10, tzinfo=UTC),
    )
    result = MagicMock()
    result.scalars.return_value.first.return_value = row
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    evidence = await benchmark_assignment_sources.SqlAlchemyBenchmarkAssignmentReader(
        session
    ).resolve(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        as_of_date=date(2026, 4, 10),
    )

    assert evidence is not None
    assert evidence.assignment_version == 3
    sql = str(session.execute.await_args.args[0])
    assert "portfolio_benchmark_assignments.effective_from <=" in sql
    assert "portfolio_benchmark_assignments.effective_to IS NULL" in sql
    assert "portfolio_benchmark_assignments.assignment_recorded_at DESC" in sql
    assert "portfolio_benchmark_assignments.assignment_version DESC" in sql
    assert "portfolio_benchmark_assignments.id DESC" in sql
