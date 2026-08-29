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
    created_at = datetime(2026, 4, 8, 1, 0, tzinfo=UTC)
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
        created_at=created_at,
        updated_at=datetime(2026, 4, 9, 1, 0, tzinfo=UTC),
    )


def _state(epoch: int = 4) -> SimpleNamespace:
    return SimpleNamespace(
        epoch=epoch,
        created_at=datetime(2026, 4, 10, 1, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 10, 2, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_maps_portfolio_instrument_price_and_fx_records() -> None:
    price_created_at = datetime(2026, 4, 10, 1, 0, tzinfo=UTC)
    price_updated_at = datetime(2026, 4, 10, 3, 0, tzinfo=UTC)
    fx_created_at = datetime(2026, 4, 10, 2, 0, tzinfo=UTC)
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [
        _Result(
            [
                SimpleNamespace(
                    portfolio_id="P1",
                    base_currency="SGD",
                    created_at=datetime(2026, 4, 8, 1, tzinfo=UTC),
                    updated_at=datetime(2026, 4, 9, 1, tzinfo=UTC),
                )
            ]
        ),
        _Result([_instrument()]),
        _Result(
            [
                SimpleNamespace(
                    price_date=date(2026, 4, 10),
                    price=Decimal("101.25"),
                    currency="SGD",
                    created_at=price_created_at,
                    updated_at=price_updated_at,
                )
            ]
        ),
        _Result(
            [
                SimpleNamespace(
                    rate_date=date(2026, 4, 10),
                    rate=Decimal("1.35"),
                    created_at=fx_created_at,
                    updated_at=None,
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
    assert portfolio.updated_at == datetime(2026, 4, 9, 1, tzinfo=UTC)
    assert [item.security_id for item in instruments] == ["SEC_1"]
    assert prices[0].price == Decimal("101.25")
    assert prices[0].evidence_timestamp == price_updated_at
    assert rates[0].rate == Decimal("1.35")
    assert rates[0].evidence_timestamp == fx_created_at

    instrument_sql = str(
        session.execute.await_args_list[1].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    fx_sql = str(
        session.execute.await_args_list[3].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(instruments.security_id) IN ('SEC_1')" in instrument_sql
    assert "upper(trim(fx_rates.from_currency)) = 'USD'" in fx_sql
    assert "upper(trim(fx_rates.to_currency)) = 'SGD'" in fx_sql
    assert "ORDER BY fx_rates.rate_date ASC, fx_rates.id ASC" in fx_sql


@pytest.mark.asyncio
async def test_maps_current_snapshot_position_and_fences_current_epoch() -> None:
    portfolio_created_at = datetime(2026, 4, 9, 8, 0, tzinfo=UTC)
    portfolio_updated_at = datetime(2026, 4, 9, 9, 0, tzinfo=UTC)
    session = AsyncMock(spec=AsyncSession)
    snapshot = SimpleNamespace(
        date=date(2026, 4, 9),
        security_id=" SEC_1 ",
        quantity=Decimal("10"),
        market_price=Decimal("100"),
        market_value=Decimal("1000"),
        market_value_local=Decimal("1000"),
        cost_basis=Decimal("950"),
        cost_basis_local=Decimal("950"),
        valuation_status="VALUED_STALE",
        valuation_source_currency="EUR",
        valuation_reporting_currency="SGD",
        valuation_fx_rate_date=date(2026, 4, 9),
        valuation_fx_rate=Decimal("1.35"),
        created_at=datetime(2026, 4, 10, 1, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 10, 2, 0, tzinfo=UTC),
    )
    session.execute.return_value = _Result(
        [
            (
                snapshot,
                _instrument(),
                _state(),
                "SEC_1",
                date(2026, 4, 10),
                Decimal("975"),
                Decimal("970"),
                portfolio_created_at,
                portfolio_updated_at,
            )
        ]
    )
    reader = SqlAlchemyCoreSnapshotSourceReader(session)

    records = await reader.get_position_snapshot(
        portfolio_id="P1",
        as_of_date=date(2026, 4, 10),
    )

    assert records[0].security_id == "SEC_1"
    assert records[0].market_price == Decimal("100")
    assert records[0].market_value == Decimal("1000")
    assert records[0].cost_basis == Decimal("975")
    assert records[0].cost_basis_local == Decimal("970")
    assert records[0].epoch == 4
    assert records[0].business_date == date(2026, 4, 9)
    assert records[0].portfolio_business_date == date(2026, 4, 10)
    assert records[0].valuation_status == "VALUED_STALE"
    assert records[0].valuation_source_currency == "EUR"
    assert records[0].valuation_reporting_currency == "SGD"
    assert records[0].valuation_fx_rate_date == date(2026, 4, 9)
    assert records[0].valuation_fx_rate == Decimal("1.35")
    assert records[0].portfolio_fact_created_at == portfolio_created_at
    assert records[0].portfolio_fact_updated_at == portfolio_updated_at
    assert records[0].instrument.name == "Global Bond"
    assert records[0].instrument.created_at == datetime(2026, 4, 8, 1, 0, tzinfo=UTC)

    sql = str(
        session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "position_history.epoch = position_state.epoch" in sql
    assert "daily_position_snapshots.epoch" in sql
    assert "daily_position_snapshots.date <= '2026-04-10'" in sql
    assert "position_history.position_date" in sql
    assert "quantity != 0" in sql
    assert "row_number() over" in sql
    assert "left outer join daily_position_snapshots" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_source", ["snapshot", "instrument"])
async def test_snapshot_read_fails_closed_for_incomplete_current_position_coverage(
    missing_source: str,
) -> None:
    snapshot = SimpleNamespace(
        date=date(2026, 4, 10),
        security_id="SEC_1",
        quantity=Decimal("10"),
        market_price=Decimal("100"),
        market_value=Decimal("1000"),
        market_value_local=Decimal("1000"),
        valuation_status="VALUED_CURRENT",
        valuation_source_currency="SGD",
        valuation_reporting_currency="SGD",
        valuation_fx_rate_date=None,
        valuation_fx_rate=None,
        created_at=datetime(2026, 4, 10, 1, tzinfo=UTC),
        updated_at=datetime(2026, 4, 10, 2, tzinfo=UTC),
    )
    complete_row = (
        snapshot,
        _instrument("SEC_1"),
        _state(),
        "SEC_1",
        date(2026, 4, 10),
        Decimal("950"),
        Decimal("950"),
        datetime(2026, 4, 10, 1, tzinfo=UTC),
        datetime(2026, 4, 10, 2, tzinfo=UTC),
    )
    incomplete_row = (
        None if missing_source == "snapshot" else snapshot,
        None if missing_source == "instrument" else _instrument("SEC_2"),
        _state(),
        "SEC_2",
        date(2026, 4, 10),
        Decimal("500"),
        Decimal("500"),
        datetime(2026, 4, 10, 1, tzinfo=UTC),
        datetime(2026, 4, 10, 2, tzinfo=UTC),
    )
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result([complete_row, incomplete_row])

    records = await SqlAlchemyCoreSnapshotSourceReader(session).get_position_snapshot(
        portfolio_id="P1",
        as_of_date=date(2026, 4, 10),
    )

    assert records == []


@pytest.mark.asyncio
async def test_maps_history_fallback_without_snapshot_market_values() -> None:
    session = AsyncMock(spec=AsyncSession)
    history = SimpleNamespace(
        position_date=date(2026, 4, 9),
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

    assert records[0].market_price is None
    assert records[0].market_value is None
    assert records[0].market_value_local is None
    assert records[0].cost_basis == Decimal("950")
    assert records[0].business_date == date(2026, 4, 9)
    assert records[0].portfolio_business_date == date(2026, 4, 9)
    assert records[0].valuation_status is None
    assert records[0].valuation_source_currency is None
    assert records[0].valuation_reporting_currency is None
    assert records[0].valuation_fx_rate_date is None
    assert records[0].valuation_fx_rate is None
    assert records[0].portfolio_fact_created_at == history.created_at
    assert records[0].portfolio_fact_updated_at == history.updated_at

    sql = str(
        session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    ).lower()
    assert "position_history.position_date <= '2026-04-10'" in sql
    assert "position_history.quantity != 0" in sql
    assert "position_history.epoch = position_state.epoch" in sql


@pytest.mark.asyncio
async def test_reads_exact_financial_reconciliation_controls_in_one_query() -> None:
    from portfolio_common.domain.holdings_reconciliation import HoldingsReconciliationScope

    session = AsyncMock(spec=AsyncSession)
    updated_at = datetime(2026, 4, 10, 3, tzinfo=UTC)
    session.execute.return_value = _Result(
        [
            SimpleNamespace(
                business_date=date(2026, 4, 10),
                epoch=4,
                status="COMPLETED",
                updated_at=updated_at,
            )
        ]
    )
    reader = SqlAlchemyCoreSnapshotSourceReader(session)

    controls = await reader.get_financial_reconciliation_controls(
        portfolio_id="P1",
        scopes=(
            HoldingsReconciliationScope(
                business_date=date(2026, 4, 10),
                epoch=4,
                latest_evidence_timestamp=updated_at,
                source_row_count=2,
            ),
        ),
    )

    assert controls[0].status == "COMPLETED"
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "pipeline_stage_state.stage_name = 'FINANCIAL_RECONCILIATION'" in sql
    assert "pipeline_stage_state.portfolio_id = 'P1'" in sql
    assert "(pipeline_stage_state.business_date, pipeline_stage_state.epoch) IN" in sql
