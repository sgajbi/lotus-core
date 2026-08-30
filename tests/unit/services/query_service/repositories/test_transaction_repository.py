# tests/unit/services/query_service/repositories/test_transaction_repository.py
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import Transaction
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.application.transaction_query import (
    TransactionLedgerFilters,
    transaction_ledger_query_spec,
)
from src.services.query_service.app.repositories.transaction_repository import TransactionRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession with configurable results."""
    session = AsyncMock(spec=AsyncSession)

    mock_result_list = MagicMock()
    mock_result_list.all.return_value = [
        (Transaction(), None, None, None, None),
        (Transaction(), None, None, None, None),
    ]
    mock_result_list.scalars.return_value.all.return_value = [Transaction(), Transaction()]

    mock_result_scalar = MagicMock()
    mock_result_scalar.scalar.return_value = 10

    def execute_side_effect(statement):
        if "count(" in str(statement.compile()).lower():
            return mock_result_scalar
        return mock_result_list

    session.execute = AsyncMock(side_effect=execute_side_effect)
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> TransactionRepository:
    """Provides an instance of the repository with a mock session."""
    return TransactionRepository(mock_db_session)


def _filters(**overrides: object) -> TransactionLedgerFilters:
    values = {"portfolio_id": "P1", **overrides}
    return TransactionLedgerFilters(**values)


def _query_spec(
    *,
    sort_by: str | None = None,
    sort_order: str | None = "desc",
    **filter_overrides: object,
):
    return transaction_ledger_query_spec(
        filters=_filters(**filter_overrides),
        sort_by=sort_by,
        sort_order=sort_order,
    )


async def test_get_transactions_default_sort(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    """
    GIVEN no specific sort order
    WHEN get_transactions is called
    THEN the query should order by transaction_date descending.
    """
    await repository.get_transactions(query_spec=_query_spec(), skip=0, limit=100)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "ORDER BY transactions.transaction_date DESC, transactions.id DESC" in compiled_query


async def test_get_transactions_security_drill_down_defaults_to_latest_first(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    await repository.get_transactions(
        query_spec=_query_spec(security_id=" SEC-HOLDING-1 "),
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
        query_spec=_query_spec(sort_by="quantity", sort_order="asc"),
        skip=0,
        limit=100,
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "ORDER BY transactions.quantity ASC, transactions.id ASC" in compiled_query


async def test_get_transactions_settlement_date_sort_uses_stable_tie_breaker(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    await repository.get_transactions(
        query_spec=_query_spec(sort_by="settlement_date", sort_order="asc"),
        skip=0,
        limit=100,
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "ORDER BY transactions.settlement_date ASC, transactions.id ASC" in compiled_query


async def test_get_transactions_with_all_filters(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    """
    GIVEN all possible filters
    WHEN get_transactions is called
    THEN the query should contain all corresponding WHERE clauses.
    """
    await repository.get_transactions(
        query_spec=_query_spec(
            security_id=" S1 ",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        ),
        skip=0,
        limit=100,
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "trim(transactions.security_id) = 'S1'" in compiled_query
    assert "transactions.transaction_date >= '2025-01-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2025-02-01 00:00:00'" in compiled_query


async def test_get_transactions_exact_identity_is_portfolio_scoped_and_index_backed(
    repository: TransactionRepository,
    mock_db_session: AsyncMock,
) -> None:
    await repository.get_transactions(
        query_spec=_query_spec(transaction_id="TX-EXACT"),
        skip=0,
        limit=2,
    )

    statement = mock_db_session.execute.await_args.args[0]
    compiled_query = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "transactions.transaction_id = 'TX-EXACT'" in compiled_query
    assert "LIMIT 2" in compiled_query
    exact_lookup_index = next(
        index
        for index in Transaction.__table__.indexes
        if index.name == "ix_transactions_portfolio_transaction_id"
    )
    assert [column.name for column in exact_lookup_index.columns] == [
        "portfolio_id",
        "transaction_id",
    ]


async def test_get_transactions_with_fx_filters(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    await repository.get_transactions(
        query_spec=_query_spec(
            transaction_type="FX_SWAP",
            component_type="FX_CONTRACT_OPEN",
            linked_transaction_group_id="LTG-FX-001",
            fx_contract_id="FXC-001",
            swap_event_id="FXSWAP-001",
            near_leg_group_id="FXSWAP-001-NEAR",
            far_leg_group_id="FXSWAP-001-FAR",
        ),
        skip=0,
        limit=100,
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
        query_spec=_query_spec(as_of_date=date(2025, 1, 15)),
        skip=0,
        limit=100,
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.transaction_date < '2025-01-16 00:00:00'" in compiled_query


async def test_establish_transaction_ledger_read_snapshot_is_repeatable_and_read_only(
    repository: TransactionRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.in_transaction.return_value = False

    await repository.establish_transaction_ledger_read_snapshot()

    statement = mock_db_session.execute.await_args.args[0]
    assert str(statement) == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"


async def test_establish_transaction_ledger_read_snapshot_rejects_an_existing_transaction(
    repository: TransactionRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.in_transaction.return_value = True

    with pytest.raises(
        RuntimeError,
        match="must be established before the first database read",
    ):
        await repository.establish_transaction_ledger_read_snapshot()

    mock_db_session.execute.assert_not_awaited()


async def test_get_transactions_pages_transactions_before_loading_cost_collection(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    rows = await repository.get_transactions(
        query_spec=_query_spec(instrument_id="INST-AAPL-USD"),
        skip=0,
        limit=25,
    )

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.instrument_id = 'INST-AAPL-USD'" in compiled_query
    assert "JOIN LATERAL" in compiled_query
    assert "array_agg(transaction_costs.amount ORDER BY transaction_costs.id ASC)" in compiled_query
    assert "LEFT OUTER JOIN transaction_costs" not in compiled_query
    assert "LEFT OUTER JOIN LATERAL (SELECT cashflows.id" in compiled_query
    assert "ORDER BY cashflows.epoch DESC, cashflows.id DESC" in compiled_query
    assert "LIMIT 25" in compiled_query
    assert compiled_query.index("LIMIT 25") < compiled_query.index("JOIN LATERAL")
    assert len(rows) == 2
    assert not hasattr(rows[0], "transaction")


async def test_get_transactions_count(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    """
    GIVEN a set of filters
    WHEN get_transactions_count is called
    THEN it should build the correct count query and return the scalar result.
    """
    count = await repository.get_transactions_count(filters=_filters(security_id=" S1 "))

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

    count = await repository.get_transactions_count(filters=_filters(portfolio_id="P_EMPTY"))

    assert count == 0


async def test_get_transactions_count_applies_identity_and_date_filters(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    count = await repository.get_transactions_count(
        filters=_filters(
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
        ),
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


async def test_get_transactions_count_with_date_filters(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalar.return_value = 2
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    count = await repository.get_transactions_count(
        filters=_filters(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        ),
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

    count = await repository.get_transactions_count(filters=_filters(as_of_date=date(2025, 1, 15)))

    assert count == 3
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.transaction_date < '2025-01-16 00:00:00'" in compiled_query


async def test_list_realized_tax_evidence_transactions_filters_explicit_tax_evidence(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    mock_rows = MagicMock()
    mock_rows.scalars.return_value.all.return_value = [Transaction()]
    mock_db_session.execute = AsyncMock(return_value=mock_rows)

    rows = await repository.list_realized_tax_evidence_transactions(
        filters=_filters(
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
            as_of_date=date(2026, 5, 3),
        ),
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
        filters=_filters(instrument_id="INST-AAPL-USD"),
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

    latest = await repository.get_latest_business_date(calendar_code="GLOBAL")

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
    assert "ORDER BY fx_rates.rate_date DESC, fx_rates.id DESC" in compiled_query


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
        filters=_filters(
            transaction_type="FX_SWAP",
            component_type="FX_CONTRACT_OPEN",
            linked_transaction_group_id="LTG-1",
            fx_contract_id="FXC-1",
            swap_event_id="SWAP-1",
            near_leg_group_id="NEAR-1",
            far_leg_group_id="FAR-1",
        ),
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
        filters=_filters(
            transaction_type="FX_FORWARD",
            component_type="FX_CASH_SETTLEMENT_BUY",
            fx_contract_id="FXC-001",
            swap_event_id="FXSWAP-001",
        ),
    )

    assert count == 4
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transactions.transaction_type = 'FX_FORWARD'" in compiled_query
    assert "transactions.component_type = 'FX_CASH_SETTLEMENT_BUY'" in compiled_query
    assert "transactions.fx_contract_id = 'FXC-001'" in compiled_query
    assert "transactions.swap_event_id = 'FXSWAP-001'" in compiled_query


async def test_get_transaction_ledger_input_evidence_applies_complete_scope_filters(
    repository: TransactionRepository, mock_db_session: AsyncMock
):
    transaction_updated_at = datetime(2025, 2, 3, 14, 45, tzinfo=UTC)
    cost_updated_at = datetime(2025, 2, 3, 15, 0, tzinfo=UTC)
    cashflow_updated_at = datetime(2025, 2, 3, 15, 15, tzinfo=UTC)
    fx_updated_at = datetime(2025, 2, 3, 15, 30, tzinfo=UTC)
    row = MagicMock(
        transaction_count=4,
        transaction_latest_at=transaction_updated_at,
        transaction_digest="tx-digest",
        transaction_cost_latest_at=cost_updated_at,
        transaction_cost_digest="cost-digest",
        selected_cashflow_latest_at=cashflow_updated_at,
        selected_cashflow_digest="cashflow-digest",
        selected_fx_rate_latest_at=fx_updated_at,
        selected_fx_rate_digest="fx-digest",
    )
    mock_result = MagicMock()
    mock_result.one.return_value = row
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    result = await repository.get_transaction_ledger_input_evidence(
        filters=_filters(
            security_id=" S1 ",
            transaction_type="FX_FORWARD",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            as_of_date=date(2025, 1, 15),
        ),
        reporting_currency="SGD",
        as_of_date=date(2025, 1, 15),
    )

    assert result.transaction_count == 4
    assert result.latest_evidence_timestamp == fx_updated_at
    assert result.transaction_digest == "tx-digest"
    assert result.transaction_cost_digest == "cost-digest"
    assert result.selected_cashflow_digest == "cashflow-digest"
    assert result.selected_fx_rate_digest == "fx-digest"
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "transaction_ledger_transaction_evidence" in compiled_query
    assert "transaction_ledger_cost_evidence" in compiled_query
    assert "transaction_ledger_cashflow_evidence" in compiled_query
    assert "transaction_ledger_fx_evidence" in compiled_query
    assert "string_agg" in compiled_query.lower()
    assert compiled_query.lower().count("jsonb_build_array") >= 5
    assert " || " in compiled_query
    assert "timezone('UTC', transactions.transaction_date)" in compiled_query
    assert 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"' in compiled_query
    assert "to_char(transaction_ledger_ranked_fx_rates.rate_date, 'YYYY-MM-DD')" in compiled_query
    assert "sha256" in compiled_query.lower()
    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "trim(transactions.security_id) = 'S1'" in compiled_query
    assert "transactions.transaction_type = 'FX_FORWARD'" in compiled_query
    assert "transactions.transaction_date >= '2025-01-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2025-02-01 00:00:00'" in compiled_query
    assert "transactions.transaction_date < '2025-01-16 00:00:00'" in compiled_query
