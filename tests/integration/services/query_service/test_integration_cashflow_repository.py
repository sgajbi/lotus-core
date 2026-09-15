# tests/integration/services/query_service/test_cashflow_repository.py
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from portfolio_common.database_models import (
    Cashflow,
    Portfolio,
    PositionState,
    Transaction,
)
from portfolio_common.domain.tenant import TenantContext, TenantId
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.services.query_service.app.application.transaction_query import (
    TransactionLedgerFilters,
    transaction_ledger_query_spec,
)
from src.services.query_service.app.repositories.cashflow_repository import CashflowRepository
from src.services.query_service.app.repositories.transaction_repository import TransactionRepository
from src.services.query_service.app.services.cash_movement_service import CashMovementService
from src.services.query_service.app.services.cashflow_projection_service import (
    CashflowProjectionService,
)
from tests.test_support.tenant import TEST_TENANT_ID

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
def setup_cashflow_data(db_engine, clean_db):
    """
    Seeds the database with a mix of internal and external cashflows for testing.
    """
    portfolio_id = "MWR_TEST_PORT_01"
    security_id_income = "INCOME_SEC_01"
    with Session(db_engine) as session:
        # Prerequisites
        session.add(
            Portfolio(
                tenant_id=TEST_TENANT_ID,
                portfolio_id=portfolio_id,
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            )
        )
        session.add(
            Transaction(
                transaction_id="T1",
                portfolio_id=portfolio_id,
                instrument_id="I1",
                security_id="S1",
                transaction_date=date(2025, 1, 15),
                transaction_type="DEPOSIT",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            )
        )
        session.add(
            Transaction(
                transaction_id="T2",
                portfolio_id=portfolio_id,
                instrument_id="I2",
                security_id="S2",
                transaction_date=date(2025, 1, 20),
                transaction_type="BUY",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            )
        )
        session.add(
            Transaction(
                transaction_id="T3",
                portfolio_id=portfolio_id,
                instrument_id="I3",
                security_id="S3",
                transaction_date=date(2025, 1, 25),
                transaction_type="WITHDRAWAL",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            )
        )
        session.add(
            Transaction(
                transaction_id="T4",
                portfolio_id=portfolio_id,
                instrument_id="I4",
                security_id=security_id_income,
                transaction_date=date(2025, 1, 1),
                transaction_type="DIVIDEND",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            )
        )
        session.add(
            Transaction(
                transaction_id="T5",
                portfolio_id=portfolio_id,
                instrument_id="I5",
                security_id=security_id_income,
                transaction_date=date(2025, 1, 1),
                transaction_type="INTEREST",
                quantity=1,
                price=1,
                gross_transaction_amount=1,
                trade_currency="USD",
                currency="USD",
            )
        )

        # Add PositionState records for epoch-aware filtering
        session.add(
            PositionState(
                portfolio_id=portfolio_id,
                security_id=security_id_income,
                epoch=1,
                watermark_date=date(2025, 1, 1),
            )
        )

        session.flush()

        # Cashflows to test against
        session.add_all(
            [
                # External, should be included
                Cashflow(
                    transaction_id="T1",
                    portfolio_id=portfolio_id,
                    cashflow_date=date(2025, 1, 15),
                    amount=Decimal("10000"),
                    currency="USD",
                    classification="CASHFLOW_IN",
                    timing="BOD",
                    calculation_type="NET",
                    is_portfolio_flow=True,
                ),
                # Internal, should be excluded
                Cashflow(
                    transaction_id="T2",
                    portfolio_id=portfolio_id,
                    security_id="S2",
                    cashflow_date=date(2025, 1, 20),
                    amount=Decimal("-5000"),
                    currency="USD",
                    classification="INVESTMENT_OUTFLOW",
                    timing="BOD",
                    calculation_type="NET",
                    is_portfolio_flow=False,
                ),
                # External, should be included
                Cashflow(
                    transaction_id="T3",
                    portfolio_id=portfolio_id,
                    cashflow_date=date(2025, 1, 25),
                    amount=Decimal("-2000"),
                    currency="USD",
                    classification="CASHFLOW_OUT",
                    timing="EOD",
                    calculation_type="NET",
                    is_portfolio_flow=True,
                ),
                # Income in correct epoch
                Cashflow(
                    transaction_id="T4",
                    portfolio_id=portfolio_id,
                    security_id=security_id_income,
                    cashflow_date=date(2025, 2, 1),
                    amount=Decimal("100"),
                    currency="USD",
                    classification="INCOME",
                    timing="EOD",
                    calculation_type="NET",
                    is_position_flow=True,
                    epoch=1,
                ),
                # Income in incorrect epoch (should be filtered out)
                Cashflow(
                    transaction_id="T5",
                    portfolio_id=portfolio_id,
                    security_id=security_id_income,
                    cashflow_date=date(2025, 2, 2),
                    amount=Decimal("999"),
                    currency="USD",
                    classification="INCOME",
                    timing="EOD",
                    calculation_type="NET",
                    is_position_flow=True,
                    epoch=0,
                ),
            ]
        )
        session.commit()


async def test_get_external_flows(setup_cashflow_data, async_db_session: AsyncSession):
    """
    GIVEN a mix of internal and external cashflows in the database
    WHEN get_external_flows is called
    THEN it should return only the two external flows (CASHFLOW_IN and CASHFLOW_OUT).
    """
    # ARRANGE
    repo = CashflowRepository(async_db_session)
    portfolio_id = "MWR_TEST_PORT_01"
    start_date = date(2025, 1, 1)
    end_date = date(2025, 1, 31)

    # ACT
    results = await repo.get_external_flows(portfolio_id, start_date, end_date)

    # ASSERT
    assert len(results) == 2

    # Results are tuples of (date, amount)
    assert results[0][0] == date(2025, 1, 15)
    assert results[0][1] == Decimal("10000")

    assert results[1][0] == date(2025, 1, 25)
    assert results[1][1] == Decimal("-2000")


async def test_get_external_flows_uses_latest_cashflow_epoch(clean_db, async_db_session):
    """
    GIVEN a replayed external cashflow persisted in multiple epochs
    WHEN get_external_flows is called
    THEN it should return only the latest cashflow version for the transaction.
    """
    portfolio_id = "MWR_EPOCH_FILTER_PORT_01"
    transaction_id = "EXT_FLOW_TXN_01"

    async_db_session.add(
        Portfolio(
            tenant_id=TEST_TENANT_ID,
            portfolio_id=portfolio_id,
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="f",
        )
    )
    async_db_session.add(
        Transaction(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            instrument_id="I-EXT-1",
            security_id="CASH_USD",
            transaction_date=date(2025, 1, 15),
            transaction_type="DEPOSIT",
            quantity=1,
            price=1,
            gross_transaction_amount=100,
            trade_currency="USD",
            currency="USD",
        )
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            Cashflow(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id="CASH_USD",
                cashflow_date=date(2025, 1, 15),
                amount=Decimal("100"),
                currency="USD",
                classification="CASHFLOW_IN",
                timing="BOD",
                calculation_type="NET",
                is_portfolio_flow=True,
                epoch=0,
            ),
            Cashflow(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id="CASH_USD",
                cashflow_date=date(2025, 1, 15),
                amount=Decimal("100"),
                currency="USD",
                classification="CASHFLOW_IN",
                timing="BOD",
                calculation_type="NET",
                is_portfolio_flow=True,
                epoch=2,
            ),
        ]
    )
    await async_db_session.commit()

    repo = CashflowRepository(async_db_session)
    results = await repo.get_external_flows(portfolio_id, date(2025, 1, 1), date(2025, 1, 31))

    assert results == [(date(2025, 1, 15), Decimal("100"))]


async def test_get_portfolio_cashflow_series_uses_latest_cashflow_epoch(
    clean_db, async_db_session: AsyncSession
):
    """
    GIVEN replayed portfolio-flow cashflows for the same transaction
    WHEN get_portfolio_cashflow_series is called
    THEN the daily total should reflect only the latest transaction epoch.
    """
    portfolio_id = "PORT_CF_SERIES_EPOCH_01"
    transaction_id = "PORT_CF_SERIES_TXN_01"

    async_db_session.add(
        Portfolio(
            tenant_id=TEST_TENANT_ID,
            portfolio_id=portfolio_id,
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="f",
        )
    )
    async_db_session.add(
        Transaction(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            instrument_id="I-SER-1",
            security_id="CASH_USD",
            transaction_date=date(2025, 2, 1),
            transaction_type="WITHDRAWAL",
            quantity=1,
            price=1,
            gross_transaction_amount=50,
            trade_currency="USD",
            currency="USD",
        )
    )
    await async_db_session.flush()
    async_db_session.add_all(
        [
            Cashflow(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id="CASH_USD",
                cashflow_date=date(2025, 2, 1),
                amount=Decimal("-50"),
                currency="USD",
                classification="CASHFLOW_OUT",
                timing="EOD",
                calculation_type="NET",
                is_portfolio_flow=True,
                epoch=0,
            ),
            Cashflow(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id="CASH_USD",
                cashflow_date=date(2025, 2, 1),
                amount=Decimal("-50"),
                currency="USD",
                classification="CASHFLOW_OUT",
                timing="EOD",
                calculation_type="NET",
                is_portfolio_flow=True,
                epoch=4,
            ),
        ]
    )
    await async_db_session.commit()

    repo = CashflowRepository(async_db_session)
    evidence = await repo.get_portfolio_cashflow_series_with_evidence(
        portfolio_id,
        date(2025, 2, 1),
        date(2025, 2, 1),
        tenant_id=TenantId(TEST_TENANT_ID),
    )

    assert evidence.rows == [(date(2025, 2, 1), Decimal("-50"))]
    assert evidence.latest_evidence_timestamp is not None
    assert evidence.source_row_count == 1
    assert evidence.source_total == Decimal("-50")


async def test_cash_movement_summary_returns_exact_source_controls(
    setup_cashflow_data, async_db_session: AsyncSession
) -> None:
    repo = CashflowRepository(async_db_session)

    evidence = await repo.get_portfolio_cash_movement_summary(
        portfolio_id="MWR_TEST_PORT_01",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        tenant_id=TenantId(TEST_TENANT_ID),
    )

    assert evidence.source_row_count == 3
    assert evidence.source_currency_totals == {"USD": Decimal("3000")}
    assert sum(row[5] for row in evidence.rows) == evidence.source_row_count
    assert (
        sum((row[6] for row in evidence.rows), start=Decimal("0"))
        == (evidence.source_currency_totals["USD"])
    )


@pytest.mark.lifecycle
@pytest.mark.parametrize(
    "window_date,inclusive_start,exclusive_end,dst_offsets",
    [
        pytest.param(
            date(2026, 3, 1),
            datetime(2026, 3, 1, tzinfo=UTC),
            datetime(2026, 3, 2, tzinfo=UTC),
            None,
            id="month-rollover",
        ),
        pytest.param(
            date(2024, 2, 29),
            datetime(2024, 2, 29, tzinfo=UTC),
            datetime(2024, 3, 1, tzinfo=UTC),
            None,
            id="leap-day",
        ),
        pytest.param(
            date(2025, 12, 31),
            datetime(2025, 12, 31, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
            None,
            id="year-rollover",
        ),
        pytest.param(
            date(2026, 3, 8),
            datetime(2026, 3, 8, tzinfo=UTC),
            datetime(2026, 3, 9, tzinfo=UTC),
            (-18000, -14400),
            id="dst-spring",
        ),
        pytest.param(
            date(2026, 11, 1),
            datetime(2026, 11, 1, tzinfo=UTC),
            datetime(2026, 11, 2, tzinfo=UTC),
            (-14400, -18000),
            id="dst-fall",
        ),
    ],
)
async def test_projected_settlement_window_and_utc_bucket_ignore_session_timezone(
    clean_db,
    async_db_session: AsyncSession,
    window_date: date,
    inclusive_start: datetime,
    exclusive_end: datetime,
    dst_offsets: tuple[int, int] | None,
) -> None:
    """PostgreSQL proof of UTC event-date membership and bucket semantics."""
    portfolio_id = "UTC-WINDOW-PORTFOLIO"
    async_db_session.add(
        Portfolio(
            tenant_id=TEST_TENANT_ID,
            portfolio_id=portfolio_id,
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="SG",
            client_id="utc-window-client",
            status="active",
        )
    )
    boundary_rows = (
        ("UTC-WINDOW-BEFORE", inclusive_start - timedelta(seconds=1), "10"),
        ("UTC-WINDOW-IN", inclusive_start, "20"),
        ("UTC-WINDOW-EXCLUSIVE", exclusive_end, "30"),
    )
    for transaction_id, settlement_date, amount in boundary_rows:
        async_db_session.add(
            Transaction(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                instrument_id=transaction_id,
                security_id=transaction_id,
                transaction_type="DEPOSIT",
                quantity=1,
                price=1,
                gross_transaction_amount=Decimal(amount),
                trade_currency="USD",
                currency="USD",
                transaction_date=inclusive_start - timedelta(days=1),
                settlement_date=settlement_date,
            )
        )
    # Independent trade-instant controls settle after the reporting window.
    # They must not become settlement cashflows in this window merely because
    # their trade instant belongs to it.
    for suffix, transaction_date, amount in boundary_rows:
        async_db_session.add(
            Transaction(
                transaction_id=f"TRADE-{suffix}",
                portfolio_id=portfolio_id,
                instrument_id="UTC-TRADE-EDGE",
                security_id="UTC-TRADE-EDGE",
                transaction_type="DEPOSIT",
                quantity=1,
                price=1,
                gross_transaction_amount=Decimal(amount),
                trade_currency="USD",
                currency="USD",
                transaction_date=transaction_date,
                settlement_date=exclusive_end + timedelta(days=1),
            )
        )
    await async_db_session.commit()

    repository = CashflowRepository(async_db_session)
    transaction_repository = TransactionRepository(async_db_session)
    assert await transaction_repository.portfolio_exists(
        portfolio_id, tenant_id=TenantId(TEST_TENANT_ID)
    )
    for session_timezone in ("UTC", "Asia/Singapore", "America/New_York"):
        await async_db_session.execute(
            sa.text("SELECT set_config('TimeZone', :session_timezone, true)"),
            {"session_timezone": session_timezone},
        )
        if session_timezone == "America/New_York" and dst_offsets is not None:
            # Verify that PostgreSQL's actual timezone data exercises a DST
            # transition, not just a scenario label. These are session-chaos
            # offsets, never authority for a booking-centre business date.
            actual_offsets = (
                await async_db_session.execute(
                    sa.text(
                        "SELECT EXTRACT(TIMEZONE FROM CAST(:start AS timestamptz)), "
                        "EXTRACT(TIMEZONE FROM CAST(:end AS timestamptz))"
                    ),
                    {"start": inclusive_start, "end": exclusive_end},
                )
            ).one()
            assert tuple(actual_offsets) == dst_offsets
        evidence = await repository.get_projected_settlement_cashflow_series_with_evidence(
            portfolio_id=portfolio_id,
            start_date=window_date,
            end_date=window_date,
            tenant_id=TenantId(TEST_TENANT_ID),
        )
        assert evidence.rows == [(window_date, Decimal("20"))]
        assert evidence.source_row_count == 1
        assert evidence.source_total == Decimal("20")
        for date_filters, expected_suffixes in (
            ({"start_date": window_date}, ("IN", "EXCLUSIVE")),
            ({"end_date": window_date}, ("BEFORE", "IN")),
            ({"as_of_date": window_date}, ("BEFORE", "IN")),
            (
                {"start_date": window_date, "end_date": window_date},
                ("IN",),
            ),
            (
                {"start_date": window_date, "as_of_date": window_date},
                ("IN",),
            ),
        ):
            filters = TransactionLedgerFilters(
                portfolio_id=portfolio_id,
                instrument_id="UTC-TRADE-EDGE",
                **date_filters,
            )
            rows = await transaction_repository.get_transactions(
                query_spec=transaction_ledger_query_spec(
                    filters=filters, sort_by="transaction_date", sort_order="asc"
                ),
                skip=0,
                limit=10,
            )
            expected_ids = [f"TRADE-UTC-WINDOW-{suffix}" for suffix in expected_suffixes]
            assert [row.transaction_id for row in rows] == expected_ids
            assert await transaction_repository.get_transactions_count(filters=filters) == len(
                expected_ids
            )
            expected_facts = {
                f"TRADE-{transaction_id}": (transaction_date, Decimal(amount))
                for transaction_id, transaction_date, amount in boundary_rows
            }
            assert [(row.transaction_date, row.gross_transaction_amount) for row in rows] == [
                expected_facts[transaction_id] for transaction_id in expected_ids
            ]


async def test_cashflow_source_cut_is_stable_across_products_and_rejects_foreign_tenant(
    setup_cashflow_data, async_db_session: AsyncSession
) -> None:
    """PostgreSQL proof that the common cut is admitted and replay-stable."""
    tenant_context = TenantContext(tenant_id=TenantId(TEST_TENANT_ID))
    foreign_tenant = TenantId("tenant-foreign")
    repo = CashflowRepository(async_db_session)

    source_evidence = await repo.get_cashflow_source_cut_evidence(
        portfolio_id="MWR_TEST_PORT_01",
        as_of_date=date(2025, 1, 31),
        tenant_id=tenant_context.tenant_id,
    )
    with pytest.raises(ValueError, match="not found"):
        await repo.get_cashflow_source_cut_evidence(
            portfolio_id="MWR_TEST_PORT_01",
            as_of_date=date(2025, 1, 31),
            tenant_id=foreign_tenant,
        )
    foreign_series = await repo.get_portfolio_cashflow_series_with_evidence(
        "MWR_TEST_PORT_01",
        date(2025, 1, 1),
        date(2025, 1, 31),
        tenant_id=foreign_tenant,
    )
    foreign_summary = await repo.get_portfolio_cash_movement_summary(
        "MWR_TEST_PORT_01",
        date(2025, 1, 1),
        date(2025, 1, 31),
        tenant_id=foreign_tenant,
    )
    await async_db_session.rollback()

    movement_service = CashMovementService(async_db_session)
    projection_service = CashflowProjectionService(async_db_session)
    movement_first = await movement_service.get_cash_movement_summary(
        portfolio_id="MWR_TEST_PORT_01",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        tenant_context=tenant_context,
    )
    await async_db_session.rollback()
    movement_replay = await movement_service.get_cash_movement_summary(
        portfolio_id="MWR_TEST_PORT_01",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        tenant_context=tenant_context,
    )
    await async_db_session.rollback()
    projection = await projection_service.get_cashflow_projection(
        portfolio_id="MWR_TEST_PORT_01",
        horizon_days=1,
        as_of_date=date(2025, 1, 31),
        tenant_context=tenant_context,
    )
    await async_db_session.rollback()
    assert source_evidence.materialized_at is not None
    assert source_evidence.cashflow_revision_count == 5
    assert source_evidence.cashflow_revision_digest is not None
    assert source_evidence.settlement_revision_count == 2
    assert source_evidence.settlement_revision_digest is not None
    assert foreign_series.rows == []
    assert foreign_series.source_row_count == 0
    assert foreign_summary.rows == []
    assert foreign_summary.source_row_count == 0
    assert movement_first.source_cut_id == movement_replay.source_cut_id
    assert movement_first.generated_at == movement_replay.generated_at
    assert movement_first.source_cut_id == projection.source_cut_id
    assert movement_first.generated_at == projection.generated_at
    assert movement_first.latest_evidence_timestamp is not None

    timestamp_only_at = datetime(2029, 1, 1, 12, tzinfo=UTC)
    await async_db_session.execute(
        sa.update(Cashflow)
        .where(Cashflow.portfolio_id == "MWR_TEST_PORT_01", Cashflow.transaction_id == "T1")
        .values(updated_at=timestamp_only_at)
    )
    await async_db_session.commit()
    timestamp_only_movement = await movement_service.get_cash_movement_summary(
        portfolio_id="MWR_TEST_PORT_01",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        tenant_context=tenant_context,
    )
    await async_db_session.rollback()
    assert timestamp_only_movement.source_cut_id == movement_first.source_cut_id
    assert timestamp_only_movement.generated_at == timestamp_only_at

    restatement_at = datetime(2030, 1, 1, 12, tzinfo=UTC)
    await async_db_session.execute(
        sa.update(Cashflow)
        .where(Cashflow.portfolio_id == "MWR_TEST_PORT_01", Cashflow.transaction_id == "T1")
        .values(amount=Decimal("10001"), updated_at=restatement_at)
    )
    await async_db_session.commit()
    restated_movement = await movement_service.get_cash_movement_summary(
        portfolio_id="MWR_TEST_PORT_01",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        tenant_context=tenant_context,
    )

    assert restated_movement.source_cut_id != movement_first.source_cut_id
    assert restated_movement.generated_at > timestamp_only_movement.generated_at

    await async_db_session.rollback()
    await async_db_session.execute(
        sa.update(Cashflow)
        .where(Cashflow.portfolio_id == "MWR_TEST_PORT_01", Cashflow.transaction_id == "T1")
        .values(amount=Decimal("10002"))
    )
    pending_evidence = await repo.get_cashflow_source_cut_evidence(
        portfolio_id="MWR_TEST_PORT_01",
        as_of_date=date(2025, 1, 31),
        tenant_id=tenant_context.tenant_id,
    )
    assert pending_evidence.cashflow_revision_digest != source_evidence.cashflow_revision_digest
    await async_db_session.rollback()
    rollback_replay = await movement_service.get_cash_movement_summary(
        portfolio_id="MWR_TEST_PORT_01",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        tenant_context=tenant_context,
    )
    assert rollback_replay.source_cut_id == restated_movement.source_cut_id


async def test_get_income_cashflows_is_epoch_aware(
    setup_cashflow_data, async_db_session: AsyncSession
):
    """
    GIVEN income cashflows in different epochs
    WHEN get_income_cashflows_for_position is called
    THEN it should only return the cashflow from the current, active epoch.
    """
    # ARRANGE
    repo = CashflowRepository(async_db_session)
    portfolio_id = "MWR_TEST_PORT_01"
    security_id = "INCOME_SEC_01"
    start_date = date(2025, 1, 1)
    end_date = date(2025, 3, 31)

    # ACT
    results = await repo.get_income_cashflows_for_position(
        portfolio_id, security_id, start_date, end_date
    )

    # ASSERT
    assert len(results) == 1
    # Verify it returned the record from epoch 1 and filtered out the one from epoch 0
    assert results[0].epoch == 1
    assert results[0].amount == Decimal("100")


async def test_cashflows_allow_same_transaction_id_across_epochs(clean_db, async_db_session):
    """
    GIVEN a transaction that is recalculated into a new epoch
    WHEN cashflows are persisted for both the original and replay epochs
    THEN the database should retain both versions keyed by (transaction_id, epoch).
    """
    portfolio_id = "EPOCH_CASHFLOW_PORT"
    security_id = "EPOCH_CASHFLOW_SEC"
    transaction_id = "EPOCH_CASHFLOW_TXN_01"

    async_db_session.add(
        Portfolio(
            tenant_id=TEST_TENANT_ID,
            portfolio_id=portfolio_id,
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="f",
        )
    )
    async_db_session.add(
        Transaction(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            instrument_id="I-EPOCH-1",
            security_id=security_id,
            transaction_date=date(2025, 2, 10),
            transaction_type="BUY",
            quantity=1,
            price=100,
            gross_transaction_amount=100,
            trade_currency="USD",
            currency="USD",
        )
    )
    async_db_session.add(
        PositionState(
            portfolio_id=portfolio_id,
            security_id=security_id,
            epoch=1,
            watermark_date=date(2025, 2, 9),
        )
    )
    await async_db_session.flush()

    async_db_session.add_all(
        [
            Cashflow(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id=security_id,
                cashflow_date=date(2025, 2, 10),
                amount=Decimal("-100"),
                currency="USD",
                classification="INVESTMENT_OUTFLOW",
                timing="BOD",
                calculation_type="NET",
                is_position_flow=True,
                epoch=0,
            ),
            Cashflow(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                security_id=security_id,
                cashflow_date=date(2025, 2, 10),
                amount=Decimal("-100"),
                currency="USD",
                classification="INVESTMENT_OUTFLOW",
                timing="BOD",
                calculation_type="NET",
                is_position_flow=True,
                epoch=1,
            ),
        ]
    )
    await async_db_session.commit()

    result = await async_db_session.execute(
        sa.text(
            """
            SELECT transaction_id, epoch
            FROM cashflows
            WHERE transaction_id = :transaction_id
            ORDER BY epoch
            """
        ),
        {"transaction_id": transaction_id},
    )
    rows = result.fetchall()

    assert rows == [(transaction_id, 0), (transaction_id, 1)]
