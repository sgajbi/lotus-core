from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.cashflow_repository import CashflowRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock(all=lambda: []))
    return session


async def test_projected_settlement_cashflow_series_limits_to_external_future_settlements(
    mock_db_session: AsyncMock,
):
    repository = CashflowRepository(mock_db_session)

    await repository.get_projected_settlement_cashflow_series(
        portfolio_id="P1",
        start_date=__import__("datetime").date(2026, 4, 18),
        end_date=__import__("datetime").date(2026, 4, 28),
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.transaction_type IN ('DEPOSIT', 'WITHDRAWAL')" in compiled_query
    assert (
        "date(transactions.settlement_date) BETWEEN '2026-04-18' AND '2026-04-28'" in compiled_query
    )
    assert "date(transactions.transaction_date) < '2026-04-18'" in compiled_query
    assert "transactions.transaction_type = 'BUY'" not in compiled_query


async def test_latest_cashflows_subquery_prefers_highest_epoch_per_transaction() -> None:
    subquery = CashflowRepository._latest_cashflows_subquery()

    compiled_query = str(select(subquery).compile(compile_kwargs={"literal_binds": True}))

    assert "row_number() over" in compiled_query.lower()
    assert "partition by cashflows.transaction_id" in compiled_query.lower()
    assert "order by cashflows.epoch desc, cashflows.id desc" in compiled_query.lower()
    assert "anon_2.rn = 1" in compiled_query.lower()


async def test_cashflow_repository_portfolio_exists_uses_limit_one(
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value = MagicMock(scalar_one_or_none=lambda: "P1")
    repository = CashflowRepository(mock_db_session)

    exists = await repository.portfolio_exists("P1")

    assert exists is True
    stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolios.portfolio_id = 'P1'" in compiled_query
    assert "LIMIT 1" in compiled_query


async def test_cashflow_repository_portfolio_currency_uses_base_currency(
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value = MagicMock(scalar_one_or_none=lambda: "USD")
    repository = CashflowRepository(mock_db_session)

    portfolio_currency = await repository.get_portfolio_currency("P1")

    assert portfolio_currency == "USD"
    stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolios.base_currency" in compiled_query
    assert "portfolios.portfolio_id = 'P1'" in compiled_query
    assert "LIMIT 1" in compiled_query


async def test_cashflow_repository_latest_business_date_uses_default_calendar(
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value = MagicMock(scalar_one_or_none=lambda: date(2026, 4, 17))
    repository = CashflowRepository(mock_db_session)

    business_date = await repository.get_latest_business_date()

    assert business_date == date(2026, 4, 17)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(business_dates.date)" in compiled_query.lower()
    assert "business_dates.calendar_code = 'GLOBAL'" in compiled_query


async def test_cashflow_repository_portfolio_cashflow_series_filters_to_portfolio_flows(
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value = MagicMock(
        all=lambda: [(date(2026, 4, 18), 10), (date(2026, 4, 19), -2)]
    )
    repository = CashflowRepository(mock_db_session)

    rows = await repository.get_portfolio_cashflow_series(
        portfolio_id="P1",
        start_date=date(2026, 4, 18),
        end_date=date(2026, 4, 28),
    )

    assert rows == [(date(2026, 4, 18), 10), (date(2026, 4, 19), -2)]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "anon_1.portfolio_id = 'P1'" in compiled_query
    assert "anon_1.cashflow_date BETWEEN '2026-04-18' AND '2026-04-28'" in compiled_query
    assert "anon_1.is_portfolio_flow" in compiled_query
    assert "sum(anon_1.amount)" in compiled_query.lower()


async def test_latest_cashflow_evidence_timestamp_uses_booked_and_projected_sources(
    mock_db_session: AsyncMock,
) -> None:
    booked_timestamp = datetime(2026, 4, 18, 9, 15, tzinfo=UTC)
    projected_timestamp = datetime(2026, 4, 19, 10, 45, tzinfo=UTC)
    mock_db_session.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: booked_timestamp),
        MagicMock(scalar_one_or_none=lambda: projected_timestamp),
    ]
    repository = CashflowRepository(mock_db_session)

    latest = await repository.get_latest_cashflow_evidence_timestamp(
        portfolio_id="P1",
        start_date=date(2026, 4, 18),
        end_date=date(2026, 4, 28),
        include_projected=True,
    )

    assert latest == projected_timestamp
    booked_stmt = mock_db_session.execute.call_args_list[0][0][0]
    projected_stmt = mock_db_session.execute.call_args_list[1][0][0]
    booked_query = str(booked_stmt.compile(compile_kwargs={"literal_binds": True}))
    projected_query = str(projected_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(anon_1.updated_at)" in booked_query.lower()
    assert "anon_1.portfolio_id = 'P1'" in booked_query
    assert "anon_1.cashflow_date BETWEEN '2026-04-18' AND '2026-04-28'" in booked_query
    assert "max(transactions.updated_at)" in projected_query.lower()
    assert "transactions.transaction_type IN ('DEPOSIT', 'WITHDRAWAL')" in projected_query
    assert "date(transactions.transaction_date) < '2026-04-18'" in projected_query


async def test_latest_cashflow_evidence_timestamp_skips_projected_query_for_booked_only(
    mock_db_session: AsyncMock,
) -> None:
    booked_timestamp = datetime(2026, 4, 18, 9, 15, tzinfo=UTC)
    mock_db_session.execute.return_value = MagicMock(scalar_one_or_none=lambda: booked_timestamp)
    repository = CashflowRepository(mock_db_session)

    latest = await repository.get_latest_cashflow_evidence_timestamp(
        portfolio_id="P1",
        start_date=date(2026, 4, 18),
        end_date=date(2026, 4, 28),
        include_projected=False,
    )

    assert latest == booked_timestamp
    assert mock_db_session.execute.await_count == 1


async def test_latest_cashflow_evidence_timestamp_returns_none_when_no_evidence(
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
    repository = CashflowRepository(mock_db_session)

    latest = await repository.get_latest_cashflow_evidence_timestamp(
        portfolio_id="P1",
        start_date=date(2026, 4, 18),
        end_date=date(2026, 4, 28),
        include_projected=False,
    )

    assert latest is None


async def test_cashflow_repository_external_flows_limits_to_investor_movements(
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value = MagicMock(all=lambda: [])
    repository = CashflowRepository(mock_db_session)

    await repository.get_external_flows(
        portfolio_id="P1",
        start_date=date(2026, 4, 18),
        end_date=date(2026, 4, 28),
    )

    stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "anon_1.classification IN ('CASHFLOW_IN', 'CASHFLOW_OUT')" in compiled_query
    assert "anon_1.cashflow_date BETWEEN '2026-04-18' AND '2026-04-28'" in compiled_query
    assert "ORDER BY anon_1.cashflow_date ASC" in compiled_query


async def test_cashflow_repository_income_cashflows_query_joins_epoch_matched_positions(
    mock_db_session: AsyncMock,
) -> None:
    scalar_result = MagicMock()
    scalar_result.scalars.return_value.all.return_value = ["income-record"]
    mock_db_session.execute.return_value = scalar_result
    repository = CashflowRepository(mock_db_session)

    rows = await repository.get_income_cashflows_for_position(
        portfolio_id="P1",
        security_id="SEC-IBM",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 17),
    )

    assert rows == ["income-record"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "position_state.portfolio_id = cashflows.portfolio_id" in compiled_query.lower()
    assert "position_state.security_id = cashflows.security_id" in compiled_query.lower()
    assert "position_state.epoch = cashflows.epoch" in compiled_query.lower()
    assert "cashflows.classification = 'INCOME'" in compiled_query
    assert "cashflows.cashflow_date BETWEEN '2026-04-01' AND '2026-04-17'" in compiled_query
