"""Prove portfolio aggregation job recovery and concurrent claim behavior."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    Instrument,
    Portfolio,
    PortfolioAggregationJob,
    PositionTimeseries,
)
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from src.services.portfolio_derived_state_service.app.domain.aggregation_jobs.models import (
    AggregationJobCompletionDisposition,
    AggregationJobFailureDisposition,
    AggregationJobLeaseClaim,
    ExpiredAggregationJobRecovery,
)
from src.services.portfolio_derived_state_service.app.infrastructure import (
    portfolio_aggregation_repository,
    timeseries_generation_repository,
)

PortfolioAggregationRepository = portfolio_aggregation_repository.PortfolioAggregationRepository
TimeseriesGenerationRepository = timeseries_generation_repository.TimeseriesGenerationRepository

pytestmark = pytest.mark.asyncio


async def _seed_expired_aggregation_jobs(
    session: AsyncSession,
    *,
    count: int,
    prefix: str,
) -> list[int]:
    expired_at = datetime.now(UTC) - timedelta(minutes=5)
    portfolios = [
        Portfolio(
            portfolio_id=f"{prefix}-{index:04d}",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="balanced",
            investment_time_horizon="long_term",
            portfolio_type="discretionary",
            booking_center_code="SG",
            client_id=f"CLIENT-{prefix}-{index:04d}",
            status="ACTIVE",
        )
        for index in range(count)
    ]
    session.add_all(portfolios)
    await session.flush()
    jobs = [
        PortfolioAggregationJob(
            portfolio_id=portfolio.portfolio_id,
            aggregation_date=date(2026, 4, 10),
            status="PROCESSING",
            attempt_count=1,
            lease_owner="expired-worker",
            lease_token=f"expired-{index:04d}",
            lease_expires_at=expired_at,
        )
        for index, portfolio in enumerate(portfolios)
    ]
    session.add_all(jobs)
    await session.commit()
    return [int(job.id) for job in jobs]


async def _seed_aggregation_fence_scope(
    session: AsyncSession,
    *,
    portfolio_id: str,
    security_id: str,
    aggregation_date: date,
) -> None:
    session.add(
        Portfolio(
            portfolio_id=portfolio_id,
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="ACTIVE",
        )
    )
    session.add(
        Instrument(
            security_id=security_id,
            name="Aggregation Source Fence Instrument",
            isin=f"US-{security_id}",
            asset_class="EQUITY",
            product_type="COMMON_STOCK",
            currency="USD",
        )
    )
    await session.flush()
    session.add(
        PortfolioAggregationJob(
            portfolio_id=portfolio_id,
            aggregation_date=aggregation_date,
            status="PENDING",
            target_epoch=0,
            source_revision=1,
        )
    )
    session.add(
        DailyPositionSnapshot(
            portfolio_id=portfolio_id,
            security_id=security_id,
            date=aggregation_date,
            epoch=0,
            quantity=Decimal("1"),
            cost_basis=Decimal("1"),
            cost_basis_local=Decimal("1"),
            market_value=Decimal("1"),
            valuation_status="VALUED_CURRENT",
        )
    )
    session.add(
        PositionTimeseries(
            portfolio_id=portfolio_id,
            security_id=security_id,
            date=aggregation_date,
            epoch=0,
            bod_market_value=Decimal("1"),
            bod_cashflow_position=Decimal("0"),
            eod_cashflow_position=Decimal("0"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("0"),
            eod_market_value=Decimal("1"),
            fees=Decimal("0"),
            quantity=Decimal("1"),
            cost=Decimal("1"),
        )
    )
    await session.commit()


async def _add_materialized_position_scope(
    session: AsyncSession,
    *,
    portfolio_id: str,
    security_id: str,
    snapshot_date: date,
    epoch: int,
) -> None:
    session.add(
        Instrument(
            security_id=security_id,
            name="Advanced Epoch Aggregation Instrument",
            isin=f"US-{security_id}",
            asset_class="EQUITY",
            product_type="COMMON_STOCK",
            currency="USD",
        )
    )
    await session.flush()
    session.add_all(
        [
            DailyPositionSnapshot(
                portfolio_id=portfolio_id,
                security_id=security_id,
                date=snapshot_date,
                epoch=epoch,
                quantity=Decimal("2"),
                cost_basis=Decimal("2"),
                cost_basis_local=Decimal("2"),
                market_value=Decimal("3"),
                market_value_local=Decimal("3"),
                valuation_status="VALUED_CURRENT",
            ),
            PositionTimeseries(
                portfolio_id=portfolio_id,
                security_id=security_id,
                date=snapshot_date,
                epoch=epoch,
                bod_market_value=Decimal("2"),
                bod_cashflow_position=Decimal("0"),
                eod_cashflow_position=Decimal("0"),
                bod_cashflow_portfolio=Decimal("0"),
                eod_cashflow_portfolio=Decimal("0"),
                eod_market_value=Decimal("3"),
                fees=Decimal("0"),
                quantity=Decimal("2"),
                cost=Decimal("2"),
            ),
        ]
    )


@pytest.fixture(scope="function")
def setup_stale_aggregation_job_data(db_engine, clean_db):
    """Seed expired, current, and pending aggregation lease states."""

    with Session(db_engine) as session:
        now = datetime.now(UTC)
        expired_at = now - timedelta(minutes=20)
        current_expiry = now + timedelta(minutes=5)

        portfolios = [
            Portfolio(
                portfolio_id="P1_STALE",
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            ),
            Portfolio(
                portfolio_id="P2_RECENT",
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            ),
            Portfolio(
                portfolio_id="P3_PENDING",
                base_currency="USD",
                open_date=date(2024, 1, 1),
                risk_exposure="a",
                investment_time_horizon="b",
                portfolio_type="c",
                booking_center_code="d",
                client_id="e",
                status="f",
            ),
        ]
        session.add_all(portfolios)
        session.flush()

        jobs = [
            PortfolioAggregationJob(
                portfolio_id="P1_STALE",
                aggregation_date=date(2025, 8, 1),
                status="PROCESSING",
                attempt_count=1,
                lease_owner="expired-worker",
                lease_token="expired-token",
                lease_expires_at=expired_at,
            ),
            PortfolioAggregationJob(
                portfolio_id="P2_RECENT",
                aggregation_date=date(2025, 8, 1),
                status="PROCESSING",
                attempt_count=1,
                lease_owner="current-worker",
                lease_token="current-token",
                lease_expires_at=current_expiry,
            ),
            PortfolioAggregationJob(
                portfolio_id="P3_PENDING",
                aggregation_date=date(2025, 8, 1),
                status="PENDING",
            ),
        ]
        session.add_all(jobs)
        session.commit()


@pytest.mark.lifecycle
async def test_recover_expired_job_leases_requeues_retryable_claim(
    db_engine, clean_db, setup_stale_aggregation_job_data, async_db_session: AsyncSession
):
    """Requeue only an expired processing lease below its retry ceiling."""

    repo = PortfolioAggregationRepository(async_db_session)
    await async_db_session.execute(
        update(PortfolioAggregationJob)
        .where(PortfolioAggregationJob.portfolio_id == "P1_STALE")
        .values(failure_reason=portfolio_aggregation_repository.AGGREGATION_REPROCESS_REQUESTED)
    )
    await async_db_session.commit()

    recovery = await repo.recover_expired_job_leases(
        now=datetime.now(UTC),
        max_attempts=3,
    )
    await async_db_session.commit()

    assert recovery.requeued_count == 1
    assert recovery.failed_count == 0

    with Session(db_engine) as session:
        job1 = session.query(PortfolioAggregationJob).filter_by(portfolio_id="P1_STALE").one()
        assert job1.status == "PENDING"
        assert job1.lease_owner is None
        assert job1.lease_token is None
        assert job1.lease_expires_at is None
        assert job1.failure_reason is None

        job2 = session.query(PortfolioAggregationJob).filter_by(portfolio_id="P2_RECENT").one()
        assert job2.status == "PROCESSING"
        assert job2.lease_token == "current-token"

        job3 = session.query(PortfolioAggregationJob).filter_by(portfolio_id="P3_PENDING").one()
        assert job3.status == "PENDING"


@pytest.mark.lifecycle
async def test_recover_expired_job_leases_fails_retry_exhausted_claim(
    db_engine, clean_db, setup_stale_aggregation_job_data, async_db_session: AsyncSession
):
    """Fail an expired processing lease that reached its retry ceiling."""

    repo = PortfolioAggregationRepository(async_db_session)

    recovery = await repo.recover_expired_job_leases(
        now=datetime.now(UTC),
        max_attempts=1,
    )
    await async_db_session.commit()

    assert recovery.requeued_count == 0
    assert recovery.failed_count == 1

    with Session(db_engine) as session:
        job1 = session.query(PortfolioAggregationJob).filter_by(portfolio_id="P1_STALE").one()
        assert job1.status == "FAILED"
        assert job1.failure_reason == "Aggregation job lease expired after max attempts"
        assert job1.lease_owner is None
        assert job1.lease_token is None
        assert job1.lease_expires_at is None


@pytest.mark.lifecycle
async def test_expired_aggregation_backlog_drains_in_bounded_cohorts(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_expired_aggregation_jobs(
        async_db_session,
        count=1_001,
        prefix="P-AGG-STALE-COHORT",
    )
    repository = PortfolioAggregationRepository(async_db_session)

    first = await repository.recover_expired_job_leases(
        now=datetime.now(UTC),
        max_attempts=3,
    )
    await async_db_session.commit()
    second = await repository.recover_expired_job_leases(
        now=datetime.now(UTC),
        max_attempts=3,
    )
    await async_db_session.commit()

    assert first == ExpiredAggregationJobRecovery(requeued_count=1_000, failed_count=0)
    assert second == ExpiredAggregationJobRecovery(requeued_count=1, failed_count=0)
    status_counts = dict(
        (
            await async_db_session.execute(
                select(PortfolioAggregationJob.status, func.count())
                .where(PortfolioAggregationJob.portfolio_id.like("P-AGG-STALE-COHORT-%"))
                .group_by(PortfolioAggregationJob.status)
            )
        ).all()
    )
    assert status_counts == {"PENDING": 1_001}


@pytest.mark.lifecycle
async def test_concurrent_aggregation_recovery_claims_disjoint_stale_cohorts(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_expired_aggregation_jobs(
        async_db_session,
        count=1_001,
        prefix="P-AGG-STALE-CONCURRENT",
    )
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    async with session_factory() as first_session, session_factory() as second_session:
        async with first_session.begin():
            first = await PortfolioAggregationRepository(first_session).recover_expired_job_leases(
                max_attempts=3
            )
            async with second_session.begin():
                second = await PortfolioAggregationRepository(
                    second_session
                ).recover_expired_job_leases(max_attempts=3)

    assert first == ExpiredAggregationJobRecovery(requeued_count=1_000, failed_count=0)
    assert second == ExpiredAggregationJobRecovery(requeued_count=1, failed_count=0)
    pending_count = await async_db_session.scalar(
        select(func.count()).where(
            PortfolioAggregationJob.portfolio_id.like("P-AGG-STALE-CONCURRENT-%"),
            PortfolioAggregationJob.status == "PENDING",
        )
    )
    assert pending_count == 1_001


@pytest.mark.lifecycle
async def test_later_aggregation_recovery_chunk_failure_rolls_back_all_updates(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    job_ids = await _seed_expired_aggregation_jobs(
        async_db_session,
        count=1_001,
        prefix="P-AGG-STALE-ROLLBACK",
    )
    bind = async_db_session.bind
    assert bind is not None
    update_count = 0

    def fail_second_update(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        nonlocal update_count
        normalized = statement.lower().lstrip()
        if normalized.startswith("update portfolio_aggregation_jobs"):
            update_count += 1
            if update_count == 2:
                raise RuntimeError("injected second aggregation recovery chunk failure")

    sqlalchemy_event.listen(bind.sync_engine, "before_cursor_execute", fail_second_update)
    try:
        with pytest.raises(RuntimeError, match="second aggregation recovery chunk failure"):
            async with async_db_session.begin():
                await PortfolioAggregationRepository(async_db_session)._requeue_expired_job_leases(
                    job_ids
                )
    finally:
        sqlalchemy_event.remove(bind.sync_engine, "before_cursor_execute", fail_second_update)

    durable_processing_count = await async_db_session.scalar(
        select(func.count()).where(
            PortfolioAggregationJob.id.in_(job_ids),
            PortfolioAggregationJob.status == "PROCESSING",
        )
    )
    assert update_count == 2
    assert durable_processing_count == 1_001


@pytest.mark.lifecycle
async def test_recovery_skips_row_locked_by_terminal_writer_transaction(
    db_engine, clean_db, setup_stale_aggregation_job_data, async_db_session: AsyncSession
):
    """Skip a stale row while a terminal writer transaction owns the row lock."""

    job_id = (
        (
            await async_db_session.execute(
                select(PortfolioAggregationJob.id).where(
                    PortfolioAggregationJob.portfolio_id == "P1_STALE"
                )
            )
        )
        .scalars()
        .one()
    )
    await async_db_session.commit()

    with Session(db_engine) as completing_session:
        completing_session.execute(
            update(PortfolioAggregationJob)
            .where(PortfolioAggregationJob.id == job_id)
            .values(status="COMPLETE", updated_at=datetime.now(UTC))
        )
        recovery = await asyncio.wait_for(
            PortfolioAggregationRepository(async_db_session).recover_expired_job_leases(
                now=datetime.now(UTC),
                max_attempts=3,
            ),
            timeout=15,
        )
        await async_db_session.commit()
        completing_session.commit()

    assert recovery.requeued_count == 0
    assert recovery.failed_count == 0

    with Session(db_engine) as session:
        job = session.query(PortfolioAggregationJob).filter_by(id=job_id).one()
        assert job.status == "COMPLETE"


@pytest.mark.lifecycle
async def test_claim_eligible_jobs_does_not_double_claim_under_concurrency(
    clean_db, async_db_session: AsyncSession
):
    """Lease one ready job to only one of two concurrent claimers."""

    async_db_session.add(
        Portfolio(
            portfolio_id="P-AGG-CLAIM",
            base_currency="USD",
            open_date=date(2024, 1, 1),
            risk_exposure="a",
            investment_time_horizon="b",
            portfolio_type="c",
            booking_center_code="d",
            client_id="e",
            status="ACTIVE",
        )
    )
    async_db_session.add(
        Instrument(
            security_id="SEC-AGG-CLAIM",
            name="Aggregation Claim Instrument",
            isin="US-AGG-CLAIM",
            asset_class="EQUITY",
            product_type="COMMON_STOCK",
            currency="USD",
        )
    )
    await async_db_session.flush()
    async_db_session.add(
        PortfolioAggregationJob(
            portfolio_id="P-AGG-CLAIM",
            aggregation_date=date(2025, 8, 15),
            status="PENDING",
        )
    )
    async_db_session.add(
        DailyPositionSnapshot(
            portfolio_id="P-AGG-CLAIM",
            security_id="SEC-AGG-CLAIM",
            date=date(2025, 8, 15),
            epoch=0,
            quantity=Decimal("1"),
            cost_basis=Decimal("1"),
            cost_basis_local=Decimal("1"),
            valuation_status="VALUED_CURRENT",
        )
    )
    async_db_session.add(
        PositionTimeseries(
            portfolio_id="P-AGG-CLAIM",
            security_id="SEC-AGG-CLAIM",
            date=date(2025, 8, 15),
            epoch=0,
            bod_market_value=Decimal("1"),
            bod_cashflow_position=Decimal("0"),
            eod_cashflow_position=Decimal("0"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("0"),
            eod_market_value=Decimal("1"),
            fees=Decimal("0"),
            quantity=Decimal("1"),
            cost=Decimal("1"),
        )
    )
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def claim_one(claimant: str):
        async with session_factory() as session:
            repo = PortfolioAggregationRepository(session)
            claimed = await repo.claim_eligible_jobs(
                batch_size=1,
                lease=AggregationJobLeaseClaim(
                    owner=f"aggregation-runtime-{claimant}",
                    token=f"lease-token-{claimant}",
                    duration_seconds=300,
                ),
            )
            await session.commit()
            return claimed

    first_claim, second_claim = await asyncio.gather(claim_one("one"), claim_one("two"))
    all_claimed = [*first_claim, *second_claim]

    assert len(all_claimed) == 1
    assert len({job.id for job in all_claimed}) == 1

    async with session_factory() as verification_session:
        jobs = (
            (
                await verification_session.execute(
                    select(PortfolioAggregationJob).where(
                        PortfolioAggregationJob.portfolio_id == "P-AGG-CLAIM",
                        PortfolioAggregationJob.aggregation_date == date(2025, 8, 15),
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(jobs) == 1
    assert jobs[0].status == "PROCESSING"
    assert jobs[0].attempt_count == 1
    assert jobs[0].lease_token in {"lease-token-one", "lease-token-two"}
    async with session_factory() as authority_session:
        database_now = await authority_session.scalar(select(func.clock_timestamp()))
        lease_expiry = await authority_session.scalar(
            select(PortfolioAggregationJob.lease_expires_at).where(
                PortfolioAggregationJob.portfolio_id == "P-AGG-CLAIM"
            )
        )
        recovery = await PortfolioAggregationRepository(
            authority_session
        ).recover_expired_job_leases(max_attempts=3)
    assert database_now is not None
    assert lease_expiry is not None
    assert 295 <= (lease_expiry - database_now).total_seconds() <= 305
    assert recovery == ExpiredAggregationJobRecovery(requeued_count=0, failed_count=0)


@pytest.mark.lifecycle
async def test_newer_epoch_supersedes_claim_and_rearms_same_portfolio_day(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """Fence an epoch-zero claim once epoch-one source material arrives."""

    portfolio_id = "P-AGG-EPOCH-FENCE"
    security_id = "SEC-AGG-EPOCH-FENCE"
    aggregation_date = date(2025, 8, 15)
    await _seed_aggregation_fence_scope(
        async_db_session,
        portfolio_id=portfolio_id,
        security_id=security_id,
        aggregation_date=aggregation_date,
    )

    repository = PortfolioAggregationRepository(async_db_session)
    first_claim = (
        await repository.claim_eligible_jobs(
            batch_size=1,
            lease=AggregationJobLeaseClaim(
                owner="aggregation-runtime-first",
                token="lease-token-first",
                duration_seconds=300,
            ),
        )
    )[0]
    assert first_claim.target_epoch == 0
    assert first_claim.source_revision == 1
    await async_db_session.commit()

    async_db_session.add(
        DailyPositionSnapshot(
            portfolio_id=portfolio_id,
            security_id=security_id,
            date=aggregation_date,
            epoch=1,
            quantity=Decimal("1"),
            cost_basis=Decimal("1"),
            cost_basis_local=Decimal("1"),
            valuation_status="VALUED_CURRENT",
        )
    )
    await async_db_session.commit()

    disposition = await repository.complete_or_requeue_job(
        job_id=first_claim.id,
        lease_token=first_claim.lease.token,
        target_epoch=first_claim.target_epoch,
        source_revision=first_claim.source_revision,
    )
    await async_db_session.commit()

    assert disposition is AggregationJobCompletionDisposition.REQUEUED
    requeued_job = await async_db_session.get(
        PortfolioAggregationJob,
        first_claim.id,
    )
    assert requeued_job is not None
    assert requeued_job.status == "PENDING"
    assert requeued_job.target_epoch == 0
    assert requeued_job.source_revision == 1

    async_db_session.add(
        PositionTimeseries(
            portfolio_id=portfolio_id,
            security_id=security_id,
            date=aggregation_date,
            epoch=1,
            bod_market_value=Decimal("1"),
            bod_cashflow_position=Decimal("0"),
            eod_cashflow_position=Decimal("0"),
            bod_cashflow_portfolio=Decimal("0"),
            eod_cashflow_portfolio=Decimal("0"),
            eod_market_value=Decimal("2"),
            fees=Decimal("0"),
            quantity=Decimal("1"),
            cost=Decimal("1"),
        )
    )
    await async_db_session.flush()
    await TimeseriesGenerationRepository(async_db_session).stage_aggregation_jobs(
        portfolio_id,
        [aggregation_date],
        1,
        "corr-epoch-one",
    )
    await async_db_session.commit()

    second_claim = (
        await repository.claim_eligible_jobs(
            batch_size=1,
            lease=AggregationJobLeaseClaim(
                owner="aggregation-runtime-second",
                token="lease-token-second",
                duration_seconds=300,
            ),
        )
    )[0]
    assert second_claim.id == first_claim.id
    assert second_claim.target_epoch == 1
    assert second_claim.source_revision == 2
    await async_db_session.commit()

    await TimeseriesGenerationRepository(async_db_session).stage_aggregation_jobs(
        portfolio_id,
        [aggregation_date],
        0,
        "corr-delayed-lower-epoch",
    )
    await async_db_session.commit()
    delayed_lower_epoch_disposition = await repository.complete_or_requeue_job(
        job_id=second_claim.id,
        lease_token=second_claim.lease.token,
        target_epoch=second_claim.target_epoch,
        source_revision=second_claim.source_revision,
    )
    await async_db_session.commit()

    assert delayed_lower_epoch_disposition is AggregationJobCompletionDisposition.REQUEUED
    third_claim = (
        await repository.claim_eligible_jobs(
            batch_size=1,
            lease=AggregationJobLeaseClaim(
                owner="aggregation-runtime-third",
                token="lease-token-third",
                duration_seconds=300,
            ),
        )
    )[0]
    assert third_claim.id == first_claim.id
    assert third_claim.target_epoch == 1
    assert third_claim.source_revision == 3


@pytest.mark.lifecycle
async def test_claim_promotes_carry_forward_day_to_authoritative_portfolio_epoch(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """Claim a non-business-day job after another security advances the portfolio epoch."""

    portfolio_id = "P-AGG-CARRY-FORWARD-EPOCH"
    carried_security_id = "SEC-AGG-CARRIED"
    advanced_security_id = "SEC-AGG-ADVANCED"
    aggregation_date = date(2026, 3, 8)
    advanced_snapshot_date = date(2026, 3, 6)
    await _seed_aggregation_fence_scope(
        async_db_session,
        portfolio_id=portfolio_id,
        security_id=carried_security_id,
        aggregation_date=aggregation_date,
    )
    await _add_materialized_position_scope(
        async_db_session,
        portfolio_id=portfolio_id,
        security_id=advanced_security_id,
        snapshot_date=advanced_snapshot_date,
        epoch=1,
    )
    await async_db_session.commit()

    repository = PortfolioAggregationRepository(async_db_session)
    claim = (
        await repository.claim_eligible_jobs(
            batch_size=1,
            lease=AggregationJobLeaseClaim(
                owner="aggregation-runtime-carry-forward",
                token="lease-token-carry-forward",
                duration_seconds=300,
            ),
        )
    )[0]

    assert claim.target_epoch == 1
    assert claim.source_revision == 2
    disposition = await repository.complete_or_requeue_job(
        job_id=claim.id,
        lease_token=claim.lease.token,
        target_epoch=claim.target_epoch,
        source_revision=claim.source_revision,
    )
    assert disposition is AggregationJobCompletionDisposition.COMPLETE


@pytest.mark.lifecycle
async def test_claimed_target_is_fenced_when_source_advances_between_claim_statements(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """Keep the selected target stable and requeue when source commits before lease update."""

    portfolio_id = "P-AGG-CLAIM-SNAPSHOT-FENCE"
    aggregation_date = date(2026, 3, 8)
    await _seed_aggregation_fence_scope(
        async_db_session,
        portfolio_id=portfolio_id,
        security_id="SEC-AGG-CLAIM-SNAPSHOT-CARRIED",
        aggregation_date=aggregation_date,
    )
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async with session_factory() as claim_session:
        repository = PortfolioAggregationRepository(claim_session)
        selected_targets = await repository._find_eligible_job_targets(batch_size=1)
        assert selected_targets[0].target_epoch == 0
        assert selected_targets[0].source_advanced is False

        async with session_factory() as source_session:
            await _add_materialized_position_scope(
                source_session,
                portfolio_id=portfolio_id,
                security_id="SEC-AGG-CLAIM-SNAPSHOT-ADVANCED",
                snapshot_date=date(2026, 3, 6),
                epoch=1,
            )
            await source_session.commit()

        first_lease = AggregationJobLeaseClaim(
            owner="aggregation-runtime-snapshot-fence-first",
            token="lease-token-snapshot-fence-first",
            duration_seconds=300,
        )
        first_claim = (
            await repository._claim_eligible_job_rows(
                selected_targets,
                lease=first_lease,
            )
        )[0]
        await claim_session.commit()
        assert first_claim.target_epoch == 0
        assert first_claim.source_revision == 1

        disposition = await repository.complete_or_requeue_job(
            job_id=first_claim.id,
            lease_token=first_lease.token,
            target_epoch=first_claim.target_epoch,
            source_revision=first_claim.source_revision,
        )
        await claim_session.commit()
        assert disposition is AggregationJobCompletionDisposition.REQUEUED

        second_claim = (
            await repository.claim_eligible_jobs(
                batch_size=1,
                lease=AggregationJobLeaseClaim(
                    owner="aggregation-runtime-snapshot-fence-second",
                    token="lease-token-snapshot-fence-second",
                    duration_seconds=300,
                ),
            )
        )[0]
        assert second_claim.target_epoch == 1
        assert second_claim.source_revision == 2


@pytest.mark.lifecycle
async def test_aggregation_terminal_fence_uses_statement_time_after_transaction_ages(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """Reject expiry even when the materialization transaction began with a valid lease."""

    portfolio_id = "P-AGG-AGED-TRANSACTION"
    aggregation_date = date(2026, 3, 8)
    await _seed_aggregation_fence_scope(
        async_db_session,
        portfolio_id=portfolio_id,
        security_id="SEC-AGG-AGED-TRANSACTION",
        aggregation_date=aggregation_date,
    )
    await async_db_session.commit()
    repository = PortfolioAggregationRepository(async_db_session)
    claim = (
        await repository.claim_eligible_jobs(
            batch_size=1,
            lease=AggregationJobLeaseClaim(
                owner="aggregation-runtime-aged-transaction",
                token="lease-token-aged-transaction",
                duration_seconds=300,
            ),
        )
    )[0]
    await async_db_session.commit()

    # Start the worker transaction before another session shortens the lease. A now()-based
    # terminal predicate would keep observing this transaction's earlier timestamp.
    await async_db_session.execute(select(func.now()))
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    async with session_factory() as control_session:
        await control_session.execute(
            update(PortfolioAggregationJob)
            .where(PortfolioAggregationJob.id == claim.id)
            .values(lease_expires_at=func.clock_timestamp() + text("INTERVAL '1 second'"))
        )
        await control_session.commit()
    await async_db_session.execute(select(func.pg_sleep(1.25)))

    disposition = await repository.complete_or_requeue_job(
        job_id=claim.id,
        lease_token=claim.lease.token,
        target_epoch=claim.target_epoch,
        source_revision=claim.source_revision,
    )
    await async_db_session.commit()

    assert disposition is AggregationJobCompletionDisposition.LOST_OWNERSHIP


@pytest.mark.lifecycle
async def test_same_epoch_snapshot_corrections_requeue_success_and_failure(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """Fence both terminal paths while corrected same-epoch staging is pending."""

    portfolio_id = "P-AGG-SAME-EPOCH-FENCE"
    security_id = "SEC-AGG-SAME-EPOCH-FENCE"
    aggregation_date = date(2025, 8, 16)
    await _seed_aggregation_fence_scope(
        async_db_session,
        portfolio_id=portfolio_id,
        security_id=security_id,
        aggregation_date=aggregation_date,
    )
    repository = PortfolioAggregationRepository(async_db_session)

    first_claim = (
        await repository.claim_eligible_jobs(
            batch_size=1,
            lease=AggregationJobLeaseClaim(
                owner="aggregation-runtime-same-epoch-success",
                token="lease-token-same-epoch-success",
                duration_seconds=300,
            ),
        )
    )[0]
    await async_db_session.commit()
    await async_db_session.execute(
        update(DailyPositionSnapshot)
        .where(
            DailyPositionSnapshot.portfolio_id == portfolio_id,
            DailyPositionSnapshot.security_id == security_id,
            DailyPositionSnapshot.date == aggregation_date,
            DailyPositionSnapshot.epoch == 0,
        )
        .values(market_value=Decimal("2"), updated_at=func.now())
    )
    await async_db_session.commit()

    completion = await repository.complete_or_requeue_job(
        job_id=first_claim.id,
        lease_token=first_claim.lease.token,
        target_epoch=first_claim.target_epoch,
        source_revision=first_claim.source_revision,
    )
    await async_db_session.commit()
    assert completion is AggregationJobCompletionDisposition.REQUEUED

    await async_db_session.execute(
        update(PositionTimeseries)
        .where(
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.security_id == security_id,
            PositionTimeseries.date == aggregation_date,
            PositionTimeseries.epoch == 0,
        )
        .values(eod_market_value=Decimal("2"), updated_at=func.now())
    )
    await TimeseriesGenerationRepository(async_db_session).stage_aggregation_jobs(
        portfolio_id,
        [aggregation_date],
        0,
        "corr-same-epoch-one",
    )
    await async_db_session.commit()

    second_claim = (
        await repository.claim_eligible_jobs(
            batch_size=1,
            lease=AggregationJobLeaseClaim(
                owner="aggregation-runtime-same-epoch-failure",
                token="lease-token-same-epoch-failure",
                duration_seconds=300,
            ),
        )
    )[0]
    assert second_claim.target_epoch == 0
    assert second_claim.source_revision == 2
    await async_db_session.commit()
    await async_db_session.execute(
        update(DailyPositionSnapshot)
        .where(
            DailyPositionSnapshot.portfolio_id == portfolio_id,
            DailyPositionSnapshot.security_id == security_id,
            DailyPositionSnapshot.date == aggregation_date,
            DailyPositionSnapshot.epoch == 0,
        )
        .values(market_value=Decimal("3"), updated_at=func.now())
    )
    await async_db_session.commit()

    failure = await repository.fail_or_requeue_job(
        job_id=second_claim.id,
        lease_token=second_claim.lease.token,
        target_epoch=second_claim.target_epoch,
        source_revision=second_claim.source_revision,
    )
    await async_db_session.commit()
    assert failure is AggregationJobFailureDisposition.REQUEUED

    await async_db_session.execute(
        update(PositionTimeseries)
        .where(
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.security_id == security_id,
            PositionTimeseries.date == aggregation_date,
            PositionTimeseries.epoch == 0,
        )
        .values(eod_market_value=Decimal("3"), updated_at=func.now())
    )
    await TimeseriesGenerationRepository(async_db_session).stage_aggregation_jobs(
        portfolio_id,
        [aggregation_date],
        0,
        "corr-same-epoch-two",
    )
    await async_db_session.commit()

    final_claim = (
        await repository.claim_eligible_jobs(
            batch_size=1,
            lease=AggregationJobLeaseClaim(
                owner="aggregation-runtime-same-epoch-final",
                token="lease-token-same-epoch-final",
                duration_seconds=300,
            ),
        )
    )[0]
    assert final_claim.target_epoch == 0
    assert final_claim.source_revision == 3
    final_completion = await repository.complete_or_requeue_job(
        job_id=final_claim.id,
        lease_token=final_claim.lease.token,
        target_epoch=final_claim.target_epoch,
        source_revision=final_claim.source_revision,
    )
    assert final_completion is AggregationJobCompletionDisposition.COMPLETE


@pytest.mark.lifecycle
async def test_expired_superseded_revision_requeues_after_prior_attempt_exhaustion(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    """Do not fail a source revision that has never received its own attempt."""

    now = datetime.now(UTC)
    job = PortfolioAggregationJob(
        portfolio_id="P-AGG-SUPERSEDED-RECOVERY",
        aggregation_date=date(2025, 8, 17),
        status="PROCESSING",
        attempt_count=3,
        target_epoch=2,
        source_revision=4,
        failure_reason="REPROCESS_REQUESTED",
        lease_owner="expired-worker",
        lease_token="expired-worker-token",
        lease_expires_at=now - timedelta(minutes=1),
    )
    async_db_session.add(job)
    await async_db_session.commit()

    recovery = await PortfolioAggregationRepository(async_db_session).recover_expired_job_leases(
        now=now, max_attempts=3
    )
    await async_db_session.commit()
    await async_db_session.refresh(job)

    assert recovery == ExpiredAggregationJobRecovery(
        requeued_count=1,
        failed_count=0,
    )
    assert job.status == "PENDING"
    assert job.attempt_count == 3
    assert job.source_revision == 4
    assert job.failure_reason is None
    assert job.lease_owner is None
    assert job.lease_token is None
    assert job.lease_expires_at is None
