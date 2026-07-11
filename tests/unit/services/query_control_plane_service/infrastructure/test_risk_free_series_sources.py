"""SQL adapter tests for governed risk-free series windows."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.query_control_plane_service.app.infrastructure.risk_free_series_sources import (
    SqlAlchemyRiskFreeSeriesReader,
)


@pytest.mark.asyncio
async def test_query_normalizes_currency_and_ranks_one_row_per_business_date() -> None:
    evidence_at = datetime(2026, 4, 10, 10, tzinfo=UTC)
    row = SimpleNamespace(
        series_id="official",
        risk_free_curve_id="USD_SOFR",
        series_date=date(2026, 4, 10),
        value=Decimal("0.035"),
        value_convention="annualized_rate",
        day_count_convention="act_360",
        compounding_convention="simple",
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

    records = await SqlAlchemyRiskFreeSeriesReader(session).list_rates(
        currency=" usd ", start_date=date(2026, 4, 1), end_date=date(2026, 4, 10)
    )

    assert records[0].risk_free_curve_id == "USD_SOFR"
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "risk_free_series.series_currency = 'USD'" in sql
    assert "PARTITION BY risk_free_series.series_date" in sql
    assert "risk_free_series.source_timestamp DESC NULLS LAST" in sql
