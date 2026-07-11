"""SQL adapter tests for governed benchmark return series windows."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.query_control_plane_service.app.infrastructure import (
    benchmark_return_series_sources,
)


@pytest.mark.asyncio
async def test_query_ranks_one_canonical_row_per_benchmark_business_date() -> None:
    evidence_at = datetime(2026, 4, 10, 10, tzinfo=UTC)
    row = SimpleNamespace(
        series_id="vendor-series",
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
        series_date=date(2026, 4, 10),
        benchmark_return=Decimal("0.0019"),
        return_period="1d",
        return_convention="total_return_index",
        series_currency="USD",
        quality_status="accepted",
        source_timestamp=evidence_at,
        source_vendor="provider",
        source_record_id="source:1",
        created_at=evidence_at,
        updated_at=evidence_at,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    records = await benchmark_return_series_sources.SqlAlchemyBenchmarkReturnSeriesReader(
        session
    ).list_returns(
        benchmark_id=" BMK_GLOBAL_BALANCED_60_40 ",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 10),
    )

    assert records[0].observed_at == evidence_at
    sql = str(session.execute.await_args.args[0])
    assert "PARTITION BY benchmark_return_series.benchmark_id" in sql
    assert "benchmark_return_series.series_date" in sql
    assert "benchmark_return_series.source_timestamp DESC NULLS LAST" in sql
    assert "ORDER BY benchmark_return_series.series_date ASC" in sql
