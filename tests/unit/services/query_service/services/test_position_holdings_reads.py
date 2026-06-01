from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import PositionHistory

from src.services.query_service.app.services.position_holdings_reads import (
    fallback_holdings_valuation_map,
    holdings_position_source_rows,
)

pytestmark = pytest.mark.asyncio


async def test_holdings_position_source_rows_reads_effective_as_of_scope() -> None:
    repository = AsyncMock()
    repository.get_latest_positions_by_portfolio_as_of_date.return_value = ["snapshot"]
    repository.get_latest_position_history_by_portfolio_as_of_date.return_value = ["history"]

    snapshot_rows, history_rows = await holdings_position_source_rows(
        repository=repository,
        portfolio_id="P1",
        effective_as_of_date=date(2025, 1, 1),
    )

    assert snapshot_rows == ["snapshot"]
    assert history_rows == ["history"]
    repository.get_latest_positions_by_portfolio_as_of_date.assert_awaited_once_with(
        "P1", date(2025, 1, 1)
    )
    repository.get_latest_position_history_by_portfolio_as_of_date.assert_awaited_once_with(
        "P1", date(2025, 1, 1)
    )
    repository.get_latest_positions_by_portfolio.assert_not_awaited()
    repository.get_latest_position_history_by_portfolio.assert_not_awaited()


async def test_holdings_position_source_rows_reads_unbounded_latest_scope() -> None:
    repository = AsyncMock()
    repository.get_latest_positions_by_portfolio.return_value = ["snapshot"]
    repository.get_latest_position_history_by_portfolio.return_value = ["history"]

    snapshot_rows, history_rows = await holdings_position_source_rows(
        repository=repository,
        portfolio_id="P1",
        effective_as_of_date=None,
    )

    assert snapshot_rows == ["snapshot"]
    assert history_rows == ["history"]
    repository.get_latest_positions_by_portfolio.assert_awaited_once_with("P1")
    repository.get_latest_position_history_by_portfolio.assert_awaited_once_with("P1")
    repository.get_latest_positions_by_portfolio_as_of_date.assert_not_awaited()
    repository.get_latest_position_history_by_portfolio_as_of_date.assert_not_awaited()


async def test_fallback_holdings_valuation_map_skips_unneeded_repository_read() -> None:
    repository = AsyncMock()

    fallback_map = await fallback_holdings_valuation_map(
        repository=repository,
        portfolio_id="P1",
        effective_as_of_date=date(2025, 1, 1),
        db_results=[],
        history_supplements=[],
        snapshot_security_ids=set(),
    )

    assert fallback_map == {}
    repository.get_latest_snapshot_valuation_map_as_of_date.assert_not_awaited()
    repository.get_latest_snapshot_valuation_map.assert_not_awaited()


async def test_fallback_holdings_valuation_map_reads_effective_as_of_scope() -> None:
    repository = AsyncMock()
    repository.get_latest_snapshot_valuation_map_as_of_date.return_value = {
        "HIST_A": {"market_value": Decimal("100")}
    }
    history_row = PositionHistory(security_id=" HIST_A ")

    fallback_map = await fallback_holdings_valuation_map(
        repository=repository,
        portfolio_id="P1",
        effective_as_of_date=date(2025, 1, 1),
        db_results=[(history_row, None, None)],
        history_supplements=[(history_row, None, None)],
        snapshot_security_ids=set(),
    )

    assert fallback_map == {"HIST_A": {"market_value": Decimal("100")}}
    repository.get_latest_snapshot_valuation_map_as_of_date.assert_awaited_once_with(
        "P1", date(2025, 1, 1), security_ids=["HIST_A"]
    )
    repository.get_latest_snapshot_valuation_map.assert_not_awaited()


async def test_fallback_holdings_valuation_map_reads_unbounded_latest_scope() -> None:
    repository = AsyncMock()
    repository.get_latest_snapshot_valuation_map.return_value = {
        "HIST_A": {"market_value": Decimal("100")}
    }
    history_row = PositionHistory(security_id=" HIST_A ")

    fallback_map = await fallback_holdings_valuation_map(
        repository=repository,
        portfolio_id="P1",
        effective_as_of_date=None,
        db_results=[(history_row, None, None)],
        history_supplements=[(history_row, None, None)],
        snapshot_security_ids=set(),
    )

    assert fallback_map == {"HIST_A": {"market_value": Decimal("100")}}
    repository.get_latest_snapshot_valuation_map.assert_awaited_once_with(
        "P1", security_ids=["HIST_A"]
    )
    repository.get_latest_snapshot_valuation_map_as_of_date.assert_not_awaited()
