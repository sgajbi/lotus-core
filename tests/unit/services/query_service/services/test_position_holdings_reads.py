from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import PositionHistory

from src.services.query_service.app.dtos.position_dto import Position
from src.services.query_service.app.dtos.valuation_dto import ValuationData
from src.services.query_service.app.services.position_holdings_reads import (
    fallback_holdings_valuation_map,
    holdings_position_source_rows,
    holdings_support_evidence,
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


async def test_holdings_support_evidence_applies_held_since_before_price_dates() -> None:
    repository = AsyncMock()
    call_order: list[str] = []

    async def get_held_since_dates(
        *,
        portfolio_id: str,
        security_epoch_pairs: list[tuple[str, int]],
    ) -> dict[tuple[str, int], date]:
        call_order.append("held_since")
        assert portfolio_id == "P1"
        assert security_epoch_pairs == [("SEC_A", 2)]
        return {("SEC_A", 2): date(2024, 12, 31)}

    async def get_latest_market_price_dates(
        *,
        security_ids: list[str],
        as_of_date: date,
    ) -> dict[str, date]:
        call_order.append("price_dates")
        assert security_ids == ["SEC_A"]
        assert as_of_date == date(2025, 1, 1)
        return {"SEC_A": date(2025, 1, 1)}

    repository.get_held_since_dates.side_effect = get_held_since_dates
    repository.get_latest_market_price_dates.side_effect = get_latest_market_price_dates
    position = Position(
        security_id=" SEC_A ",
        quantity=Decimal("1"),
        cost_basis=Decimal("100"),
        position_date=date(2025, 1, 1),
        instrument_name="Security A",
        asset_class="Equity",
        valuation=ValuationData(market_price=Decimal("10")),
    )

    latest_market_price_dates = await holdings_support_evidence(
        repository=repository,
        portfolio_id="P1",
        positions=[position],
        held_since_requests=[(0, "SEC_A", 2, date(2025, 1, 1))],
        response_as_of_date=date(2025, 1, 1),
    )

    assert latest_market_price_dates == {"SEC_A": date(2025, 1, 1)}
    assert position.held_since_date == date(2024, 12, 31)
    assert call_order == ["held_since", "price_dates"]


async def test_holdings_support_evidence_skips_held_since_when_no_requests() -> None:
    repository = AsyncMock()
    repository.get_latest_market_price_dates.return_value = {}
    cash_position = Position(
        security_id="CASH_A",
        quantity=Decimal("1"),
        cost_basis=Decimal("100"),
        position_date=date(2025, 1, 1),
        instrument_name="Cash",
        asset_class="Cash",
        valuation=ValuationData(market_price=Decimal("1")),
    )

    latest_market_price_dates = await holdings_support_evidence(
        repository=repository,
        portfolio_id="P1",
        positions=[cash_position],
        held_since_requests=[],
        response_as_of_date=date(2025, 1, 1),
    )

    assert latest_market_price_dates == {}
    repository.get_held_since_dates.assert_not_awaited()
    repository.get_latest_market_price_dates.assert_awaited_once_with(
        security_ids=[],
        as_of_date=date(2025, 1, 1),
    )
