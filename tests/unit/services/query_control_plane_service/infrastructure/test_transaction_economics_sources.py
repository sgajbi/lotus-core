"""SQL contract tests for the QCP transaction-economics source adapter."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Cashflow, Transaction, TransactionCost
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_control_plane_service.app.infrastructure.transaction_economics_sources import (  # noqa: E501
    SqlAlchemyTransactionEconomicsReader,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> SqlAlchemyTransactionEconomicsReader:
    return SqlAlchemyTransactionEconomicsReader(mock_db_session)


def _performance_economics_transaction(
    transaction_id: str = "TXN-PERF-001",
) -> Transaction:
    transaction = Transaction(
        transaction_id=transaction_id,
        portfolio_id="P1",
        instrument_id="EQ_US_AAPL",
        security_id=" EQ_US_AAPL ",
        transaction_type="DIVIDEND",
        quantity=Decimal("10.0000000000"),
        price=Decimal("100.0000000000"),
        gross_transaction_amount=Decimal("1000.0000000000"),
        allocated_cost_basis_local=Decimal("50.0000000000"),
        allocated_cost_basis_base=Decimal("60.0000000000"),
        trade_currency="usd",
        currency="usd",
        transaction_date=datetime(2026, 4, 10, 14, 0, tzinfo=UTC),
        trade_fee=Decimal("2.0000000000"),
        withholding_tax_amount=Decimal("15.0000000000"),
        other_interest_deductions_amount=Decimal("5.0000000000"),
        net_interest_amount=Decimal("80.0000000000"),
        realized_capital_pnl_local=Decimal("10.0000000000"),
        realized_fx_pnl_local=Decimal("1.0000000000"),
        realized_total_pnl_local=Decimal("11.0000000000"),
        realized_capital_pnl_base=Decimal("12.0000000000"),
        realized_fx_pnl_base=Decimal("2.0000000000"),
        realized_total_pnl_base=Decimal("14.0000000000"),
        transaction_fx_rate=Decimal("1.2000000000"),
        fx_contract_id="FXC-001",
        updated_at=datetime(2026, 4, 10, 16, 0, tzinfo=UTC),
    )
    transaction.cashflow = Cashflow(
        transaction_id=transaction_id,
        portfolio_id="P1",
        security_id="EQ_US_AAPL",
        cashflow_date=date(2026, 4, 10),
        epoch=2,
        amount=Decimal("100.0000000000"),
        currency="usd",
        classification="DIVIDEND",
        timing="EOD",
        calculation_type="BOOKED",
        is_position_flow=True,
        is_portfolio_flow=False,
        updated_at=datetime(2026, 4, 10, 17, 0, tzinfo=UTC),
    )
    transaction.costs = [
        TransactionCost(
            transaction_id=transaction_id,
            fee_type="brokerage",
            amount=Decimal("1.2500000000"),
            currency="usd",
            updated_at=datetime(2026, 4, 10, 18, 0, tzinfo=UTC),
        ),
        TransactionCost(
            transaction_id=transaction_id,
            fee_type="exchange_fee",
            amount=Decimal("0.7500000000"),
            currency="usd",
            updated_at=datetime(2026, 4, 10, 18, 30, tzinfo=UTC),
        ),
    ]
    return transaction


async def test_portfolio_exists_true(
    repository: SqlAlchemyTransactionEconomicsReader, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "P1"
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    exists = await repository.portfolio_exists("P1")

    assert exists is True


async def test_portfolio_exists_false(
    repository: SqlAlchemyTransactionEconomicsReader, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    exists = await repository.portfolio_exists("P404")

    assert exists is False


async def test_get_portfolio_base_currency(
    repository: SqlAlchemyTransactionEconomicsReader,
    mock_db_session: AsyncMock,
):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "USD"
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    base_currency = await repository.get_portfolio_base_currency("P1")

    assert base_currency == "USD"
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolios.base_currency" in compiled_query
    assert "portfolios.portfolio_id = 'P1'" in compiled_query


async def test_list_transaction_cost_evidence_filters_window_scope_and_eager_loads_costs(
    repository: SqlAlchemyTransactionEconomicsReader, mock_db_session: AsyncMock
):
    mock_rows = MagicMock()
    mock_rows.scalars.return_value.unique.return_value.all.return_value = [Transaction()]
    mock_db_session.execute = AsyncMock(return_value=mock_rows)

    rows = await repository.list_transaction_cost_evidence(
        portfolio_id="P1",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 5, 3),
        security_ids=["EQ_US_AAPL", "FI_US_TREASURY_10Y"],
        transaction_types=["BUY", "SELL"],
    )

    assert len(rows) == 1
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "transactions.transaction_date >= '2026-04-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2026-05-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2026-05-04 00:00:00'" in compiled_query
    assert "abs(transactions.gross_transaction_amount) > 0" in compiled_query
    assert "transactions.trade_fee > 0" in compiled_query
    assert "EXISTS (SELECT 1" in compiled_query
    assert "transaction_costs.transaction_id = transactions.transaction_id" in compiled_query
    assert "transaction_costs.amount > 0" in compiled_query
    assert (
        "trim(transactions.security_id) IN ('EQ_US_AAPL', 'FI_US_TREASURY_10Y')" in compiled_query
    )
    assert "transactions.transaction_type IN ('BUY', 'SELL')" in compiled_query
    assert "LEFT OUTER JOIN transaction_costs" in compiled_query
    assert "ORDER BY transactions.security_id ASC" in compiled_query


async def test_list_transaction_cost_evidence_filters_to_bounded_curve_keys(
    repository: SqlAlchemyTransactionEconomicsReader, mock_db_session: AsyncMock
):
    mock_rows = MagicMock()
    mock_rows.scalars.return_value.unique.return_value.all.return_value = [Transaction()]
    mock_db_session.execute = AsyncMock(return_value=mock_rows)

    rows = await repository.list_transaction_cost_evidence(
        portfolio_id="P1",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 5, 3),
        curve_keys=[("EQ_US_AAPL", "BUY", "USD"), ("EQ_US_MSFT", "SELL", "USD")],
    )

    assert len(rows) == 1
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(transactions.security_id) = 'EQ_US_AAPL'" in compiled_query
    assert "upper(trim(transactions.transaction_type)) = 'BUY'" in compiled_query
    assert "upper(trim(transactions.currency)) = 'USD'" in compiled_query
    assert "trim(transactions.security_id) = 'EQ_US_MSFT'" in compiled_query
    assert "upper(trim(transactions.transaction_type)) = 'SELL'" in compiled_query


async def test_list_transaction_cost_evidence_skips_read_when_curve_key_scope_empty(
    repository: SqlAlchemyTransactionEconomicsReader, mock_db_session: AsyncMock
):
    rows = await repository.list_transaction_cost_evidence(
        portfolio_id="P1",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 5, 3),
        curve_keys=[],
    )

    assert rows == []
    mock_db_session.execute.assert_not_awaited()


async def test_list_transaction_cost_curve_keys_uses_grouped_keyset_limit(
    repository: SqlAlchemyTransactionEconomicsReader, mock_db_session: AsyncMock
):
    mock_rows = MagicMock()
    mock_rows.all.return_value = [("EQ_US_MSFT", "BUY", "USD")]
    mock_db_session.execute = AsyncMock(return_value=mock_rows)

    keys = await repository.list_transaction_cost_curve_keys(
        portfolio_id="P1",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 5, 3),
        security_ids=["EQ_US_AAPL", "EQ_US_MSFT"],
        transaction_types=["BUY"],
        min_observation_count=2,
        after_key=("EQ_US_AAPL", "BUY", "USD"),
        limit=3,
    )

    assert keys == [("EQ_US_MSFT", "BUY", "USD")]
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "SELECT trim(transactions.security_id) AS security_id" in compiled_query
    assert "upper(trim(transactions.transaction_type)) AS transaction_type" in compiled_query
    assert "upper(trim(transactions.currency)) AS currency" in compiled_query
    assert "trim(transactions.security_id) IN ('EQ_US_AAPL', 'EQ_US_MSFT')" in compiled_query
    assert "transactions.transaction_type IN ('BUY')" in compiled_query
    assert "GROUP BY trim(transactions.security_id)" in compiled_query
    assert "HAVING count(transactions.id) >= 2" in compiled_query
    assert "trim(transactions.security_id) > 'EQ_US_AAPL'" in compiled_query
    assert "upper(trim(transactions.transaction_type)) > 'BUY'" in compiled_query
    assert "upper(trim(transactions.currency)) > 'USD'" in compiled_query
    assert "ORDER BY trim(transactions.security_id) ASC" in compiled_query
    assert "LIMIT 3" in compiled_query


async def test_list_transaction_cost_curve_available_security_ids_uses_grouped_subquery(
    repository: SqlAlchemyTransactionEconomicsReader, mock_db_session: AsyncMock
):
    mock_rows = MagicMock()
    mock_rows.scalars.return_value.all.return_value = ["EQ_US_AAPL"]
    mock_db_session.execute = AsyncMock(return_value=mock_rows)

    security_ids = await repository.list_transaction_cost_curve_available_security_ids(
        portfolio_id="P1",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 5, 3),
        security_ids=["EQ_US_AAPL", "EQ_US_MSFT"],
        transaction_types=["BUY"],
        min_observation_count=2,
    )

    assert security_ids == {"EQ_US_AAPL"}
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "SELECT DISTINCT anon_1.security_id" in compiled_query
    assert "GROUP BY trim(transactions.security_id)" in compiled_query
    assert "HAVING count(transactions.id) >= 2" in compiled_query
    assert "trim(transactions.security_id) IN ('EQ_US_AAPL', 'EQ_US_MSFT')" in compiled_query
    assert "transactions.transaction_type IN ('BUY')" in compiled_query


async def test_list_performance_component_economics_evidence_selects_latest_cashflow_epoch(
    repository: SqlAlchemyTransactionEconomicsReader, mock_db_session: AsyncMock
):
    mock_rows = MagicMock()
    mock_rows.scalars.return_value.unique.return_value.all.return_value = [
        _performance_economics_transaction()
    ]
    mock_db_session.execute = AsyncMock(return_value=mock_rows)

    rows = await repository.list_performance_component_economics_evidence(
        portfolio_id="P1",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 5, 3),
        security_ids=["EQ_US_AAPL"],
        transaction_types=["DIVIDEND"],
    )

    assert len(rows) == 1
    assert rows[0].transaction_id == "TXN-PERF-001"
    assert rows[0].security_id == " EQ_US_AAPL "
    assert rows[0].allocated_cost_basis_local == Decimal("50.0000000000")
    assert rows[0].allocated_cost_basis_base == Decimal("60.0000000000")
    assert rows[0].cashflow is not None
    assert rows[0].cashflow.amount == Decimal("100.0000000000")
    assert rows[0].cashflow.updated_at == datetime(2026, 4, 10, 17, 0, tzinfo=UTC)
    assert [cost.fee_type for cost in rows[0].costs] == ["brokerage", "exchange_fee"]
    assert [cost.amount for cost in rows[0].costs] == [
        Decimal("1.2500000000"),
        Decimal("0.7500000000"),
    ]
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "row_number() OVER" in compiled_query
    assert "PARTITION BY cashflows.transaction_id" in compiled_query
    assert "ORDER BY cashflows.epoch DESC, cashflows.id DESC" in compiled_query
    assert "anon_1.transaction_id = transactions.transaction_id" in compiled_query
    assert "anon_1.rn = 1" in compiled_query
    assert "LEFT OUTER JOIN cashflows AS cashflows_1 ON cashflows_1.id = anon_1.id" in (
        compiled_query
    )
    assert "trim(transactions.security_id) IN ('EQ_US_AAPL')" in compiled_query
    assert "transactions.transaction_type IN ('DIVIDEND')" in compiled_query
    assert "ORDER BY trim(transactions.security_id) ASC" in compiled_query
    assert "date(transactions.transaction_date) ASC" in compiled_query
    assert "transactions.transaction_id ASC" in compiled_query


async def test_list_performance_component_economics_evidence_applies_cursor_and_limit(
    repository: SqlAlchemyTransactionEconomicsReader, mock_db_session: AsyncMock
):
    mock_rows = MagicMock()
    transaction = _performance_economics_transaction(transaction_id="TXN-PERF-002")
    transaction.cashflow = None
    transaction.costs = []
    mock_rows.scalars.return_value.unique.return_value.all.return_value = [transaction]
    mock_db_session.execute = AsyncMock(return_value=mock_rows)

    rows = await repository.list_performance_component_economics_evidence(
        portfolio_id="P1",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 5, 3),
        security_ids=["EQ_US_AAPL", "EQ_US_MSFT"],
        transaction_types=["DIVIDEND", "BUY"],
        after_key=("EQ_US_AAPL", "2026-04-10", "TXN-001"),
        limit=11,
    )

    assert len(rows) == 1
    assert rows[0].transaction_id == "TXN-PERF-002"
    assert rows[0].cashflow is None
    assert rows[0].costs == ()
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(transactions.security_id) IN ('EQ_US_AAPL', 'EQ_US_MSFT')" in compiled_query
    assert "transactions.transaction_type IN ('DIVIDEND', 'BUY')" in compiled_query
    assert "trim(transactions.security_id) > 'EQ_US_AAPL'" in compiled_query
    assert "date(transactions.transaction_date) > '2026-04-10'" in compiled_query
    assert "transactions.transaction_id > 'TXN-001'" in compiled_query
    assert "ORDER BY trim(transactions.security_id) ASC" in compiled_query
    assert "date(transactions.transaction_date) ASC" in compiled_query
    assert "transactions.transaction_id ASC" in compiled_query
    assert "LIMIT 11" in compiled_query
