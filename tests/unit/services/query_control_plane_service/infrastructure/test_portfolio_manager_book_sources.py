"""Persistence-adapter tests for portfolio-manager book membership."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_manager_book_sources,
)


@pytest.mark.asyncio
async def test_reader_maps_portfolio_master_rows_to_domain_records() -> None:
    row = SimpleNamespace(
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_id="CIF_SG_GLOBAL_BAL_001",
        booking_center_code="Singapore",
        portfolio_type="DISCRETIONARY",
        status="ACTIVE",
        open_date=date(2025, 3, 31),
        close_date=None,
        base_currency="SGD",
        created_at=datetime(2026, 5, 3, 8, tzinfo=UTC),
        updated_at=datetime(2026, 5, 3, 9, tzinfo=UTC),
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    records = await portfolio_manager_book_sources.SqlAlchemyPortfolioManagerBookReader(
        session
    ).list_members(
        portfolio_manager_id="PM_SG_DPM_001",
        as_of_date=date(2026, 5, 3),
        booking_center_code="Singapore",
        portfolio_types=("DISCRETIONARY",),
        include_inactive=False,
    )

    assert records[0].portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert records[0].updated_at == datetime(2026, 5, 3, 9, tzinfo=UTC)
    statement = session.execute.await_args.args[0]
    sql = str(statement)
    assert "portfolios.advisor_id" in sql
    assert "portfolios.booking_center_code" in sql
    assert "portfolios.portfolio_type IN" in sql
    assert "portfolios.status" in sql
    assert "ORDER BY portfolios.portfolio_id ASC" in sql
