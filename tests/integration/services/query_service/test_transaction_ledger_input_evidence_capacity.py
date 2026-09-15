from datetime import UTC, date, datetime
from time import perf_counter

import pytest
from portfolio_common.database_models import Cashflow, Portfolio, Transaction, TransactionCost
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.application.transaction_query import TransactionLedgerFilters
from src.services.query_service.app.repositories.transaction_repository import TransactionRepository
from tests.test_support.tenant import TEST_TENANT_ID

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.performance]

TRANSACTION_COUNT = 100_000
BATCH_SIZE = 5_000
PHYSICAL_BATCH_SIZE = 1_000


async def _insert_bank_day_batch(
    session: AsyncSession,
    model: type[Transaction | TransactionCost | Cashflow],
    rows: list[dict[str, object]],
) -> None:
    # Asyncpg executemany executes one physical statement per row. Explicit
    # multi-VALUES preserves statement-trigger batching; 1,000 rows also keeps
    # each seed family's bound parameters below the driver's 32,767 limit.
    for start in range(0, len(rows), PHYSICAL_BATCH_SIZE):
        await session.execute(insert(model).values(rows[start : start + PHYSICAL_BATCH_SIZE]))


async def _seed_bank_day_ledger(async_db_session: AsyncSession, *, count: int) -> None:
    await async_db_session.execute(
        insert(Portfolio),
        [
            {
                "portfolio_id": "PORT-LEDGER-CAPACITY",
                "tenant_id": TEST_TENANT_ID,
                "base_currency": "USD",
                "open_date": date(2024, 1, 1),
                "risk_exposure": "BALANCED",
                "investment_time_horizon": "LONG_TERM",
                "portfolio_type": "ADVISORY",
                "booking_center_code": "SG",
                "client_id": "CLIENT-LEDGER-CAPACITY",
                "status": "ACTIVE",
            }
        ],
    )
    for start in range(0, count, BATCH_SIZE):
        stop = min(start + BATCH_SIZE, count)
        transaction_ids = [f"TX-CAPACITY-{sequence:06d}" for sequence in range(start, stop)]
        await _insert_bank_day_batch(
            async_db_session,
            Transaction,
            [
                {
                    "transaction_id": transaction_id,
                    "portfolio_id": "PORT-LEDGER-CAPACITY",
                    "instrument_id": f"INST-{sequence % 500:04d}",
                    "security_id": f"SEC-{sequence % 500:04d}",
                    "transaction_type": "BUY",
                    "quantity": "10",
                    "price": "100",
                    "gross_transaction_amount": "1000",
                    "trade_currency": "USD",
                    "currency": "USD",
                    "transaction_date": datetime(2026, 1, 2, tzinfo=UTC),
                }
                for sequence, transaction_id in zip(
                    range(start, stop),
                    transaction_ids,
                    strict=True,
                )
            ],
        )
        await _insert_bank_day_batch(
            async_db_session,
            TransactionCost,
            [
                {
                    "transaction_id": transaction_id,
                    "fee_type": "BROKERAGE",
                    "amount": "1",
                    "currency": "USD",
                }
                for transaction_id in transaction_ids
            ],
        )
        await _insert_bank_day_batch(
            async_db_session,
            Cashflow,
            [
                {
                    "transaction_id": transaction_id,
                    "portfolio_id": "PORT-LEDGER-CAPACITY",
                    "security_id": f"SEC-{sequence % 500:04d}",
                    "cashflow_date": date(2026, 1, 2),
                    "epoch": 1,
                    "amount": "-1001",
                    "currency": "USD",
                    "classification": "TRADE_SETTLEMENT",
                    "timing": "SETTLED",
                    "calculation_type": "TRANSACTION_DERIVED",
                    "is_position_flow": True,
                    "is_portfolio_flow": False,
                }
                for sequence, transaction_id in zip(
                    range(start, stop),
                    transaction_ids,
                    strict=True,
                )
            ],
        )
        await async_db_session.commit()


@pytest.mark.lifecycle
@pytest.mark.parametrize("count,expected_refreshes", [(21, 3), (1001, 5)])
async def test_bank_day_seed_refreshes_source_cut_per_physical_statement(
    clean_db,
    async_db_session: AsyncSession,
    count: int,
    expected_refreshes: int,
) -> None:
    # Retain the real refresh implementation and its transaction locks. Count
    # durable database work, not Python execute calls or trigger metadata.
    async with async_db_session.bind.connect() as connection:
        # Deliberately warm both source triggers on this same backend. Rolling
        # back the fixture facts does not discard their cached function plans.
        warmup = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as warmup_session:
                await _seed_bank_day_ledger(warmup_session, count=1)
        finally:
            await warmup.rollback()
        await connection.execute(
            text("CREATE TEMP TABLE bank_day_source_cut_refresh_log (portfolio_id text)")
        )
        await connection.execute(
            text(
                "ALTER FUNCTION refresh_portfolio_cashflow_source_cut(text) "
                "RENAME TO bank_day_source_cut_refresh_implementation"
            )
        )
        await connection.execute(
            text(
                """
                CREATE FUNCTION refresh_portfolio_cashflow_source_cut(target_portfolio_id text)
                RETURNS void LANGUAGE plpgsql AS $$
                BEGIN
                    INSERT INTO pg_temp.bank_day_source_cut_refresh_log (portfolio_id)
                    VALUES (target_portfolio_id);
                    PERFORM bank_day_source_cut_refresh_implementation(target_portfolio_id);
                END;
                $$
                """
            )
        )
        # Cached trigger expressions can retain the renamed implementation OID.
        # Resolve the logging wrapper before measuring this backend's work.
        await connection.execute(text("DISCARD PLANS"))
        await connection.commit()
        try:
            async with AsyncSession(bind=connection, expire_on_commit=False) as seed_session:
                await _seed_bank_day_ledger(seed_session, count=count)
                actual_refreshes = dict(
                    (
                        await seed_session.execute(
                            text(
                                "SELECT portfolio_id, count(*) FROM "
                                "pg_temp.bank_day_source_cut_refresh_log GROUP BY portfolio_id"
                            )
                        )
                    ).all()
                )
                assert actual_refreshes == {"PORT-LEDGER-CAPACITY": expected_refreshes}
                for table in ("transactions", "transaction_costs", "cashflows"):
                    assert await seed_session.scalar(text(f"SELECT count(*) FROM {table}")) == count
                assert await seed_session.scalar(text("SELECT sum(amount) FROM cashflows")) == (
                    -1001 * count
                )
                assert (
                    await seed_session.scalar(
                        text("SELECT cashflow_revision_count FROM portfolio_cashflow_source_cuts")
                    )
                    == count
                )
        finally:
            await connection.rollback()
            await connection.execute(
                text("DROP FUNCTION refresh_portfolio_cashflow_source_cut(text)")
            )
            await connection.execute(
                text(
                    "ALTER FUNCTION bank_day_source_cut_refresh_implementation(text) "
                    "RENAME TO refresh_portfolio_cashflow_source_cut"
                )
            )
            await connection.commit()


async def test_transaction_ledger_input_evidence_is_bounded_at_bank_day_volume(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_bank_day_ledger(async_db_session, count=TRANSACTION_COUNT)
    started_at = perf_counter()
    evidence = await TransactionRepository(async_db_session).get_transaction_ledger_input_evidence(
        filters=TransactionLedgerFilters(
            portfolio_id="PORT-LEDGER-CAPACITY",
            as_of_date=date(2026, 1, 31),
        ),
        reporting_currency="USD",
        as_of_date=date(2026, 1, 31),
    )
    elapsed_seconds = perf_counter() - started_at

    assert evidence.transaction_count == TRANSACTION_COUNT
    assert len(evidence.transaction_digest or "") == 64
    assert len(evidence.transaction_cost_digest or "") == 64
    assert len(evidence.selected_cashflow_digest or "") == 64
    assert evidence.selected_fx_rate_digest is None
    print(
        "ledger_input_evidence_capacity "
        f"rows={TRANSACTION_COUNT} costs={TRANSACTION_COUNT} cashflows={TRANSACTION_COUNT} "
        f"elapsed_seconds={elapsed_seconds:.3f}"
    )


@pytest.mark.lifecycle
async def test_source_cut_refresh_statement_has_bounded_actual_tuple_work(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """Execute the installed refresh SQL, not a hand-copied query-shape proxy."""
    count = 1001
    portfolio_id = "PORT-LEDGER-CAPACITY"
    await _seed_bank_day_ledger(async_db_session, count=count)
    refresh_sql = text("SELECT refresh_portfolio_cashflow_source_cut(:portfolio_id)")
    # Settle source timestamp chronology before comparing unchanged refreshes.
    await async_db_session.execute(refresh_sql, {"portfolio_id": portfolio_id})
    snapshot_sql = text(
        "SELECT portfolio_base_currency, cashflow_revision_count, cashflow_revision_digest, "
        "settlement_revision_count, settlement_revision_digest, materialized_at "
        "FROM portfolio_cashflow_source_cuts WHERE portfolio_id = :portfolio_id"
    )
    before = (await async_db_session.execute(snapshot_sql, {"portfolio_id": portfolio_id})).one()
    installed_sql = await async_db_session.scalar(
        text(
            "SELECT pg_get_functiondef('refresh_portfolio_cashflow_source_cut(text)'::regprocedure)"
        )
    )
    assert isinstance(installed_sql, str)
    statement_sql = installed_sql[installed_sql.index("WITH portfolio_facts AS (") :].rsplit(
        "END;", 1
    )[0]
    assert statement_sql.count("INSERT INTO portfolio_cashflow_source_cuts (") == 1
    assert "target_portfolio_id" in statement_sql
    statement_sql = statement_sql.replace("target_portfolio_id", ":portfolio_id")
    # Preserve the real function's durable parent-row lock around its write.
    await async_db_session.execute(
        text(
            "SELECT 1 FROM portfolios WHERE portfolio_id = :portfolio_id "
            "AND tenant_id = :tenant_id FOR NO KEY UPDATE"
        ),
        {"portfolio_id": portfolio_id, "tenant_id": TEST_TENANT_ID},
    )
    actual_plan = await async_db_session.scalar(
        text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement_sql),
        {"portfolio_id": portfolio_id},
    )
    after = (await async_db_session.execute(snapshot_sql, {"portfolio_id": portfolio_id})).one()
    assert before == after
    assert after.portfolio_base_currency == "USD"
    assert after.cashflow_revision_count == count
    assert after.settlement_revision_count == 0
    assert await async_db_session.scalar(text("SELECT sum(amount) FROM cashflows")) == -1001 * count
    assert isinstance(actual_plan, list)
    pending_nodes = [actual_plan[0]["Plan"]]
    tuple_work = 0
    while pending_nodes:
        node = pending_nodes.pop()
        tuple_work += (
            node["Actual Rows"]
            + node.get("Rows Removed by Filter", 0)
            + node.get("Rows Removed by Join Filter", 0)
        ) * node["Actual Loops"]
        pending_nodes.extend(node.get("Plans", []))
    print(f"source_cut_actual_tuple_work rows={count} tuple_work={tuple_work}")
    assert tuple_work <= 10 * count + 100
