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


def _lot(*, security_id: str, lot_id: str, acquisition_date: date) -> SimpleNamespace:
    return SimpleNamespace(
        portfolio_id="PB_1",
        security_id=security_id,
        instrument_id=security_id,
        lot_id=lot_id,
        open_quantity="1.0000000000",
        original_quantity="1.0000000000",
        acquisition_date=acquisition_date,
        lot_cost_base="100.0000000000",
        lot_cost_local="100.0000000000",
        source_transaction_id=f"TX_{lot_id}",
        source_system="position_lot_state",
        calculation_policy_id="average_cost",
        calculation_policy_version="v1",
        updated_at=datetime(2026, 4, 10, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_portfolio_ownership_query_requires_admitted_tenant_scope() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = "PB_1"
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    exists = await dpm_portfolio_state_sources.SqlAlchemyDpmPortfolioStateReader(
        session
    ).portfolio_exists(tenant_id="tenant-a", portfolio_id="PB_1")

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert exists is True
    assert "portfolios.tenant_id = 'tenant-a'" in sql
    assert "portfolios.portfolio_id = 'PB_1'" in sql


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


@pytest.mark.asyncio
async def test_tax_lot_read_chunks_internal_filter_and_applies_global_page_order() -> None:
    later = _lot(security_id="SEC_1000", lot_id="LOT_1000", acquisition_date=date(2026, 4, 2))
    earlier = _lot(security_id="SEC_0000", lot_id="LOT_0000", acquisition_date=date(2026, 4, 1))
    first_result = MagicMock()
    first_result.all.return_value = [(later, "USD")]
    second_result = MagicMock()
    second_result.all.return_value = [(earlier, "USD")]
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[first_result, second_result])

    records = await dpm_portfolio_state_sources.SqlAlchemyDpmPortfolioStateReader(
        session
    ).list_portfolio_tax_lots(
        portfolio_id="PB_1",
        as_of_date=date(2026, 4, 10),
        security_ids=[f"SEC_{index:04d}" for index in reversed(range(1_001))],
        include_closed_lots=False,
        lot_status_filter=None,
        after_sort_key=None,
        limit=1,
    )

    assert [record.lot_id for record in records] == ["LOT_0000"]
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_instrument_reference_read_chunks_oversized_internal_filter() -> None:
    first_result = MagicMock()
    first_result.scalars.return_value.all.return_value = ["SEC_0000"]
    second_result = MagicMock()
    second_result.scalars.return_value.all.return_value = ["SEC_1000"]
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[first_result, second_result])

    known = await dpm_portfolio_state_sources.SqlAlchemyDpmPortfolioStateReader(
        session
    ).list_known_instrument_security_ids([f"SEC_{index:04d}" for index in reversed(range(1_001))])

    assert known == {"SEC_0000", "SEC_1000"}
    assert session.execute.await_count == 2
