"""SQL adapter tests for governed index series windows."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.query_control_plane_service.app.infrastructure.index_series_sources import (
    SqlAlchemyIndexSeriesReader,
)


def _result(row: SimpleNamespace) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    return result


def _common_row() -> dict[str, object]:
    evidence_at = datetime(2026, 4, 10, 10, tzinfo=UTC)
    return {
        "series_id": "vendor-series",
        "index_id": "IDX_MSCI_WORLD_TR",
        "series_date": date(2026, 4, 10),
        "series_currency": "USD",
        "quality_status": "accepted",
        "source_timestamp": evidence_at,
        "source_vendor": "MSCI",
        "source_record_id": "source:1",
        "created_at": evidence_at,
        "updated_at": evidence_at,
    }


@pytest.mark.asyncio
async def test_price_query_ranks_one_canonical_row_per_business_date() -> None:
    row = SimpleNamespace(
        **_common_row(), index_price=Decimal("123.45"), value_convention="close_price"
    )
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(row))

    records = await SqlAlchemyIndexSeriesReader(session).list_prices(
        index_id=" IDX_MSCI_WORLD_TR ",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 10),
    )

    assert records[0].observed_at == row.source_timestamp
    sql = str(session.execute.await_args.args[0])
    assert "row_number() OVER" in sql
    assert "PARTITION BY index_price_series.index_id, index_price_series.series_date" in sql
    assert "index_price_series.source_timestamp DESC NULLS LAST" in sql
    assert "ORDER BY index_price_series.index_id ASC, index_price_series.series_date ASC" in sql


@pytest.mark.asyncio
async def test_return_query_ranks_one_canonical_row_per_business_date() -> None:
    row = SimpleNamespace(
        **_common_row(),
        index_return=Decimal("0.0012"),
        return_period="1d",
        return_convention="total_return_index",
    )
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(row))

    records = await SqlAlchemyIndexSeriesReader(session).list_returns(
        index_id="IDX_MSCI_WORLD_TR",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 10),
    )

    assert records[0].index_return == Decimal("0.0012")
    sql = str(session.execute.await_args.args[0])
    assert "PARTITION BY index_return_series.index_id, index_return_series.series_date" in sql
    assert "index_return_series.source_timestamp DESC NULLS LAST" in sql
    assert "ORDER BY index_return_series.index_id ASC, index_return_series.series_date ASC" in sql


@pytest.mark.asyncio
async def test_bulk_price_query_normalizes_ids_and_uses_one_ordered_query() -> None:
    row = SimpleNamespace(
        **_common_row(), index_price=Decimal("123.45"), value_convention="close_price"
    )
    session = MagicMock()
    session.execute = AsyncMock(return_value=_result(row))

    records = await SqlAlchemyIndexSeriesReader(session).list_prices_for_indices(
        index_ids=[" IDX_A ", "IDX_B", "IDX_A", " "],
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 10),
    )

    assert len(records) == 1
    sql = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "index_price_series.index_id IN ('IDX_A', 'IDX_B')" in sql
    assert "ORDER BY index_price_series.index_id ASC, index_price_series.series_date ASC" in sql
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_bulk_index_scope_avoids_database_io() -> None:
    session = MagicMock()
    session.execute = AsyncMock()
    reader = SqlAlchemyIndexSeriesReader(session)

    assert (
        await reader.list_prices_for_indices(
            index_ids=[], start_date=date(2026, 4, 1), end_date=date(2026, 4, 10)
        )
        == []
    )
    assert (
        await reader.list_returns_for_indices(
            index_ids=[" "], start_date=date(2026, 4, 1), end_date=date(2026, 4, 10)
        )
        == []
    )
    session.execute.assert_not_awaited()
