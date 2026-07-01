# tests/unit/services/query_service/repositories/test_transaction_repository.py
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Cashflow, Transaction, TransactionCost
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.transaction_repository import TransactionRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession with configurable results."""
    session = AsyncMock(spec=AsyncSession)

    mock_result_list = MagicMock()
    mock_result_list.scalars.return_value.all.return_value = [Transaction(), Transaction()]

    mock_result_scalar = MagicMock()
    mock_result_scalar.scalar.return_value = 10

    def execute_side_effect(statement):
        if "count" in str(statement.compile()).lower():
            return mock_result_scalar
        return mock_result_list

    session.execute = AsyncMock(side_effect=execute_side_effect)
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> TransactionRepository:
    """Provides an instance of the repository with a mock session."""
    return TransactionRepository(mock_db_session)


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


async def test_get_transactions_default_sort(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    """
    GIVEN no specific sort order
    WHEN get_transactions is called
    THEN the query should order by transaction_date descending.
    """
    await repository.get_transactions(portfolio_id="P1", skip=0, limit=100)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "ORDER BY transactions.transaction_date DESC, transactions.id DESC" in compiled_query


async def test_get_transactions_security_drill_down_defaults_to_latest_first(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    await repository.get_transactions(
        portfolio_id="P1",
        security_id=" SEC-HOLDING-1 ",
        skip=0,
        limit=25,
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "trim(transactions.security_id) = 'SEC-HOLDING-1'" in compiled_query
    assert "ORDER BY transactions.transaction_date DESC, transactions.id DESC" in compiled_query


async def test_get_transactions_custom_sort(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    """
    GIVEN a custom sort field and order
    WHEN get_transactions is called
    THEN the query should use the specified order.
    """
    await repository.get_transactions(
        portfolio_id="P1", skip=0, limit=100, sort_by="quantity", sort_order="asc"
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "ORDER BY transactions.quantity ASC, transactions.id ASC" in compiled_query


async def test_get_transactions_invalid_sort_falls_back_to_default(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    """
    GIVEN an invalid sort field
    WHEN get_transactions is called
    THEN the query should fall back to the default sort order.
    """
    await repository.get_transactions(portfolio_id="P1", skip=0, limit=100, sort_by="invalid_field")

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "ORDER BY transactions.transaction_date DESC, transactions.id DESC" in compiled_query


async def test_get_transactions_invalid_sort_order_falls_back_to_desc(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    await repository.get_transactions(
        portfolio_id="P1", skip=0, limit=100, sort_by="quantity", sort_order="invalid"
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "ORDER BY transactions.quantity DESC, transactions.id DESC" in compiled_query


async def test_get_transactions_with_all_filters(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    """
    GIVEN all possible filters
    WHEN get_transactions is called
    THEN the query should contain all corresponding WHERE clauses.
    """
    await repository.get_transactions(
        portfolio_id="P1",
        skip=0,
        limit=100,
        security_id=" S1 ",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "trim(transactions.security_id) = 'S1'" in compiled_query
    assert "transactions.transaction_date >= '2025-01-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2025-02-01 00:00:00'" in compiled_query


async def test_get_transactions_with_fx_filters(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    await repository.get_transactions(
        portfolio_id="P1",
        skip=0,
        limit=100,
        transaction_type="FX_SWAP",
        component_type="FX_CONTRACT_OPEN",
        linked_transaction_group_id="LTG-FX-001",
        fx_contract_id="FXC-001",
        swap_event_id="FXSWAP-001",
        near_leg_group_id="FXSWAP-001-NEAR",
        far_leg_group_id="FXSWAP-001-FAR",
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.transaction_type = 'FX_SWAP'" in compiled_query
    assert "transactions.component_type = 'FX_CONTRACT_OPEN'" in compiled_query
    assert "transactions.linked_transaction_group_id = 'LTG-FX-001'" in compiled_query
    assert "transactions.fx_contract_id = 'FXC-001'" in compiled_query
    assert "transactions.swap_event_id = 'FXSWAP-001'" in compiled_query
    assert "transactions.near_leg_group_id = 'FXSWAP-001-NEAR'" in compiled_query
    assert "transactions.far_leg_group_id = 'FXSWAP-001-FAR'" in compiled_query


async def test_get_transactions_with_as_of_date_filter(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    await repository.get_transactions(
        portfolio_id="P1",
        skip=0,
        limit=100,
        as_of_date=date(2025, 1, 15),
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.transaction_date < '2025-01-16 00:00:00'" in compiled_query


async def test_get_transactions_applies_instrument_filter_and_eager_loads_related_rows(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    await repository.get_transactions(
        portfolio_id="P1",
        skip=0,
        limit=25,
        instrument_id="INST-AAPL-USD",
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.instrument_id = 'INST-AAPL-USD'" in compiled_query
    assert "LEFT OUTER JOIN cashflows" in compiled_query
    assert "LEFT OUTER JOIN transaction_costs" in compiled_query


async def test_get_transactions_count(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    """
    GIVEN a set of filters
    WHEN get_transactions_count is called
    THEN it should build the correct count query and return the scalar result.
    """
    count = await repository.get_transactions_count(portfolio_id="P1", security_id=" S1 ")

    assert count == 10
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "count(transactions.id)" in compiled_query.lower()
    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "trim(transactions.security_id) = 'S1'" in compiled_query


async def test_get_transactions_count_returns_zero_when_scalar_none(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    mock_result_scalar_none = MagicMock()
    mock_result_scalar_none.scalar.return_value = None
    mock_db_session.execute = AsyncMock(return_value=mock_result_scalar_none)

    count = await repository.get_transactions_count(portfolio_id="P_EMPTY")

    assert count == 0


async def test_get_transactions_count_applies_identity_and_date_filters(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    count = await repository.get_transactions_count(
        portfolio_id="P1",
        instrument_id="INST-AAPL-USD",
        transaction_type="BUY",
        component_type="SECURITY_TRADE",
        linked_transaction_group_id="LTG-001",
        fx_contract_id="FXC-001",
        swap_event_id="SWAP-001",
        near_leg_group_id="NEAR-001",
        far_leg_group_id="FAR-001",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert count == 10
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "transactions.instrument_id = 'INST-AAPL-USD'" in compiled_query
    assert "transactions.transaction_type = 'BUY'" in compiled_query
    assert "transactions.component_type = 'SECURITY_TRADE'" in compiled_query
    assert "transactions.linked_transaction_group_id = 'LTG-001'" in compiled_query
    assert "transactions.fx_contract_id = 'FXC-001'" in compiled_query
    assert "transactions.swap_event_id = 'SWAP-001'" in compiled_query
    assert "transactions.near_leg_group_id = 'NEAR-001'" in compiled_query
    assert "transactions.far_leg_group_id = 'FAR-001'" in compiled_query
    assert "transactions.transaction_date >= '2025-01-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2025-02-01 00:00:00'" in compiled_query


async def test_portfolio_exists_true(repository: TransactionRepository, mock_db_session: AsyncMock):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "P1"
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    exists = await repository.portfolio_exists("P1")

    assert exists is True


async def test_portfolio_exists_false(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    exists = await repository.portfolio_exists("P404")

    assert exists is False


async def test_get_portfolio_base_currency(
    repository: TransactionRepository,
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


async def test_get_transactions_count_with_date_filters(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalar.return_value = 2
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    count = await repository.get_transactions_count(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert count == 2
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.transaction_date >= '2025-01-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2025-02-01 00:00:00'" in compiled_query


async def test_get_transactions_count_with_as_of_date(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalar.return_value = 3
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    count = await repository.get_transactions_count(
        portfolio_id="P1",
        as_of_date=date(2025, 1, 15),
    )

    assert count == 3
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.transaction_date < '2025-01-16 00:00:00'" in compiled_query


async def test_list_transaction_cost_evidence_filters_window_scope_and_eager_loads_costs(
    repository: TransactionRepository, mock_db_session: AsyncMock
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
    repository: TransactionRepository, mock_db_session: AsyncMock
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
    repository: TransactionRepository, mock_db_session: AsyncMock
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
    repository: TransactionRepository, mock_db_session: AsyncMock
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
    repository: TransactionRepository, mock_db_session: AsyncMock
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
    repository: TransactionRepository, mock_db_session: AsyncMock
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
    repository: TransactionRepository, mock_db_session: AsyncMock
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


async def test_list_realized_tax_evidence_transactions_filters_explicit_tax_evidence(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    mock_rows = MagicMock()
    mock_rows.scalars.return_value.all.return_value = [Transaction()]
    mock_db_session.execute = AsyncMock(return_value=mock_rows)

    rows = await repository.list_realized_tax_evidence_transactions(
        portfolio_id="P1",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        as_of_date=date(2026, 5, 3),
    )

    assert len(rows) == 1
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "transactions.withholding_tax_amount IS NOT NULL" in compiled_query
    assert "transactions.other_interest_deductions_amount IS NOT NULL" in compiled_query
    assert "transactions.transaction_date >= '2026-04-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2026-05-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2026-05-04 00:00:00'" in compiled_query
    assert "ORDER BY transactions.currency ASC" in compiled_query
    assert "transactions.transaction_date ASC" in compiled_query
    assert "transactions.transaction_id ASC" in compiled_query


async def test_get_transactions_count_applies_instrument_filter(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalar.return_value = 6
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    count = await repository.get_transactions_count(
        portfolio_id="P1",
        instrument_id="INST-AAPL-USD",
    )

    assert count == 6
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.instrument_id = 'INST-AAPL-USD'" in compiled_query


async def test_get_latest_business_date(
    repository: TransactionRepository,
    mock_db_session: AsyncMock,
):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = date(2025, 1, 31)
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    latest = await repository.get_latest_business_date()

    assert latest == date(2025, 1, 31)
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "business_dates.calendar_code = 'GLOBAL'" in compiled_query


async def test_get_latest_fx_rate_returns_identity_for_same_currency(
    repository: TransactionRepository,
    mock_db_session: AsyncMock,
):
    rate = await repository.get_latest_fx_rate(
        from_currency=" usd ",
        to_currency="USD",
        as_of_date=date(2026, 4, 30),
    )

    assert rate == Decimal("1")
    mock_db_session.execute.assert_not_awaited()


async def test_get_latest_fx_rate_queries_latest_available_rate(
    repository: TransactionRepository,
    mock_db_session: AsyncMock,
):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = Decimal("1.36")
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    rate = await repository.get_latest_fx_rate(
        from_currency=" usd ",
        to_currency=" sgd ",
        as_of_date=date(2026, 4, 30),
    )

    assert rate == Decimal("1.36")
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "upper(trim(fx_rates.from_currency)) = 'USD'" in compiled_query
    assert "upper(trim(fx_rates.to_currency)) = 'SGD'" in compiled_query
    assert "fx_rates.rate_date <= '2026-04-30'" in compiled_query
    assert "ORDER BY fx_rates.rate_date DESC" in compiled_query


async def test_list_known_instrument_security_ids_queries_instrument_master(
    repository: TransactionRepository,
    mock_db_session: AsyncMock,
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["S1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    security_ids = await repository.list_known_instrument_security_ids([" S1 ", "S2", "S1"])

    assert security_ids == {"S1"}
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(instruments.security_id) IN ('S1', 'S2')" in compiled_query


async def test_list_known_instrument_security_ids_skips_empty_scope(
    repository: TransactionRepository,
    mock_db_session: AsyncMock,
):
    assert await repository.list_known_instrument_security_ids([" ", ""]) == set()
    mock_db_session.execute.assert_not_awaited()


async def test_get_transactions_count_with_component_and_fx_filters(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalar.return_value = 4
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    count = await repository.get_transactions_count(
        portfolio_id="P1",
        transaction_type="FX_SWAP",
        component_type="FX_CONTRACT_OPEN",
        linked_transaction_group_id="LTG-1",
        fx_contract_id="FXC-1",
        swap_event_id="SWAP-1",
        near_leg_group_id="NEAR-1",
        far_leg_group_id="FAR-1",
    )

    assert count == 4
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.component_type = 'FX_CONTRACT_OPEN'" in compiled_query
    assert "transactions.linked_transaction_group_id = 'LTG-1'" in compiled_query
    assert "transactions.fx_contract_id = 'FXC-1'" in compiled_query
    assert "transactions.swap_event_id = 'SWAP-1'" in compiled_query
    assert "transactions.near_leg_group_id = 'NEAR-1'" in compiled_query
    assert "transactions.far_leg_group_id = 'FAR-1'" in compiled_query


async def test_get_transactions_count_with_fx_filters(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalar.return_value = 4
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    count = await repository.get_transactions_count(
        portfolio_id="P1",
        transaction_type="FX_FORWARD",
        component_type="FX_CASH_SETTLEMENT_BUY",
        fx_contract_id="FXC-001",
        swap_event_id="FXSWAP-001",
    )

    assert count == 4
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.transaction_type = 'FX_FORWARD'" in compiled_query
    assert "transactions.component_type = 'FX_CASH_SETTLEMENT_BUY'" in compiled_query
    assert "transactions.fx_contract_id = 'FXC-001'" in compiled_query
    assert "transactions.swap_event_id = 'FXSWAP-001'" in compiled_query


async def test_get_latest_evidence_timestamp_applies_transaction_window_filters(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    updated_at = datetime(2025, 2, 3, 14, 45, tzinfo=UTC)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = updated_at
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    result = await repository.get_latest_evidence_timestamp(
        portfolio_id="P1",
        security_id=" S1 ",
        transaction_type="FX_FORWARD",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        as_of_date=date(2025, 1, 15),
    )

    assert result == updated_at
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(transactions.updated_at)" in compiled_query.lower()
    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "trim(transactions.security_id) = 'S1'" in compiled_query
    assert "transactions.transaction_type = 'FX_FORWARD'" in compiled_query
    assert "transactions.transaction_date >= '2025-01-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2025-02-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2025-01-16 00:00:00'" in compiled_query
