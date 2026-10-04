from datetime import date
from decimal import Decimal
from types import SimpleNamespace
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


@pytest.mark.parametrize("page_size", [0, 501])
async def test_authority_impact_rejects_unbounded_pages_before_query(page_size: int) -> None:
    repository, session = _repository()

    with pytest.raises(ValueError, match="page size must be between 1 and 500"):
        await repository.find_authoritative_price_impact_page(
            tenant_id="TENANT-1",
            legal_book_id="BOOK-1",
            security_id="SEC-1",
            valuation_date=date(2026, 8, 21),
            page_size=page_size,
        )

    session.execute.assert_not_awaited()


@pytest.mark.parametrize("identity_field", ["tenant_id", "legal_book_id", "security_id"])
@pytest.mark.parametrize("invalid_identity", [None, "", "   "])
async def test_authority_impact_rejects_incomplete_scope_before_database_access(
    identity_field: str, invalid_identity: object
) -> None:
    repository, session = _repository()
    scope = {"tenant_id": "TENANT-1", "legal_book_id": "BOOK-1", "security_id": "SEC-1"}
    scope[identity_field] = invalid_identity

    with pytest.raises(ValueError, match="identity must be nonblank text"):
        await repository.find_authoritative_price_impact_page(
            **scope, valuation_date=date(2026, 8, 21)
        )

    session.execute.assert_not_awaited()


@pytest.mark.parametrize("page_size", [1, 500])
async def test_authority_impact_first_page_keeps_exact_scope_and_signed_current_holdings(
    page_size: int,
) -> None:
    repository, session = _repository()
    session.execute.return_value.all.return_value = [
        SimpleNamespace(portfolio_id="PORT-1", security_id="SEC-1", epoch=3)
    ]

    page = await repository.find_authoritative_price_impact_page(
        tenant_id="TENANT-1",
        legal_book_id="BOOK-1",
        security_id="SEC-1",
        valuation_date=date(2026, 8, 21),
        page_size=page_size,
    )

    assert page == [("PORT-1", "SEC-1", 3)]
    sql = _compile_postgresql(session.execute.await_args.args[0])
    assert "JOIN portfolios ON portfolios.portfolio_id = position_state.portfolio_id" in sql
    assert "portfolios.tenant_id = 'TENANT-1'" in sql
    assert "portfolios.legal_book_id = 'BOOK-1'" in sql
    assert "position_state.security_id = 'SEC-1'" in sql
    assert "position_history.portfolio_id = position_state.portfolio_id" in sql
    assert "position_history.security_id = position_state.security_id" in sql
    assert "position_history.epoch = position_state.epoch" in sql
    assert "position_history.position_date <= '2026-08-21'" in sql
    assert "ORDER BY position_history.position_date DESC, position_history.id DESC" in sql
    assert "position_state.status IN ('CURRENT', 'REPROCESSING')" in sql
    assert ") != 0" in sql
    assert ") > 0" not in sql
    assert "market_prices" not in sql
    assert "(position_state.portfolio_id, position_state.epoch) >" not in sql
    assert "ORDER BY position_state.portfolio_id, position_state.epoch" in sql
    assert sql.rstrip().endswith(f"LIMIT {page_size}")


async def test_authority_impact_strict_epoch_cursor_and_empty_page_termination() -> None:
    repository, session = _repository()
    populated = MagicMock()
    populated.all.return_value = [
        SimpleNamespace(portfolio_id="PORT-1", security_id="SEC-1", epoch=4),
        SimpleNamespace(portfolio_id="PORT-2", security_id="SEC-1", epoch=1),
    ]
    empty = MagicMock()
    empty.all.return_value = []
    session.execute.side_effect = [populated, empty]
    scope = {
        "tenant_id": "TENANT-1",
        "legal_book_id": "BOOK-1",
        "security_id": "SEC-1",
        "valuation_date": date(2026, 8, 21),
        "page_size": 2,
    }

    page = await repository.find_authoritative_price_impact_page(**scope, after=("PORT-1", 3))
    assert page == [("PORT-1", "SEC-1", 4), ("PORT-2", "SEC-1", 1)]
    exhausted = await repository.find_authoritative_price_impact_page(
        **scope, after=(page[-1][0], page[-1][2])
    )
    assert exhausted == []
    first_sql, last_sql = [
        _compile_postgresql(call.args[0]) for call in session.execute.await_args_list
    ]
    assert "(position_state.portfolio_id, position_state.epoch) > ('PORT-1', 3)" in first_sql
    assert "(position_state.portfolio_id, position_state.epoch) > ('PORT-2', 1)" in last_sql
    assert first_sql.rstrip().endswith("LIMIT 2")
    assert last_sql.rstrip().endswith("LIMIT 2")


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
        valuation_source_currency="EUR",
        valuation_reporting_currency="USD",
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
    assert "valuation_source_currency" in sql
    assert "valuation_source_currency = excluded.valuation_source_currency" in sql.lower()
    assert "valuation_reporting_currency" in sql
    assert "valuation_reporting_currency = excluded.valuation_reporting_currency" in sql.lower()
