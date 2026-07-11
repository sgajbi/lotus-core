"""SQL adapter tests for DPM portfolio and tax-lot evidence."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.query_control_plane_service.app.infrastructure import (
    dpm_portfolio_state_sources,
)


def _session_returning_rows(*rows: object) -> MagicMock:
    result = MagicMock()
    result.all.return_value = list(rows)
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_tax_lot_read_is_bounded_ordered_and_keyset_paginated() -> None:
    lot = SimpleNamespace(
        portfolio_id="PB_1",
        security_id=" SEC_1 ",
        instrument_id=" INST_1 ",
        lot_id="LOT_2",
        open_quantity="12.5000000000",
        original_quantity="20.0000000000",
        acquisition_date=date(2026, 4, 2),
        lot_cost_base="1200.0000000000",
        lot_cost_local="1100.0000000000",
        source_transaction_id="TX_1",
        source_system="position_lot_state",
        calculation_policy_id="average_cost",
        calculation_policy_version="v1",
        updated_at=datetime(2026, 4, 10, tzinfo=UTC),
    )
    session = _session_returning_rows((lot, "SGD"))

    records = await dpm_portfolio_state_sources.SqlAlchemyDpmPortfolioStateReader(
        session
    ).list_portfolio_tax_lots(
        portfolio_id="PB_1",
        as_of_date=date(2026, 4, 10),
        security_ids=[" SEC_1 ", "SEC_1"],
        include_closed_lots=False,
        lot_status_filter=None,
        after_sort_key=(date(2026, 4, 1), "LOT_1"),
        limit=251,
    )

    assert records[0].security_id == "SEC_1"
    assert records[0].local_currency == "SGD"
    statement = session.execute.await_args.args[0]
    sql = str(statement)
    assert "position_lot_state.open_quantity >" in sql
    assert "position_lot_state.acquisition_date >" in sql
    assert "ORDER BY position_lot_state.acquisition_date ASC" in sql
    assert statement._limit_clause.value == 251


@pytest.mark.asyncio
async def test_closed_tax_lot_filter_is_explicit() -> None:
    session = _session_returning_rows()

    await dpm_portfolio_state_sources.SqlAlchemyDpmPortfolioStateReader(
        session
    ).list_portfolio_tax_lots(
        portfolio_id="PB_1",
        as_of_date=date(2026, 4, 10),
        security_ids=None,
        include_closed_lots=True,
        lot_status_filter="closed",
        after_sort_key=None,
        limit=10,
    )

    assert "position_lot_state.open_quantity <=" in str(session.execute.await_args.args[0])


@pytest.mark.asyncio
async def test_empty_normalized_security_filter_avoids_database_query() -> None:
    session = _session_returning_rows()

    records = await dpm_portfolio_state_sources.SqlAlchemyDpmPortfolioStateReader(
        session
    ).list_portfolio_tax_lots(
        portfolio_id="PB_1",
        as_of_date=date(2026, 4, 10),
        security_ids=[" ", ""],
        include_closed_lots=False,
        lot_status_filter=None,
        after_sort_key=None,
        limit=10,
    )

    assert records == []
    session.execute.assert_not_awaited()
