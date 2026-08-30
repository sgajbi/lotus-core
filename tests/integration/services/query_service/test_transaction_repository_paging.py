from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Cashflow,
    FxRate,
    Instrument,
    Portfolio,
    Transaction,
    TransactionCost,
)
from sqlalchemy import event, text, update
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
from src.services.query_service.app.services.transaction_service import TransactionService
from tests.test_support.tenant import TEST_TENANT_CONTEXT, TEST_TENANT_ID

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
                tenant_id=TEST_TENANT_ID,
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


async def test_exact_transaction_record_reuses_unique_identity_index_and_is_bounded(
    clean_db,
    db_engine,
    async_db_session: AsyncSession,
) -> None:
    transaction_id = "TX-EXACT-LOOKUP"
    portfolio_id = "PORT-EXACT-LOOKUP"
    with Session(db_engine) as session:
        session.add_all(
            [
                Portfolio(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id=portfolio_id,
                    base_currency="USD",
                    open_date=date(2024, 1, 1),
                    risk_exposure="BALANCED",
                    investment_time_horizon="LONG_TERM",
                    portfolio_type="ADVISORY",
                    booking_center_code="SG",
                    client_id="CLIENT-EXACT-LOOKUP",
                    status="ACTIVE",
                ),
                Instrument(
                    security_id="SEC-EXACT-LOOKUP",
                    name="Exact Lookup Instrument",
                    isin="ISIN-EXACT-LOOKUP",
                    currency="USD",
                    product_type="Equity",
                ),
                Transaction(
                    transaction_id=transaction_id,
                    portfolio_id=portfolio_id,
                    instrument_id="INST-EXACT-LOOKUP",
                    security_id="SEC-EXACT-LOOKUP",
                    transaction_type="BUY",
                    quantity=Decimal("10"),
                    price=Decimal("100"),
                    gross_transaction_amount=Decimal("1000"),
                    trade_currency="USD",
                    currency="USD",
                    transaction_date=datetime(2026, 1, 3, tzinfo=UTC),
                    costs=[
                        TransactionCost(
                            transaction_id=transaction_id,
                            fee_type="BROKERAGE",
                            amount=Decimal("2"),
                            currency="USD",
                        )
                    ],
                ),
            ]
        )
        session.add_all(
            [
                Transaction(
                    transaction_id=f"TX-EXACT-OTHER-{sequence:04d}",
                    portfolio_id=portfolio_id,
                    instrument_id="INST-EXACT-LOOKUP",
                    security_id="SEC-EXACT-LOOKUP",
                    transaction_type="BUY",
                    quantity=Decimal("1"),
                    price=Decimal("10"),
                    gross_transaction_amount=Decimal("10"),
                    trade_currency="USD",
                    currency="USD",
                    transaction_date=datetime(2026, 1, 4, tzinfo=UTC),
                )
                for sequence in range(300)
            ]
        )
        session.commit()
        session.execute(text("ANALYZE transactions"))
        migrated_indexes = set(
            session.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = current_schema() AND tablename = 'transactions'"
                )
            ).scalars()
        )
        session.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in session.execute(
                text(
                    "EXPLAIN (FORMAT TEXT) SELECT id FROM transactions "
                    "WHERE portfolio_id = :portfolio_id AND transaction_id = :transaction_id"
                ),
                {"portfolio_id": portfolio_id, "transaction_id": transaction_id},
            )
        )

    assert "ix_transactions_transaction_id" in migrated_indexes
    assert "ix_transactions_transaction_id" in plan
    assert "portfolio_id" in plan and "transaction_id" in plan

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
        response = await TransactionService(async_db_session).get_transaction_record(
            tenant_context=TEST_TENANT_CONTEXT,
            portfolio_id=portfolio_id,
            transaction_id=transaction_id,
            as_of_date=date(2026, 1, 31),
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", capture_sql)

    assert response.transaction.transaction_id == transaction_id
    assert response.portfolio_id == portfolio_id
    assert response.data_quality_status == "COMPLETE"
    data_reads = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith(("SELECT", "WITH"))
    ]
    assert len(data_reads) == 4
    assert "portfolios.tenant_id" in data_reads[0]
    assert any("transactions.transaction_id =" in statement for statement in data_reads)
    assert any("LIMIT" in statement for statement in data_reads)


async def test_transaction_ledger_identity_binds_only_selected_material_inputs(
    clean_db,
    db_engine,
    async_db_session: AsyncSession,
) -> None:
    with Session(db_engine) as session:
        session.add_all(
            [
                Portfolio(
                    tenant_id=TEST_TENANT_ID,
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
                    tenant_id=TEST_TENANT_ID,
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


async def test_transaction_ledger_page_and_identity_share_one_repeatable_snapshot(
    clean_db,
    db_engine,
    async_db_session: AsyncSession,
) -> None:
    with Session(db_engine) as session:
        session.add_all(
            [
                Portfolio(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id="PORT-SNAPSHOT",
                    base_currency="USD",
                    open_date=date(2024, 1, 1),
                    risk_exposure="BALANCED",
                    investment_time_horizon="LONG_TERM",
                    portfolio_type="ADVISORY",
                    booking_center_code="SG",
                    client_id="CLIENT-SNAPSHOT",
                    status="ACTIVE",
                ),
                Transaction(
                    transaction_id="TX-SNAPSHOT",
                    portfolio_id="PORT-SNAPSHOT",
                    instrument_id="INST-SNAPSHOT",
                    security_id="SEC-SNAPSHOT",
                    transaction_type="BUY",
                    quantity=Decimal("10"),
                    price=Decimal("100"),
                    gross_transaction_amount=Decimal("1000"),
                    trade_currency="USD",
                    currency="USD",
                    transaction_date=datetime(2026, 1, 3, tzinfo=UTC),
                ),
                FxRate(
                    from_currency="USD",
                    to_currency="SGD",
                    rate_date=date(2026, 1, 31),
                    rate=Decimal("1.35"),
                ),
            ]
        )
        session.commit()

    correction_committed = False
    sync_engine = async_db_session.bind.sync_engine

    def commit_correction_after_evidence(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany: bool,
    ) -> None:
        nonlocal correction_committed
        if correction_committed or "transaction_ledger_transaction_evidence" not in statement:
            return
        correction_committed = True
        with Session(db_engine) as correction_session:
            correction_session.execute(
                update(Transaction)
                .where(Transaction.transaction_id == "TX-SNAPSHOT")
                .values(
                    price=Decimal("200"),
                    gross_transaction_amount=Decimal("2000"),
                )
            )
            correction_session.execute(
                update(FxRate)
                .where(FxRate.from_currency == "USD", FxRate.to_currency == "SGD")
                .values(rate=Decimal("1.36"))
            )
            correction_session.commit()

    event.listen(sync_engine, "after_cursor_execute", commit_correction_after_evidence)
    try:
        snapshot_response = await TransactionService(async_db_session).get_transactions(
            tenant_context=TEST_TENANT_CONTEXT,
            portfolio_id="PORT-SNAPSHOT",
            skip=0,
            limit=10,
            as_of_date=date(2026, 1, 31),
            reporting_currency="SGD",
        )
    finally:
        event.remove(sync_engine, "after_cursor_execute", commit_correction_after_evidence)

    assert correction_committed is True
    assert snapshot_response.transactions[0].price == Decimal("100")
    assert snapshot_response.transactions[0].gross_transaction_amount == Decimal("1000")
    assert snapshot_response.transactions[0].gross_transaction_amount_reporting_currency == Decimal(
        "1350"
    )

    await async_db_session.rollback()
    corrected_response = await TransactionService(async_db_session).get_transactions(
        tenant_context=TEST_TENANT_CONTEXT,
        portfolio_id="PORT-SNAPSHOT",
        skip=0,
        limit=10,
        as_of_date=date(2026, 1, 31),
        reporting_currency="SGD",
    )

    assert corrected_response.transactions[0].price == Decimal("200")
    assert corrected_response.transactions[0].gross_transaction_amount == Decimal("2000")
    assert corrected_response.transactions[
        0
    ].gross_transaction_amount_reporting_currency == Decimal("2720")
    assert corrected_response.snapshot_id != snapshot_response.snapshot_id


async def test_transaction_ledger_evidence_is_session_invariant_and_matches_fx_selector(
    clean_db,
    db_engine,
    async_db_session: AsyncSession,
) -> None:
    with Session(db_engine) as session:
        session.add_all(
            [
                Portfolio(
                    tenant_id=TEST_TENANT_ID,
                    portfolio_id="PORT-FX-SELECTOR",
                    base_currency="USD",
                    open_date=date(2024, 1, 1),
                    risk_exposure="BALANCED",
                    investment_time_horizon="LONG_TERM",
                    portfolio_type="ADVISORY",
                    booking_center_code="SG",
                    client_id="CLIENT-FX-SELECTOR",
                    status="ACTIVE",
                ),
                Transaction(
                    transaction_id="TX-FX-SELECTOR",
                    portfolio_id="PORT-FX-SELECTOR",
                    instrument_id="INST-FX-SELECTOR",
                    security_id="SEC-FX-SELECTOR",
                    transaction_type="BUY",
                    quantity=Decimal("10"),
                    price=Decimal("100"),
                    gross_transaction_amount=Decimal("1000"),
                    trade_currency="USD",
                    currency="USD",
                    transaction_date=datetime(2026, 1, 3, tzinfo=UTC),
                    costs=[
                        TransactionCost(
                            transaction_id="TX-FX-SELECTOR",
                            fee_type="BROKERAGE",
                            amount=Decimal("2"),
                            currency="USD",
                        )
                    ],
                ),
                Cashflow(
                    transaction_id="TX-FX-SELECTOR",
                    portfolio_id="PORT-FX-SELECTOR",
                    security_id="SEC-FX-SELECTOR",
                    cashflow_date=date(2026, 1, 3),
                    epoch=1,
                    amount=Decimal("-1002"),
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
                    from_currency="usd",
                    to_currency="sgd",
                    rate_date=date(2026, 1, 31),
                    rate=Decimal("1.36"),
                ),
            ]
        )
        session.commit()

    repository = TransactionRepository(async_db_session)
    filters = TransactionLedgerFilters(
        portfolio_id="PORT-FX-SELECTOR",
        as_of_date=date(2026, 1, 31),
    )

    async def read_evidence():
        return await repository.get_transaction_ledger_input_evidence(
            filters=filters,
            reporting_currency="SGD",
            as_of_date=date(2026, 1, 31),
        )

    baseline = await read_evidence()
    await async_db_session.execute(text("SET LOCAL TIME ZONE 'America/New_York'"))
    await async_db_session.execute(text("SET LOCAL DateStyle TO 'SQL, DMY'"))
    alternate_session_format = await read_evidence()
    assert (
        alternate_session_format.transaction_digest,
        alternate_session_format.transaction_cost_digest,
        alternate_session_format.selected_cashflow_digest,
        alternate_session_format.selected_fx_rate_digest,
    ) == (
        baseline.transaction_digest,
        baseline.transaction_cost_digest,
        baseline.selected_cashflow_digest,
        baseline.selected_fx_rate_digest,
    )
    assert await repository.get_latest_fx_rate(
        from_currency="USD",
        to_currency="SGD",
        as_of_date=date(2026, 1, 31),
    ) == Decimal("1.36")

    await async_db_session.execute(
        update(FxRate)
        .where(FxRate.from_currency == "USD", FxRate.to_currency == "SGD")
        .values(rate=Decimal("1.37"))
    )
    await async_db_session.commit()
    unselected_change = await read_evidence()
    assert unselected_change.selected_fx_rate_digest == baseline.selected_fx_rate_digest
    assert await repository.get_latest_fx_rate(
        from_currency="USD",
        to_currency="SGD",
        as_of_date=date(2026, 1, 31),
    ) == Decimal("1.36")

    await async_db_session.execute(
        update(FxRate)
        .where(FxRate.from_currency == "usd", FxRate.to_currency == "sgd")
        .values(rate=Decimal("1.38"))
    )
    await async_db_session.commit()
    selected_change = await read_evidence()
    assert selected_change.selected_fx_rate_digest != baseline.selected_fx_rate_digest
    assert await repository.get_latest_fx_rate(
        from_currency="USD",
        to_currency="SGD",
        as_of_date=date(2026, 1, 31),
    ) == Decimal("1.38")
