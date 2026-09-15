from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from portfolio_common.database_models import Cashflow, Portfolio, Transaction, TransactionCost
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.operations.database_evidence.contract import load_hot_path_scenario_catalog
from scripts.operations.database_evidence.runtime_fragments import publish_requested_fragments
from scripts.operations.database_evidence.transaction_ledger import (
    measure_transaction_ledger_reads,
)
from tests.test_support.tenant import TEST_TENANT_ID

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db]

CATALOG_PATH = Path("contracts/operations/database-hot-path-scenarios.v1.json")
TARGET_PORTFOLIO = "PLAN-EVIDENCE-LEDGER"
NOISE_PORTFOLIO = "PLAN-EVIDENCE-NOISE"


async def _seed_transaction_ledger(session: AsyncSession, *, count: int) -> None:
    await session.execute(
        insert(Portfolio).values(
            [
                {
                    "portfolio_id": portfolio_id,
                    "tenant_id": TEST_TENANT_ID,
                    "base_currency": "USD",
                    "open_date": date(2024, 1, 1),
                    "risk_exposure": "BALANCED",
                    "investment_time_horizon": "LONG_TERM",
                    "portfolio_type": "ADVISORY",
                    "booking_center_code": "SG",
                    "client_id": f"CLIENT-{suffix}",
                    "status": "ACTIVE",
                }
                for portfolio_id, suffix in (
                    (TARGET_PORTFOLIO, "TARGET"),
                    (NOISE_PORTFOLIO, "NOISE"),
                )
            ]
        ),
    )
    batch_size = 1_000
    for start in range(0, count, batch_size):
        stop = min(start + batch_size, count)
        await session.execute(
            insert(Transaction).values(
                [
                    {
                        "transaction_id": f"PLAN-TX-{sequence:05d}",
                        "portfolio_id": (
                            TARGET_PORTFOLIO if sequence % 10 == 0 else NOISE_PORTFOLIO
                        ),
                        "instrument_id": f"PLAN-INST-{sequence % 500:04d}",
                        "security_id": f"PLAN-SEC-{sequence % 500:04d}",
                        "transaction_type": "BUY",
                        "quantity": "10",
                        "price": "100",
                        "gross_transaction_amount": "1000",
                        "trade_currency": "USD",
                        "currency": "USD",
                        "transaction_date": datetime(2026, 1, 1, tzinfo=UTC)
                        + timedelta(seconds=sequence),
                    }
                    for sequence in range(start, stop)
                ]
            ),
        )
        await session.execute(
            insert(TransactionCost).values(
                [
                    {
                        "transaction_id": f"PLAN-TX-{sequence:05d}",
                        "fee_type": "BROKERAGE",
                        "amount": "1",
                        "currency": "USD",
                    }
                    for sequence in range(start, stop)
                ]
            ),
        )
        await session.execute(
            insert(Cashflow).values(
                [
                    {
                        "transaction_id": f"PLAN-TX-{sequence:05d}",
                        "portfolio_id": (
                            TARGET_PORTFOLIO if sequence % 10 == 0 else NOISE_PORTFOLIO
                        ),
                        "security_id": f"PLAN-SEC-{sequence % 500:04d}",
                        "cashflow_date": date(2026, 1, 1),
                        "epoch": 1,
                        "amount": "-1001",
                        "currency": "USD",
                        "classification": "TRADE_SETTLEMENT",
                        "timing": "SETTLED",
                        "calculation_type": "TRANSACTION_DERIVED",
                        "is_position_flow": True,
                        "is_portfolio_flow": False,
                    }
                    for sequence in range(start, stop)
                ]
            ),
        )
    await session.commit()
    for table_name in ("transactions", "transaction_costs", "cashflows"):
        await session.execute(text(f"ANALYZE {table_name}"))


@pytest.mark.lifecycle
@pytest.mark.parametrize(
    ("count", "expected_refreshes", "expected_target_rows"),
    [
        (21, {TARGET_PORTFOLIO: 3, NOISE_PORTFOLIO: 3}, 3),
        (1001, {TARGET_PORTFOLIO: 5, NOISE_PORTFOLIO: 3}, 101),
    ],
    ids=["single-batch", "cross-batch"],
)
async def test_ledger_seed_refreshes_source_cut_once_per_portfolio_per_statement(
    clean_db,
    async_db_session: AsyncSession,
    count: int,
    expected_refreshes: dict[str, int],
    expected_target_rows: int,
) -> None:
    del clean_db
    # Observe actual refresh work on one owned connection, retaining the real
    # function and its transaction locks beneath this temporary counting wrapper.
    async with async_db_session.bind.connect() as connection:
        await connection.execute(
            text("CREATE TEMP TABLE ledger_source_cut_refresh_log (portfolio_id text)")
        )
        await connection.execute(
            text(
                "ALTER FUNCTION refresh_portfolio_cashflow_source_cut(text) "
                "RENAME TO ledger_source_cut_refresh_implementation"
            )
        )
        await connection.execute(
            text(
                """
                CREATE FUNCTION refresh_portfolio_cashflow_source_cut(target_portfolio_id text)
                RETURNS void LANGUAGE plpgsql AS $$
                BEGIN
                    INSERT INTO pg_temp.ledger_source_cut_refresh_log (portfolio_id)
                    VALUES (target_portfolio_id);
                    PERFORM ledger_source_cut_refresh_implementation(target_portfolio_id);
                END;
                $$
                """
            )
        )
        await connection.commit()
        try:
            async with AsyncSession(bind=connection, expire_on_commit=False) as seed_session:
                await _seed_transaction_ledger(seed_session, count=count)
                refreshes = dict(
                    (
                        await seed_session.execute(
                            text(
                                "SELECT portfolio_id, count(*) "
                                "FROM pg_temp.ledger_source_cut_refresh_log GROUP BY portfolio_id"
                            )
                        )
                    ).all()
                )
                assert refreshes == expected_refreshes
                assert await seed_session.scalar(text("SELECT count(*) FROM transactions")) == count
                assert await seed_session.scalar(text("SELECT count(*) FROM cashflows")) == count
                assert (
                    await seed_session.scalar(text("SELECT count(*) FROM transaction_costs"))
                    == count
                )
                assert (
                    await seed_session.scalar(
                        text(
                            "SELECT sum(amount) FROM cashflows WHERE portfolio_id = :portfolio_id"
                        ),
                        {"portfolio_id": TARGET_PORTFOLIO},
                    )
                    == -1001 * expected_target_rows
                )
                assert (
                    await seed_session.scalar(
                        text(
                            "SELECT cashflow_revision_count FROM portfolio_cashflow_source_cuts "
                            "WHERE portfolio_id = :portfolio_id"
                        ),
                        {"portfolio_id": TARGET_PORTFOLIO},
                    )
                    == expected_target_rows
                )
        finally:
            await connection.rollback()
            await connection.execute(
                text("DROP FUNCTION refresh_portfolio_cashflow_source_cut(text)")
            )
            await connection.execute(
                text(
                    "ALTER FUNCTION ledger_source_cut_refresh_implementation(text) "
                    "RENAME TO refresh_portfolio_cashflow_source_cut"
                )
            )
            await connection.commit()


async def test_transaction_ledger_page_and_count_are_bounded_and_index_backed(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    del clean_db
    catalog = load_hot_path_scenario_catalog(CATALOG_PATH)
    scenarios = catalog.by_id()
    await _seed_transaction_ledger(
        async_db_session,
        count=scenarios["transaction_ledger_page"].seed_cardinality,
    )

    count_result, page_result = await measure_transaction_ledger_reads(
        async_db_session,
        portfolio_id=TARGET_PORTFOLIO,
        count_scenario=scenarios["transaction_ledger_count"],
        page_scenario=scenarios["transaction_ledger_page"],
    )
    publish_requested_fragments((count_result, page_result))

    seeded_transactions = await async_db_session.scalar(text("SELECT count(*) FROM transactions"))
    assert seeded_transactions == scenarios["transaction_ledger_page"].seed_cardinality
