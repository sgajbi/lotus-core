from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Cashflow,
    FxRate,
    Portfolio,
    Transaction,
    TransactionCost,
)
from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.query_service.app.application.transaction_query import (
    TransactionLedgerFilters,
    transaction_ledger_query_spec,
)
from src.services.query_service.app.repositories.transaction_repository import TransactionRepository
from src.services.query_service.app.services.transaction_records import (
    transaction_ledger_reconstruction_evidence,
)

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


async def test_transaction_ledger_identity_binds_only_selected_material_inputs(
    clean_db,
    db_engine,
    async_db_session: AsyncSession,
) -> None:
    with Session(db_engine) as session:
        session.add_all(
            [
                Portfolio(
                    portfolio_id="PORT-EVIDENCE",
                    base_currency="USD",
                    open_date=date(2024, 1, 1),
                    risk_exposure="BALANCED",
                    investment_time_horizon="LONG_TERM",
                    portfolio_type="ADVISORY",
                    booking_center_code="SG",
                    client_id="CLIENT-EVIDENCE",
                    status="ACTIVE",
                ),
                Portfolio(
                    portfolio_id="PORT-UNRELATED",
                    base_currency="EUR",
                    open_date=date(2024, 1, 1),
                    risk_exposure="BALANCED",
                    investment_time_horizon="LONG_TERM",
                    portfolio_type="ADVISORY",
                    booking_center_code="SG",
                    client_id="CLIENT-UNRELATED",
                    status="ACTIVE",
                ),
                Transaction(
                    transaction_id="TX-EVIDENCE",
                    portfolio_id="PORT-EVIDENCE",
                    instrument_id="INST-EVIDENCE",
                    security_id="SEC-EVIDENCE",
                    transaction_type="BUY",
                    quantity=Decimal("10"),
                    price=Decimal("100"),
                    gross_transaction_amount=Decimal("1000"),
                    trade_currency="USD",
                    currency="USD",
                    transaction_date=datetime(2026, 1, 3, tzinfo=UTC),
                    costs=[
                        TransactionCost(
                            transaction_id="TX-EVIDENCE",
                            fee_type="BROKERAGE",
                            amount=Decimal("2"),
                            currency="USD",
                        )
                    ],
                ),
                Transaction(
                    transaction_id="TX-UNRELATED",
                    portfolio_id="PORT-UNRELATED",
                    instrument_id="INST-UNRELATED",
                    security_id="SEC-UNRELATED",
                    transaction_type="BUY",
                    quantity=Decimal("5"),
                    price=Decimal("50"),
                    gross_transaction_amount=Decimal("250"),
                    trade_currency="EUR",
                    currency="EUR",
                    transaction_date=datetime(2026, 1, 3, tzinfo=UTC),
                    costs=[
                        TransactionCost(
                            transaction_id="TX-UNRELATED",
                            fee_type="BROKERAGE",
                            amount=Decimal("3"),
                            currency="EUR",
                        )
                    ],
                ),
                Cashflow(
                    transaction_id="TX-EVIDENCE",
                    portfolio_id="PORT-EVIDENCE",
                    security_id="SEC-EVIDENCE",
                    cashflow_date=date(2026, 1, 3),
                    epoch=1,
                    amount=Decimal("-900"),
                    currency="USD",
                    classification="TRADE_SETTLEMENT",
                    timing="SETTLED",
                    calculation_type="TRANSACTION_DERIVED",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                ),
                Cashflow(
                    transaction_id="TX-EVIDENCE",
                    portfolio_id="PORT-EVIDENCE",
                    security_id="SEC-EVIDENCE",
                    cashflow_date=date(2026, 1, 3),
                    epoch=2,
                    amount=Decimal("-1000"),
                    currency="USD",
                    classification="TRADE_SETTLEMENT",
                    timing="SETTLED",
                    calculation_type="TRANSACTION_DERIVED",
                    is_position_flow=True,
                    is_portfolio_flow=False,
                ),
                FxRate(
                    from_currency="USD",
                    to_currency="SGD",
                    rate_date=date(2026, 1, 31),
                    rate=Decimal("1.35"),
                ),
                FxRate(
                    from_currency="EUR",
                    to_currency="JPY",
                    rate_date=date(2026, 1, 31),
                    rate=Decimal("160"),
                ),
            ]
        )
        session.commit()

    filters = TransactionLedgerFilters(
        portfolio_id="PORT-EVIDENCE",
        as_of_date=date(2026, 1, 31),
    )
    repository = TransactionRepository(async_db_session)

    async def read_evidence():
        return await repository.get_transaction_ledger_input_evidence(
            filters=filters,
            reporting_currency="SGD",
            as_of_date=date(2026, 1, 31),
        )

    def scope_id(evidence) -> str:
        return transaction_ledger_reconstruction_evidence(
            portfolio_id="PORT-EVIDENCE",
            response_as_of_date=date(2026, 1, 31),
            reporting_currency="SGD",
            total_count=evidence.transaction_count,
            latest_evidence_timestamp=evidence.latest_evidence_timestamp,
            ledger_filters=filters,
            input_evidence=evidence,
        ).scope_id

    statements: list[str] = []
    sync_engine = async_db_session.bind.sync_engine

    def capture_evidence_sql(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(sync_engine, "before_cursor_execute", capture_evidence_sql)
    try:
        baseline = await read_evidence()
    finally:
        event.remove(sync_engine, "before_cursor_execute", capture_evidence_sql)

    evidence_selects = [
        statement for statement in statements if statement.lstrip().upper().startswith("WITH")
    ]
    assert len(evidence_selects) == 1
    assert "transaction_ledger_transaction_evidence" in evidence_selects[0]
    assert "transaction_ledger_cost_evidence" in evidence_selects[0]
    assert "transaction_ledger_cashflow_evidence" in evidence_selects[0]
    assert "transaction_ledger_fx_evidence" in evidence_selects[0]
    baseline_scope_id = scope_id(baseline)

    await async_db_session.execute(
        update(TransactionCost)
        .where(TransactionCost.transaction_id == "TX-UNRELATED")
        .values(amount=Decimal("4"))
    )
    await async_db_session.execute(
        update(FxRate)
        .where(FxRate.from_currency == "EUR", FxRate.to_currency == "JPY")
        .values(rate=Decimal("161"))
    )
    await async_db_session.execute(
        update(Cashflow)
        .where(Cashflow.transaction_id == "TX-EVIDENCE", Cashflow.epoch == 1)
        .values(amount=Decimal("-901"))
    )
    await async_db_session.commit()

    unrelated_changes = await read_evidence()
    assert scope_id(unrelated_changes) == baseline_scope_id

    await async_db_session.execute(
        update(Transaction)
        .where(Transaction.transaction_id == "TX-EVIDENCE")
        .values(price=Decimal("101"))
    )
    await async_db_session.commit()
    changed_transaction = await read_evidence()
    assert changed_transaction.transaction_digest != baseline.transaction_digest
    assert scope_id(changed_transaction) != baseline_scope_id

    await async_db_session.execute(
        update(TransactionCost)
        .where(TransactionCost.transaction_id == "TX-EVIDENCE")
        .values(amount=Decimal("2.5"))
    )
    await async_db_session.commit()
    changed_cost = await read_evidence()
    assert changed_cost.transaction_cost_digest != changed_transaction.transaction_cost_digest
    assert scope_id(changed_cost) != scope_id(changed_transaction)

    await async_db_session.execute(
        update(Cashflow)
        .where(Cashflow.transaction_id == "TX-EVIDENCE", Cashflow.epoch == 2)
        .values(amount=Decimal("-1001"))
    )
    await async_db_session.commit()
    changed_cashflow = await read_evidence()
    assert changed_cashflow.selected_cashflow_digest != changed_cost.selected_cashflow_digest
    assert scope_id(changed_cashflow) != scope_id(changed_cost)

    await async_db_session.execute(
        update(FxRate)
        .where(FxRate.from_currency == "USD", FxRate.to_currency == "SGD")
        .values(rate=Decimal("1.36"))
    )
    await async_db_session.commit()
    changed_fx = await read_evidence()
    assert changed_fx.selected_fx_rate_digest != changed_cashflow.selected_fx_rate_digest
    assert scope_id(changed_fx) != scope_id(changed_cashflow)
