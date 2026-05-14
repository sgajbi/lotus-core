# tests/unit/services/query_service/repositories/test_transaction_repository.py
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Transaction
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

    assert "ORDER BY transactions.transaction_date DESC" in compiled_query


async def test_get_transactions_security_drill_down_defaults_to_latest_first(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    await repository.get_transactions(
        portfolio_id="P1",
        security_id="SEC-HOLDING-1",
        skip=0,
        limit=25,
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.security_id = 'SEC-HOLDING-1'" in compiled_query
    assert "ORDER BY transactions.transaction_date DESC" in compiled_query


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

    assert "ORDER BY transactions.quantity ASC" in compiled_query


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

    assert "ORDER BY transactions.transaction_date DESC" in compiled_query


async def test_get_transactions_invalid_sort_order_falls_back_to_desc(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    await repository.get_transactions(
        portfolio_id="P1", skip=0, limit=100, sort_by="quantity", sort_order="invalid"
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "ORDER BY transactions.quantity DESC" in compiled_query


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
        security_id="S1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "transactions.security_id = 'S1'" in compiled_query
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
    count = await repository.get_transactions_count(portfolio_id="P1", security_id="S1")

    assert count == 10
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "count(transactions.id)" in compiled_query.lower()
    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "transactions.security_id = 'S1'" in compiled_query


async def test_get_transactions_count_returns_zero_when_scalar_none(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    mock_result_scalar_none = MagicMock()
    mock_result_scalar_none.scalar.return_value = None
    mock_db_session.execute = AsyncMock(return_value=mock_result_scalar_none)

    count = await repository.get_transactions_count(portfolio_id="P_EMPTY")

    assert count == 0


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
    assert "transactions.security_id IN ('EQ_US_AAPL', 'FI_US_TREASURY_10Y')" in compiled_query
    assert "transactions.transaction_type IN ('BUY', 'SELL')" in compiled_query
    assert "LEFT OUTER JOIN transaction_costs" in compiled_query
    assert "ORDER BY transactions.security_id ASC" in compiled_query


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
        from_currency="USD",
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
        from_currency="USD",
        to_currency="SGD",
        as_of_date=date(2026, 4, 30),
    )

    assert rate == Decimal("1.36")
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "fx_rates.from_currency = 'USD'" in compiled_query
    assert "fx_rates.to_currency = 'SGD'" in compiled_query
    assert "fx_rates.rate_date <= '2026-04-30'" in compiled_query
    assert "ORDER BY fx_rates.rate_date DESC" in compiled_query


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
        security_id="S1",
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
    assert "transactions.security_id = 'S1'" in compiled_query
    assert "transactions.transaction_type = 'FX_FORWARD'" in compiled_query
    assert "transactions.transaction_date >= '2025-01-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2025-02-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2025-01-16 00:00:00'" in compiled_query
