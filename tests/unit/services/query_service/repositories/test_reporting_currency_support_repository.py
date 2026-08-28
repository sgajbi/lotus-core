from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.reporting_currency_support_repository import (
    ReportingCurrencySupportRepository,
)

pytestmark = pytest.mark.asyncio


def _result(*, scalar=None, scalars=None, rows=None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = list(scalars or [])
    result.all.return_value = list(rows or [])
    return result


def _repository(*results: MagicMock) -> tuple[ReportingCurrencySupportRepository, AsyncMock]:
    db = AsyncMock(spec=AsyncSession)
    db.execute.side_effect = list(results)
    return ReportingCurrencySupportRepository(db), db


async def test_portfolio_currency_source_is_as_of_and_tenant_fenced() -> None:
    portfolio = SimpleNamespace(
        tenant_id="tenant-1", base_currency=" usd ", open_date=date(2026, 1, 1)
    )
    repository, db = _repository(
        _result(scalar=portfolio),
        _result(scalars=["EUR", " eur ", "GBP"]),
    )

    source = await repository.get_portfolio_currency_source(
        portfolio_id="PF-1",
        tenant_id="tenant-1",
        as_of_date=date(2026, 8, 28),
    )

    assert source is not None
    assert source.tenant_id == "tenant-1"
    assert source.base_currency == "USD"
    assert source.source_currencies == ("EUR", "GBP", "USD")
    assert db.execute.await_count == 2
    portfolio_sql = str(
        db.execute.await_args_list[0].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "portfolios.portfolio_id = 'PF-1'" in portfolio_sql
    assert "portfolios.tenant_id = 'tenant-1'" in portfolio_sql
    currency_sql = str(
        db.execute.await_args_list[1].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "LEFT OUTER JOIN instruments" in currency_sql
    assert "position_history.position_date <= '2026-08-28'" in currency_sql
    assert "quantity != 0" in currency_sql
    assert "position_timeseries.date = '2026-08-28'" in currency_sql
    assert "cashflows.cashflow_date = '2026-08-28'" in currency_sql
    assert "SELECT DISTINCT upper(trim(instruments.currency)) AS source_currency" in currency_sql
    assert "ORDER BY upper(trim(instruments.currency)) ASC" in currency_sql


async def test_portfolio_currency_source_returns_none_when_portfolio_missing() -> None:
    repository, db = _repository(_result(scalar=None))

    source = await repository.get_portfolio_currency_source(
        portfolio_id="MISSING",
        tenant_id=None,
        as_of_date=date(2026, 8, 28),
    )

    assert source is None
    db.execute.assert_awaited_once()


async def test_portfolio_currency_source_fails_closed_before_portfolio_inception() -> None:
    repository, db = _repository(
        _result(
            scalar=SimpleNamespace(
                tenant_id="tenant-1", base_currency="USD", open_date=date(2026, 9, 1)
            )
        )
    )

    with pytest.raises(ValueError, match="precedes portfolio inception"):
        await repository.get_portfolio_currency_source(
            portfolio_id="PF-1",
            tenant_id="tenant-1",
            as_of_date=date(2026, 8, 28),
        )

    db.execute.assert_awaited_once()


async def test_portfolio_currency_source_fails_closed_for_invalid_persisted_currency() -> None:
    repository, db = _repository(
        _result(
            scalar=SimpleNamespace(tenant_id=None, base_currency="USD", open_date=date(2026, 1, 1))
        ),
        _result(scalars=["US1"]),
    )

    with pytest.raises(ValueError, match="three-letter ISO 4217"):
        await repository.get_portfolio_currency_source(
            portfolio_id="PF-1",
            tenant_id=None,
            as_of_date=date(2026, 8, 28),
        )

    assert db.execute.await_count == 2


@pytest.mark.parametrize("unresolved_currency", [None, "   "])
async def test_portfolio_currency_source_fails_closed_for_unresolved_position_currency(
    unresolved_currency: str | None,
) -> None:
    repository, db = _repository(
        _result(
            scalar=SimpleNamespace(
                tenant_id="tenant-1", base_currency="USD", open_date=date(2026, 1, 1)
            )
        ),
        _result(scalars=[unresolved_currency]),
    )

    with pytest.raises(ValueError, match="position source currency is unavailable"):
        await repository.get_portfolio_currency_source(
            portfolio_id="PF-1",
            tenant_id="tenant-1",
            as_of_date=date(2026, 8, 28),
        )


async def test_latest_fx_dates_batches_sources_and_ignores_null_rates() -> None:
    repository, db = _repository(_result(rows=[("EUR", date(2026, 8, 20)), ("GBP", None)]))

    dates = await repository.get_latest_fx_rate_dates(
        from_currencies=(" eur ", "GBP"),
        to_currency=" usd ",
        as_of_date=date(2026, 8, 28),
    )

    assert dates == {"EUR": date(2026, 8, 20)}
    db.execute.assert_awaited_once()
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "upper(trim(fx_rates.from_currency)) IN ('EUR', 'GBP')" in sql
    assert "upper(trim(fx_rates.to_currency)) = 'USD'" in sql
    assert "fx_rates.rate_date = '2026-08-28'" in sql
    assert "fx_rates.rate_date <=" not in sql
    assert "GROUP BY upper(trim(fx_rates.from_currency))" in sql


async def test_latest_fx_dates_skips_empty_source_set() -> None:
    repository, db = _repository()

    assert (
        await repository.get_latest_fx_rate_dates(
            from_currencies=(), to_currency="USD", as_of_date=date(2026, 8, 28)
        )
        == {}
    )
    db.execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("portfolio_result", "instrument_result", "expected"),
    [
        (_result(scalar="PF-1"), None, True),
        (_result(scalar=None), _result(scalar="SEC-1"), True),
        (_result(scalar=None), _result(scalar=None), False),
    ],
)
async def test_selector_observation_checks_portfolios_then_instruments(
    portfolio_result: MagicMock,
    instrument_result: MagicMock | None,
    expected: bool,
) -> None:
    results = (
        (portfolio_result,) if instrument_result is None else (portfolio_result, instrument_result)
    )
    repository, db = _repository(*results)

    observed = await repository.is_selector_currency_observed(currency=" eur ")

    assert observed is expected
    assert db.execute.await_count == len(results)
    first_sql = str(
        db.execute.await_args_list[0].args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "upper(trim(portfolios.base_currency)) = 'EUR'" in first_sql


async def test_selector_observation_normalizes_code_before_query() -> None:
    repository, db = _repository(_result(scalar="PF-1"))

    assert await repository.is_selector_currency_observed(currency="usd") is True
    sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "upper(trim(portfolios.base_currency)) = 'USD'" in sql
