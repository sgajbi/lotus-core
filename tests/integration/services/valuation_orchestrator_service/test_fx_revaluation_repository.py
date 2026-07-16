"""PostgreSQL integration tests for direct-pair FX correction revaluation."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
    ReprocessingJob,
    Transaction,
)
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.valuation_orchestrator_service.app.core.fx_revaluation_job_processor import (
    FxRevaluationJobProcessor,
)
from src.services.valuation_orchestrator_service.app.domain.fx_revaluation import (
    ClaimedFxRevaluationJob,
    DirectCurrencyPair,
    FxRateCorrection,
    RejectedFxRevaluationJob,
)
from src.services.valuation_orchestrator_service.app.infrastructure.repositories import (
    fx_revaluation_repository,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]


def _portfolio(portfolio_id: str, base_currency: str) -> Portfolio:
    return Portfolio(
        portfolio_id=portfolio_id,
        base_currency=base_currency,
        open_date=date(2026, 1, 1),
        risk_exposure="balanced",
        investment_time_horizon="long_term",
        portfolio_type="discretionary",
        booking_center_code="SG",
        client_id=f"CLIENT-{portfolio_id}",
        status="ACTIVE",
    )


def _instrument(security_id: str, currency: str) -> Instrument:
    return Instrument(
        security_id=security_id,
        name=f"{security_id} instrument",
        isin=f"ISIN-{security_id}",
        currency=currency,
        product_type="BOND",
        asset_class="FIXED_INCOME",
    )


def _transaction(transaction_id: str, portfolio_id: str, security_id: str) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id=security_id,
        security_id=security_id,
        transaction_date=date(2026, 4, 1),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        trade_currency="USD",
        currency="USD",
    )


async def _seed_position(
    session: AsyncSession,
    *,
    portfolio_id: str,
    security_id: str,
    transaction_id: str,
    quantity: Decimal,
) -> None:
    session.add(
        PositionState(
            portfolio_id=portfolio_id,
            security_id=security_id,
            epoch=0,
            watermark_date=date(2026, 4, 1),
            status="CURRENT",
        )
    )
    session.add(
        PositionHistory(
            portfolio_id=portfolio_id,
            security_id=security_id,
            transaction_id=transaction_id,
            position_date=date(2026, 4, 1),
            epoch=0,
            quantity=quantity,
            cost_basis=Decimal("1000") if quantity > 0 else Decimal("0"),
            cost_basis_local=Decimal("1000") if quantity > 0 else Decimal("0"),
        )
    )


async def test_direct_pair_query_excludes_inverse_unrelated_and_closed_positions(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio("P-SGD", "SGD"),
            _portfolio("P-USD", "USD"),
            _instrument("USD-BOND", "USD"),
            _instrument("SGD-BOND", "SGD"),
            _transaction("TX-MATCH", "P-SGD", "USD-BOND"),
            _transaction("TX-BASE-SAME", "P-USD", "USD-BOND"),
            _transaction("TX-INVERSE", "P-USD", "SGD-BOND"),
            _transaction("TX-CLOSED", "P-SGD", "USD-BOND"),
        ]
    )
    await async_db_session.flush()
    await _seed_position(
        async_db_session,
        portfolio_id="P-SGD",
        security_id="USD-BOND",
        transaction_id="TX-MATCH",
        quantity=Decimal("10"),
    )
    await _seed_position(
        async_db_session,
        portfolio_id="P-USD",
        security_id="USD-BOND",
        transaction_id="TX-BASE-SAME",
        quantity=Decimal("10"),
    )
    await _seed_position(
        async_db_session,
        portfolio_id="P-USD",
        security_id="SGD-BOND",
        transaction_id="TX-INVERSE",
        quantity=Decimal("10"),
    )
    await async_db_session.flush()
    async_db_session.add(
        PositionHistory(
            portfolio_id="P-SGD",
            security_id="USD-BOND",
            transaction_id="TX-CLOSED",
            position_date=date(2026, 4, 9),
            epoch=0,
            quantity=Decimal("0"),
            cost_basis=Decimal("0"),
            cost_basis_local=Decimal("0"),
        )
    )
    await async_db_session.flush()
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session)

    keys = await repository.find_open_position_keys(
        pair=DirectCurrencyPair("USD", "SGD"),
        effective_date=date(2026, 4, 10),
    )

    assert keys == []


async def test_direct_pair_query_returns_open_matching_position_epoch(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio("P-SGD", "SGD"),
            _instrument("USD-BOND", "USD"),
            _transaction("TX-MATCH", "P-SGD", "USD-BOND"),
        ]
    )
    await async_db_session.flush()
    await _seed_position(
        async_db_session,
        portfolio_id="P-SGD",
        security_id="USD-BOND",
        transaction_id="TX-MATCH",
        quantity=Decimal("10"),
    )
    await async_db_session.flush()
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session)

    keys = await repository.find_open_position_keys(
        pair=DirectCurrencyPair("USD", "SGD"),
        effective_date=date(2026, 4, 10),
    )

    assert [(key.portfolio_id, key.security_id, key.epoch) for key in keys] == [
        ("P-SGD", "USD-BOND", 0)
    ]


async def test_replay_impact_includes_position_first_opened_after_correction(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio("P-SGD", "SGD"),
            _instrument("USD-BOND", "USD"),
            _transaction("TX-LATER", "P-SGD", "USD-BOND"),
        ]
    )
    await async_db_session.flush()
    async_db_session.add(
        PositionState(
            portfolio_id="P-SGD",
            security_id="USD-BOND",
            epoch=0,
            watermark_date=date(2026, 4, 12),
            status="CURRENT",
        )
    )
    async_db_session.add(
        PositionHistory(
            portfolio_id="P-SGD",
            security_id="USD-BOND",
            transaction_id="TX-LATER",
            position_date=date(2026, 4, 12),
            epoch=0,
            quantity=Decimal("10"),
            cost_basis=Decimal("1000"),
            cost_basis_local=Decimal("1000"),
        )
    )
    await async_db_session.flush()
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session)

    keys = await repository.find_affected_position_keys(
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
    )

    assert [(key.portfolio_id, key.security_id, key.epoch) for key in keys] == [
        ("P-SGD", "USD-BOND", 0)
    ]


async def test_durable_replay_coalesces_pair_to_earliest_date_and_latest_lineage(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session)
    pair = DirectCurrencyPair("USD", "SGD")
    await repository.stage_durable_replay(
        correction=FxRateCorrection(
            pair=pair,
            effective_date=date(2026, 4, 10),
            content_hash="sha256:" + ("a" * 64),
            generated_at=datetime(2026, 4, 10, 8, tzinfo=timezone.utc),
        ),
        correlation_id="corr-later-date",
    )
    await repository.stage_durable_replay(
        correction=FxRateCorrection(
            pair=pair,
            effective_date=date(2026, 4, 8),
            content_hash="sha256:" + ("b" * 64),
            generated_at=datetime(2026, 4, 10, 9, tzinfo=timezone.utc),
        ),
        correlation_id="corr-latest-correction",
    )
    await async_db_session.commit()

    jobs = (
        (
            await async_db_session.execute(
                select(ReprocessingJob).where(
                    ReprocessingJob.job_type == "RESET_FX_WATERMARKS",
                    ReprocessingJob.status == "PENDING",
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(jobs) == 1
    assert jobs[0].payload == {
        "from_currency": "USD",
        "to_currency": "SGD",
        "earliest_impacted_date": "2026-04-08",
        "content_hash": "sha256:" + ("b" * 64),
        "generated_at": "2026-04-10T09:00:00+00:00",
    }
    assert jobs[0].correlation_id == "corr-latest-correction"


async def test_concurrent_pair_replays_keep_earliest_date_and_newest_lineage(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    session_factory = async_sessionmaker(
        bind=async_db_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    pair = DirectCurrencyPair("USD", "SGD")
    start = asyncio.Event()

    async def stage(correction: FxRateCorrection, correlation_id: str) -> None:
        await start.wait()
        async with session_factory() as session:
            repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(session)
            await repository.stage_durable_replay(
                correction=correction,
                correlation_id=correlation_id,
            )
            await session.commit()

    newer_lineage = FxRateCorrection(
        pair=pair,
        effective_date=date(2026, 4, 10),
        content_hash="sha256:" + ("b" * 64),
        generated_at=datetime(2026, 4, 10, 10, tzinfo=timezone.utc),
    )
    earlier_effective_date = FxRateCorrection(
        pair=pair,
        effective_date=date(2026, 4, 8),
        content_hash="sha256:" + ("a" * 64),
        generated_at=datetime(2026, 4, 10, 9, tzinfo=timezone.utc),
    )
    tasks = [
        asyncio.create_task(stage(newer_lineage, "corr-newest-lineage")),
        asyncio.create_task(stage(earlier_effective_date, "corr-earliest-date")),
    ]
    start.set()
    await asyncio.gather(*tasks)

    jobs = (
        (
            await async_db_session.execute(
                select(ReprocessingJob).where(
                    ReprocessingJob.job_type == "RESET_FX_WATERMARKS",
                    ReprocessingJob.status == "PENDING",
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(jobs) == 1
    assert jobs[0].payload == {
        "from_currency": "USD",
        "to_currency": "SGD",
        "earliest_impacted_date": "2026-04-08",
        "content_hash": "sha256:" + ("b" * 64),
        "generated_at": "2026-04-10T10:00:00+00:00",
    }
    assert jobs[0].correlation_id == "corr-newest-lineage"


async def test_stale_fx_replay_coalesces_with_newer_pending_pair_job(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    stale_job = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "2026-04-08",
            "content_hash": "sha256:" + ("a" * 64),
            "generated_at": "2026-04-10T08:00:00+00:00",
        },
        status="PROCESSING",
        attempt_count=2,
        correlation_id="corr-stale-earliest",
        updated_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    pending_job = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "2026-04-10",
            "content_hash": "sha256:" + ("b" * 64),
            "generated_at": "2026-04-10T09:00:00+00:00",
        },
        status="PENDING",
        attempt_count=0,
        correlation_id="corr-pending-latest",
    )
    async_db_session.add_all([stale_job, pending_job])
    await async_db_session.commit()

    recovered_count = await ReprocessingJobRepository(async_db_session).find_and_reset_stale_jobs(
        timeout_minutes=15, max_attempts=3
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    jobs = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_FX_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )
    assert recovered_count == 1
    assert len(jobs) == 2
    assert jobs[0].status == "COMPLETE"
    assert jobs[0].failure_reason == "Coalesced into pending FX replay during stale recovery"
    assert jobs[1].status == "PENDING"
    assert jobs[1].attempt_count == 2
    assert jobs[1].payload == {
        "from_currency": "USD",
        "to_currency": "SGD",
        "earliest_impacted_date": "2026-04-08",
        "content_hash": "sha256:" + ("b" * 64),
        "generated_at": "2026-04-10T09:00:00+00:00",
    }
    assert jobs[1].correlation_id == "corr-pending-latest"


async def test_malformed_fx_replay_is_claimed_and_failed_supportably(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    malformed_job = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "not-a-date",
        },
        status="PENDING",
        correlation_id="corr-malformed-fx-replay",
    )
    async_db_session.add(malformed_job)
    await async_db_session.commit()
    job_id = malformed_job.id

    revaluation = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session)
    claimed = await revaluation.claim_pending_jobs(batch_size=1)

    assert len(claimed) == 1
    assert isinstance(claimed[0], RejectedFxRevaluationJob)
    assert claimed[0].job_id == job_id
    assert "Invalid isoformat string" in claimed[0].rejection_reason

    await FxRevaluationJobProcessor().process(
        job=claimed[0],
        jobs=ReprocessingJobRepository(async_db_session),
        watermarks=PositionStateRepository(async_db_session),
        revaluation=revaluation,
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    failed_job = await async_db_session.get(ReprocessingJob, job_id)
    assert failed_job is not None
    assert failed_job.status == "FAILED"
    assert failed_job.failure_reason is not None
    assert "invalid_fx_revaluation_job_payload" in failed_job.failure_reason


@pytest.mark.parametrize(
    "malformed_payload",
    [
        {
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "not-a-date",
            "content_hash": "sha256:malformed-date",
            "generated_at": "2026-04-10T08:00:00+00:00",
        },
        {
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "2026-04-10",
            "content_hash": "sha256:malformed-timestamp",
            "generated_at": "not-a-timestamp",
        },
    ],
)
async def test_valid_fx_replay_quarantines_malformed_pending_pair_before_upsert(
    clean_db,
    async_db_session: AsyncSession,
    malformed_payload: dict[str, str],
) -> None:
    malformed_job = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload=malformed_payload,
        status="PENDING",
        correlation_id="corr-malformed-pending-pair",
    )
    async_db_session.add(malformed_job)
    await async_db_session.commit()
    malformed_job_id = malformed_job.id

    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session)
    await repository.stage_durable_replay(
        correction=FxRateCorrection(
            pair=DirectCurrencyPair("USD", "SGD"),
            effective_date=date(2026, 4, 8),
            content_hash="sha256:" + ("c" * 64),
            generated_at=datetime(2026, 4, 10, 9, tzinfo=timezone.utc),
        ),
        correlation_id="corr-valid-replacement",
    )
    await async_db_session.commit()
    async_db_session.expire_all()

    jobs = (
        (
            await async_db_session.execute(
                select(ReprocessingJob)
                .where(ReprocessingJob.job_type == "RESET_FX_WATERMARKS")
                .order_by(ReprocessingJob.id.asc())
            )
        )
        .scalars()
        .all()
    )

    assert len(jobs) == 2
    assert jobs[0].id == malformed_job_id
    assert jobs[0].status == "FAILED"
    assert jobs[0].failure_reason == (
        "invalid_fx_revaluation_job_payload: superseded during valid replay staging"
    )
    assert jobs[1].status == "PENDING"
    assert jobs[1].payload == {
        "from_currency": "USD",
        "to_currency": "SGD",
        "earliest_impacted_date": "2026-04-08",
        "content_hash": "sha256:" + ("c" * 64),
        "generated_at": "2026-04-10T09:00:00+00:00",
    }
    assert jobs[1].correlation_id == "corr-valid-replacement"


async def test_claimed_fx_job_resets_exact_affected_watermark_and_completes(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    async_db_session.add_all(
        [
            _portfolio("P-SGD", "SGD"),
            _instrument("USD-BOND", "USD"),
            _transaction("TX-MATCH", "P-SGD", "USD-BOND"),
        ]
    )
    await async_db_session.flush()
    await _seed_position(
        async_db_session,
        portfolio_id="P-SGD",
        security_id="USD-BOND",
        transaction_id="TX-MATCH",
        quantity=Decimal("10"),
    )
    state = await async_db_session.get(PositionState, ("P-SGD", "USD-BOND"))
    assert state is not None
    state.watermark_date = date(2026, 4, 15)
    claimed_job = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "2026-04-10",
            "content_hash": "sha256:" + ("a" * 64),
            "generated_at": "2026-04-10T08:00:00+00:00",
        },
        status="PROCESSING",
        correlation_id="corr-fx-worker",
    )
    async_db_session.add(claimed_job)
    await async_db_session.flush()

    claimed = ClaimedFxRevaluationJob(
        job_id=claimed_job.id,
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
        correlation_id="corr-fx-worker",
    )

    await FxRevaluationJobProcessor().process(
        job=claimed,
        jobs=ReprocessingJobRepository(async_db_session),
        watermarks=PositionStateRepository(async_db_session),
        revaluation=fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session),
    )
    await async_db_session.commit()

    refreshed_state = await async_db_session.get(PositionState, ("P-SGD", "USD-BOND"))
    refreshed_job = await async_db_session.get(ReprocessingJob, claimed_job.id)
    assert refreshed_state is not None
    assert refreshed_state.watermark_date == date(2026, 4, 9)
    assert refreshed_state.status == "REPROCESSING"
    assert refreshed_job is not None
    assert refreshed_job.status == "COMPLETE"
