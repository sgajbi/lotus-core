from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    FinancialReconciliationRun,
    FxRate,
    Instrument,
    Portfolio,
)
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.financial_reconciliation_service.app.ports import (
    reconciliation_repository_ports,
)
from src.services.financial_reconciliation_service.app.repositories import (
    reconciliation_repository as reconciliation_repo,
)
from tests.test_support.tenant import TEST_TENANT_ID

pytestmark = pytest.mark.asyncio


async def test_latest_fx_rates_resolve_all_point_in_time_keys_in_one_statement(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add_all(
        [
            FxRate(
                from_currency="EUR",
                to_currency="USD",
                rate_date=date(2026, 4, 1),
                rate=Decimal("1.10"),
            ),
            FxRate(
                from_currency="EUR",
                to_currency="USD",
                rate_date=date(2026, 4, 5),
                rate=Decimal("1.20"),
            ),
            FxRate(
                from_currency="GBP",
                to_currency="USD",
                rate_date=date(2026, 4, 2),
                rate=Decimal("1.30"),
            ),
        ]
    )
    await async_db_session.commit()
    keys = [
        reconciliation_repository_ports.FxRateLookupKey("EUR", "USD", date(2026, 4, 3)),
        reconciliation_repository_ports.FxRateLookupKey("EUR", "USD", date(2026, 4, 5)),
        reconciliation_repository_ports.FxRateLookupKey("GBP", "USD", date(2026, 4, 1)),
    ]
    statements: list[str] = []
    bind = async_db_session.bind
    assert bind is not None

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        if "fx_lookup" in statement.lower():
            statements.append(statement)

    sqlalchemy_event.listen(bind.sync_engine, "before_cursor_execute", capture_statement)
    try:
        rates = await reconciliation_repo.ReconciliationRepository(
            async_db_session, tenant_id=TEST_TENANT_ID
        ).fetch_latest_fx_rates(keys=list(reversed(keys)) + [keys[0]])
    finally:
        sqlalchemy_event.remove(bind.sync_engine, "before_cursor_execute", capture_statement)

    assert rates == {
        keys[0]: Decimal("1.1000000000"),
        keys[1]: Decimal("1.2000000000"),
        keys[2]: None,
    }
    assert len(statements) == 1


async def test_position_valuation_rows_select_latest_security_state_through_target_epoch(
    clean_db, async_db_session: AsyncSession
):
    portfolio_id = "P-MIXED-EPOCH"
    business_date = date(2026, 4, 10)
    async_db_session.add(
        Portfolio(
            tenant_id=TEST_TENANT_ID,
            legal_book_id="BOOK-TEST",
            portfolio_id=portfolio_id,
            base_currency="USD",
            open_date=date(2020, 1, 1),
            risk_exposure="MEDIUM",
            investment_time_horizon="LONG",
            portfolio_type="DISCRETIONARY",
            booking_center_code="SG",
            client_id="CLIENT-MIXED-EPOCH",
            status="ACTIVE",
        )
    )
    async_db_session.add_all(
        [
            Instrument(
                security_id=security_id,
                name=security_id,
                isin=f"ISIN-{security_id}",
                currency="USD",
                product_type="EQUITY",
            )
            for security_id in ("SEC-A", "SEC-B", "SEC-C")
        ]
    )
    await async_db_session.flush()

    def snapshot(security_id: str, epoch: int, market_price: str) -> DailyPositionSnapshot:
        price = Decimal(market_price)
        return DailyPositionSnapshot(
            portfolio_id=portfolio_id,
            security_id=security_id,
            date=business_date,
            epoch=epoch,
            quantity=Decimal("10"),
            cost_basis=Decimal("90"),
            cost_basis_local=Decimal("90"),
            market_price=price,
            market_value=price * Decimal("10"),
            market_value_local=price * Decimal("10"),
            unrealized_gain_loss=(price * Decimal("10")) - Decimal("90"),
            unrealized_gain_loss_local=(price * Decimal("10")) - Decimal("90"),
            valuation_status="VALUED",
        )

    async_db_session.add_all(
        [
            snapshot("SEC-A", 0, "10"),
            snapshot("SEC-A", 2, "12"),
            snapshot("SEC-A", 4, "14"),
            snapshot("SEC-B", 1, "11"),
            snapshot("SEC-C", 3, "13"),
        ]
    )
    await async_db_session.commit()

    rows = await reconciliation_repo.ReconciliationRepository(
        async_db_session, tenant_id=TEST_TENANT_ID
    ).fetch_position_valuation_rows(
        portfolio_id=portfolio_id,
        business_date=business_date,
        epoch=3,
    )

    assert [(row[0].security_id, row[0].epoch) for row in rows] == [
        ("SEC-A", 2),
        ("SEC-B", 1),
        ("SEC-C", 3),
    ]
    assert [row[3] for row in rows] == [None, None, None]


async def test_create_run_deduplicates_concurrent_requests(
    clean_db, async_db_session: AsyncSession
):
    async_db_session.add(
        Portfolio(
            tenant_id=TEST_TENANT_ID,
            legal_book_id="BOOK-TEST",
            portfolio_id="P-CONC",
            base_currency="USD",
            open_date=date(2020, 1, 1),
            risk_exposure="MEDIUM",
            investment_time_horizon="LONG",
            portfolio_type="DISCRETIONARY",
            booking_center_code="SG",
            client_id="CLIENT-P-CONC",
            status="ACTIVE",
        )
    )
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    dedupe_key = "auto:transaction_cashflow:P-CONC:2026-03-14:7"
    barrier_lock = asyncio.Lock()
    barrier_ready = asyncio.Event()
    barrier_count = 0

    async def create_one() -> tuple[str, bool]:
        nonlocal barrier_count
        async with session_factory() as session:
            repo = reconciliation_repo.ReconciliationRepository(session, tenant_id=TEST_TENANT_ID)
            original_get = repo.get_run_by_dedupe_key

            async def synchronized_get_run_by_dedupe_key(key: str):
                nonlocal barrier_count
                result = await original_get(key)
                async with barrier_lock:
                    barrier_count += 1
                    if barrier_count == 2:
                        barrier_ready.set()
                await barrier_ready.wait()
                return result

            repo.get_run_by_dedupe_key = synchronized_get_run_by_dedupe_key  # type: ignore[method-assign]
            run, created = await repo.create_run(
                reconciliation_type="transaction_cashflow",
                portfolio_id="P-CONC",
                business_date=date(2026, 3, 14),
                epoch=7,
                aggregation_revision=11,
                requested_by="system_pipeline",
                dedupe_key=dedupe_key,
                correlation_id="corr-conc",
                tolerance=Decimal("0.01"),
            )
            await session.commit()
            return run.run_id, created

    first, second = await asyncio.gather(create_one(), create_one())

    created_flags = sorted([first[1], second[1]])
    assert created_flags == [False, True]
    assert first[0] == second[0]

    async with session_factory() as verification_session:
        rows = (
            (
                await verification_session.execute(
                    select(FinancialReconciliationRun).where(
                        FinancialReconciliationRun.dedupe_key == dedupe_key
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    assert rows[0].run_id == first[0]
    assert rows[0].aggregation_revision == 11
