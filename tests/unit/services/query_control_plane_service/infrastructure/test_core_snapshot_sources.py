"""Tests for QCP Core snapshot source-record mapping and query contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure.core_snapshot_sources import (
    SqlAlchemyCoreSnapshotSourceReader,
)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


def _instrument(security_id: str = " SEC_1 ") -> SimpleNamespace:
    return SimpleNamespace(
        security_id=security_id,
        name="Global Bond",
        currency="SGD",
        asset_class="Fixed Income",
        sector="Government",
        country_of_risk="SG",
        isin="SG0000000001",
        issuer_id="ISS_1",
        issuer_name="Singapore Treasury",
        ultimate_parent_issuer_id="ISS_1",
        ultimate_parent_issuer_name="Singapore Treasury",
        liquidity_tier="T1",
    )


def _state(epoch: int = 4) -> SimpleNamespace:
    return SimpleNamespace(
        epoch=epoch,
        created_at=datetime(2026, 4, 10, 1, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 10, 2, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_maps_portfolio_instrument_price_and_fx_records() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [
        _Result([SimpleNamespace(portfolio_id="P1", base_currency="SGD")]),
        _Result([_instrument()]),
        _Result(
            [
                SimpleNamespace(
                    price_date=date(2026, 4, 10),
                    price=Decimal("101.25"),
                    currency="SGD",
                )
            ]
        ),
        _Result(
            [
                SimpleNamespace(
                    rate_date=date(2026, 4, 10),
                    rate=Decimal("1.35"),
                )
            ]
        ),
    ]
    reader = SqlAlchemyCoreSnapshotSourceReader(session)

    portfolio = await reader.get_portfolio("P1")
    instruments = await reader.get_instruments([" SEC_1 ", "SEC_1"])
    prices = await reader.get_prices(security_id=" SEC_1 ", end_date=date(2026, 4, 10))
    rates = await reader.get_fx_rates(
        from_currency=" usd ",
        to_currency=" sgd ",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 10),
    )

    assert portfolio is not None and portfolio.base_currency == "SGD"
    assert [item.security_id for item in instruments] == ["SEC_1"]
    assert prices[0].price == Decimal("101.25")
    assert rates[0].rate == Decimal("1.35")

    instrument_sql = str(
        session.execute.await_args_list[1].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    fx_sql = str(
        session.execute.await_args_list[3].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(instruments.security_id) IN ('SEC_1')" in instrument_sql
    assert "upper(trim(fx_rates.from_currency)) = 'USD'" in fx_sql
    assert "upper(trim(fx_rates.to_currency)) = 'SGD'" in fx_sql


@pytest.mark.asyncio
async def test_maps_current_snapshot_position_and_fences_current_epoch() -> None:
    session = AsyncMock(spec=AsyncSession)
    snapshot = SimpleNamespace(
        security_id=" SEC_1 ",
        quantity=Decimal("10"),
        market_value=Decimal("1000"),
        market_value_local=Decimal("1000"),
        cost_basis=Decimal("950"),
        cost_basis_local=Decimal("950"),
        created_at=datetime(2026, 4, 10, 1, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 10, 2, 0, tzinfo=UTC),
    )
    session.execute.return_value = _Result([(snapshot, _instrument(), _state())])
    reader = SqlAlchemyCoreSnapshotSourceReader(session)

    records = await reader.get_position_snapshot(
        portfolio_id="P1",
        as_of_date=date(2026, 4, 10),
    )

    assert records[0].security_id == "SEC_1"
    assert records[0].market_value == Decimal("1000")
    assert records[0].cost_basis == Decimal("950")
    assert records[0].epoch == 4
    assert records[0].instrument.name == "Global Bond"

    sql = str(
        session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "position_history.epoch = position_state.epoch" in sql
    assert "daily_position_snapshots.epoch" in sql
    assert "daily_position_snapshots.date <= '2026-04-10'" in sql
    assert "row_number() over" in sql


@pytest.mark.asyncio
async def test_maps_history_fallback_without_snapshot_market_values() -> None:
    session = AsyncMock(spec=AsyncSession)
    history = SimpleNamespace(
        security_id="SEC_1",
        quantity=Decimal("10"),
        cost_basis=Decimal("950"),
        cost_basis_local=Decimal("950"),
        created_at=datetime(2026, 4, 9, 1, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 9, 2, 0, tzinfo=UTC),
    )
    session.execute.return_value = _Result([(history, _instrument(), _state())])
    reader = SqlAlchemyCoreSnapshotSourceReader(session)

    records = await reader.get_position_history(
        portfolio_id="P1",
        as_of_date=date(2026, 4, 10),
    )

    assert records[0].market_value is None
    assert records[0].market_value_local is None
    assert records[0].cost_basis == Decimal("950")

    sql = str(
        session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "position_history.position_date <= '2026-04-10'" in sql
    assert "position_history.quantity != 0" in sql
    assert "position_history.epoch = position_state.epoch" in sql
