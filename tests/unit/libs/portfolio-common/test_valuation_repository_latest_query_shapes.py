from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import DailyPositionSnapshot
from portfolio_common.valuation_repository_base import ValuationRepositoryBase
from sqlalchemy.dialects import postgresql

pytestmark = pytest.mark.asyncio


def _compile_postgresql(statement: object) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _repository() -> tuple[ValuationRepositoryBase, AsyncMock]:
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    result.scalars.return_value.all.return_value = []
    result.mappings.return_value.all.return_value = []
    session.execute.return_value = result
    return ValuationRepositoryBase(session), session


async def test_price_revaluation_lookup_uses_current_epoch_distinct_latest_history() -> None:
    repository, session = _repository()

    await repository.find_position_keys_requiring_price_revaluation("SEC-1", date(2026, 8, 21))

    sql = _compile_postgresql(session.execute.await_args.args[0])
    assert "SELECT DISTINCT ON (position_history.portfolio_id, position_history.epoch)" in sql
    assert "position_state.epoch = anon_1.epoch" in sql
    assert "anon_1.quantity != 0" in sql
    assert "row_number()" not in sql


async def test_holding_lookup_uses_current_epoch_distinct_latest_history() -> None:
    repository, session = _repository()

    await repository.find_portfolios_holding_security_on_date("SEC-1", date(2026, 8, 21))

    sql = _compile_postgresql(session.execute.await_args.args[0])
    assert "SELECT DISTINCT ON (position_history.portfolio_id)" in sql
    assert "position_state.epoch = position_history.epoch" in sql
    assert "anon_1.quantity != 0" in sql
    assert "row_number()" not in sql


async def test_open_position_lookup_uses_current_epoch_distinct_latest_snapshot() -> None:
    repository, session = _repository()

    await repository.get_all_open_positions()

    sql = _compile_postgresql(session.execute.await_args.args[0])
    assert (
        "SELECT DISTINCT ON (daily_position_snapshots.portfolio_id, "
        "trim(daily_position_snapshots.security_id))" in sql
    )
    assert "position_state.epoch = daily_position_snapshots.epoch" in sql
    assert "anon_1.quantity != 0" in sql
    assert "row_number()" not in sql


async def test_snapshot_upsert_preserves_valuation_fx_effective_date() -> None:
    repository, session = _repository()
    snapshot = DailyPositionSnapshot(
        portfolio_id="PORT-1",
        security_id="SEC-EUR",
        date=date(2026, 8, 21),
        epoch=3,
        quantity=Decimal("10"),
        cost_basis=Decimal("900"),
        cost_basis_local=Decimal("800"),
        valuation_status="VALUED_CURRENT",
        valuation_fx_rate_date=date(2026, 8, 20),
        valuation_fx_rate=Decimal("1.2345"),
    )

    await repository.upsert_daily_snapshot(snapshot)

    sql = _compile_postgresql(session.execute.await_args.args[0])
    assert "valuation_fx_rate_date" in sql
    assert "2026-08-20" in sql
    assert "valuation_fx_rate_date = excluded.valuation_fx_rate_date" in sql.lower()
    assert "valuation_fx_rate" in sql
    assert "1.2345" in sql
    assert "valuation_fx_rate = excluded.valuation_fx_rate" in sql.lower()
