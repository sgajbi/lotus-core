from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import Cashflow, Portfolio, Transaction, TransactionCost
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.query_service.app.application.transaction_query import (
    TransactionLedgerFilters,
    transaction_ledger_query_spec,
)
from src.services.query_service.app.repositories.transaction_repository import TransactionRepository

pytestmark = pytest.mark.asyncio


def _transaction(*, sequence: int, cost_count: int) -> Transaction:
    transaction_id = f"TX-PAGE-{sequence}"
    return Transaction(
        transaction_id=transaction_id,
        portfolio_id="PORT-PAGE",
        instrument_id=f"INST-{sequence}",
        security_id=f"SEC-{sequence}",
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
        transaction_date=datetime(2026, 1, sequence, tzinfo=UTC),
        costs=[
            TransactionCost(
                transaction_id=transaction_id,
                fee_type=f"FEE-{cost_index}",
                amount=Decimal(cost_index + 1),
                currency="USD",
            )
            for cost_index in range(cost_count)
        ],
    )


def _cashflow(*, epoch: int, amount: str) -> Cashflow:
    return Cashflow(
        transaction_id="TX-PAGE-3",
        portfolio_id="PORT-PAGE",
        security_id="SEC-3",
        cashflow_date=date(2026, 1, 3),
        epoch=epoch,
        amount=Decimal(amount),
        currency="USD",
        classification="TRADE_SETTLEMENT",
        timing="SETTLED",
        calculation_type="TRANSACTION_DERIVED",
        is_position_flow=True,
        is_portfolio_flow=False,
    )


async def test_transaction_page_and_costs_share_one_bounded_statement_snapshot(
    clean_db,
    db_engine,
    async_db_session: AsyncSession,
) -> None:
    with Session(db_engine) as session:
        session.add(
            Portfolio(
                portfolio_id="PORT-PAGE",
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="BALANCED",
                investment_time_horizon="LONG_TERM",
                portfolio_type="ADVISORY",
                booking_center_code="SG",
                client_id="CLIENT-PAGE",
                status="ACTIVE",
            )
        )
        session.add_all(
            [
                _transaction(sequence=1, cost_count=1),
                _transaction(sequence=2, cost_count=2),
                _transaction(sequence=3, cost_count=3),
                _cashflow(epoch=1, amount="-900"),
                _cashflow(epoch=2, amount="-1000"),
            ]
        )
        session.commit()

    statements: list[str] = []
    sync_engine = async_db_session.bind.sync_engine

    def capture_sql(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(sync_engine, "before_cursor_execute", capture_sql)
    try:
        transactions = await TransactionRepository(async_db_session).get_transactions(
            query_spec=transaction_ledger_query_spec(
                filters=TransactionLedgerFilters(portfolio_id="PORT-PAGE"),
                sort_by=None,
                sort_order="desc",
            ),
            skip=0,
            limit=2,
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", capture_sql)

    assert [transaction.transaction_id for transaction in transactions] == [
        "TX-PAGE-3",
        "TX-PAGE-2",
    ]
    assert [len(transaction.costs) for transaction in transactions] == [3, 2]
    assert transactions[0].cashflow is not None
    assert transactions[0].cashflow.amount == Decimal("-1000")
    assert transactions[1].cashflow is None

    select_statements = [
        statement for statement in statements if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(select_statements) == 1
    assert "JOIN LATERAL" in select_statements[0]
    assert (
        "array_agg(transaction_costs.amount ORDER BY transaction_costs.id ASC)"
        in (select_statements[0])
    )
    assert "LEFT OUTER JOIN transaction_costs" not in select_statements[0]
    assert "LIMIT" in select_statements[0]
    assert select_statements[0].index("LIMIT") < select_statements[0].index("JOIN LATERAL")
