"""PostgreSQL integration tests for direct-pair FX correction revaluation."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from portfolio_common.database_models import (
    DailyPositionSnapshot,
    FxRate,
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
    ReprocessingJob,
    Transaction,
)
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.schema import AddConstraint, DropConstraint

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

_ACTIVE_PAYLOAD_CONSTRAINT = next(
    constraint
    for constraint in ReprocessingJob.__table__.constraints
    if constraint.name == "ck_reprocessing_jobs_active_payload_valid"
)


@asynccontextmanager
async def _predecessor_active_payload_schema(
    session: AsyncSession,
    *,
    correlation_ids: tuple[str, ...],
) -> AsyncIterator[None]:
    """Build legacy queue state while restoring the current schema even on failure."""

    await session.execute(DropConstraint(_ACTIVE_PAYLOAD_CONSTRAINT))
    await session.commit()
    try:
        yield
    finally:
        await session.rollback()
        await session.execute(
            delete(ReprocessingJob).where(ReprocessingJob.correlation_id.in_(correlation_ids))
        )
        await session.execute(AddConstraint(_ACTIVE_PAYLOAD_CONSTRAINT))
        await session.commit()


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
    updated_at: datetime | None = None,
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
    position_history = PositionHistory(
        portfolio_id=portfolio_id,
        security_id=security_id,
        transaction_id=transaction_id,
        position_date=date(2026, 4, 1),
        epoch=0,
        quantity=quantity,
        cost_basis=Decimal("1000") if quantity > 0 else Decimal("0"),
        cost_basis_local=Decimal("1000") if quantity > 0 else Decimal("0"),
    )
    if updated_at is not None:
        position_history.created_at = updated_at
        position_history.updated_at = updated_at
    session.add(position_history)


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


@pytest.mark.parametrize("position_quantity", [Decimal("10"), Decimal("-10")])
async def test_direct_pair_query_returns_nonzero_matching_position_epoch(
    clean_db,
    async_db_session: AsyncSession,
    position_quantity: Decimal,
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
        quantity=position_quantity,
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


@pytest.mark.parametrize("source_is_newer", [True, False])
async def test_immediate_fx_revaluation_uses_latest_derived_authority_freshness(
    clean_db,
    async_db_session: AsyncSession,
    source_is_newer: bool,
) -> None:
    source_updated_at = datetime(2026, 4, 10, 8, tzinfo=timezone.utc)
    position_updated_at = source_updated_at + timedelta(seconds=-1 if source_is_newer else 1)
    rate = FxRate(
        from_currency="USD",
        to_currency="SGD",
        rate_date=date(2026, 4, 10),
        rate=Decimal("1.35"),
        created_at=source_updated_at,
        updated_at=source_updated_at,
    )
    async_db_session.add_all(
        [
            _portfolio("P-SGD", "SGD"),
            _instrument("USD-BOND", "USD"),
            _transaction("TX-MATCH", "P-SGD", "USD-BOND"),
            rate,
        ]
    )
    await async_db_session.flush()
    await _seed_position(
        async_db_session,
        portfolio_id="P-SGD",
        security_id="USD-BOND",
        transaction_id="TX-MATCH",
        quantity=Decimal("10"),
        updated_at=position_updated_at,
    )
    await async_db_session.commit()
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session)

    keys = await repository.find_position_keys_requiring_revaluation(
        pair=DirectCurrencyPair("USD", "SGD"),
        effective_date=date(2026, 4, 10),
    )

    assert [(key.portfolio_id, key.security_id, key.epoch) for key in keys] == (
        [("P-SGD", "USD-BOND", 0)] if source_is_newer else []
    )

    async_db_session.add(
        DailyPositionSnapshot(
            portfolio_id="P-SGD",
            security_id="USD-BOND",
            date=date(2026, 4, 10),
            epoch=0,
            quantity=Decimal("10"),
            cost_basis=Decimal("1000"),
            updated_at=max(source_updated_at, position_updated_at) + timedelta(seconds=1),
        )
    )
    await async_db_session.commit()

    assert (
        await repository.find_position_keys_requiring_revaluation(
            pair=DirectCurrencyPair("USD", "SGD"),
            effective_date=date(2026, 4, 10),
        )
        == []
    )

    rate.updated_at = max(source_updated_at, position_updated_at) + timedelta(seconds=2)
    rate.rate = Decimal("1.36")
    await async_db_session.commit()

    keys = await repository.find_position_keys_requiring_revaluation(
        pair=DirectCurrencyPair("USD", "SGD"),
        effective_date=date(2026, 4, 10),
    )

    assert [(key.portfolio_id, key.security_id, key.epoch) for key in keys] == [
        ("P-SGD", "USD-BOND", 0)
    ]


@pytest.mark.parametrize("position_quantity", [Decimal("10"), Decimal("-10")])
async def test_replay_impact_includes_nonzero_position_first_opened_after_correction(
    clean_db,
    async_db_session: AsyncSession,
    position_quantity: Decimal,
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
            quantity=position_quantity,
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


@pytest.mark.lifecycle
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
        lease_owner="stale-fx-worker",
        lease_token="3" * 32,
        lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=30),
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
        max_attempts=3
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


@pytest.mark.lifecycle
async def test_predecessor_malformed_fx_replay_is_claimed_and_failed_supportably(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    correlation_id = "corr-malformed-fx-replay"
    async with _predecessor_active_payload_schema(
        async_db_session,
        correlation_ids=(correlation_id,),
    ):
        malformed_job = ReprocessingJob(
            job_type="RESET_FX_WATERMARKS",
            payload={
                "from_currency": "USD",
                "to_currency": "SGD",
                "earliest_impacted_date": "not-a-date",
            },
            status="PENDING",
            correlation_id=correlation_id,
        )
        async_db_session.add(malformed_job)
        await async_db_session.commit()
        job_id = malformed_job.id

        revaluation = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(async_db_session)
        claimed = await revaluation.claim_pending_jobs(batch_size=1)
        await async_db_session.commit()

        assert len(claimed) == 1
        assert isinstance(claimed[0], RejectedFxRevaluationJob)
        assert claimed[0].job_id == job_id
        assert "Invalid isoformat string" in claimed[0].rejection_reason

        processor = FxRevaluationJobProcessor()
        with pytest.raises(ValueError, match="invalid_fx_revaluation_job_payload"):
            await processor.process(
                job=claimed[0],
                jobs=ReprocessingJobRepository(async_db_session),
                watermarks=PositionStateRepository(async_db_session),
                revaluation=revaluation,
            )
        await processor.mark_failed(
            job=claimed[0],
            jobs=ReprocessingJobRepository(async_db_session),
            exc=ValueError(claimed[0].rejection_reason),
        )
        await async_db_session.commit()
        async_db_session.expire_all()

        failed_job = await async_db_session.get(ReprocessingJob, job_id)
        assert failed_job is not None
        assert failed_job.status == "FAILED"
        assert failed_job.failure_reason is not None
        assert "invalid_fx_revaluation_job_payload" in failed_job.failure_reason


@pytest.mark.lifecycle
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
async def test_predecessor_malformed_pending_pair_is_quarantined_before_upsert(
    clean_db,
    async_db_session: AsyncSession,
    malformed_payload: dict[str, str],
) -> None:
    malformed_correlation_id = "corr-malformed-pending-pair"
    replacement_correlation_id = "corr-valid-replacement"
    async with _predecessor_active_payload_schema(
        async_db_session,
        correlation_ids=(malformed_correlation_id, replacement_correlation_id),
    ):
        malformed_job = ReprocessingJob(
            job_type="RESET_FX_WATERMARKS",
            payload=malformed_payload,
            status="PENDING",
            correlation_id=malformed_correlation_id,
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
            correlation_id=replacement_correlation_id,
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
        assert jobs[1].correlation_id == replacement_correlation_id


@pytest.mark.lifecycle
@pytest.mark.parametrize(
    "malformed_payload",
    [
        {
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "not-a-date",
        },
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
async def test_malformed_fx_replay_is_rejected_before_active_queue_entry(
    clean_db,
    async_db_session: AsyncSession,
    malformed_payload: dict[str, str],
) -> None:
    malformed_job = ReprocessingJob(
        job_type="RESET_FX_WATERMARKS",
        payload=malformed_payload,
        status="PENDING",
        correlation_id="corr-malformed-active-replay",
    )
    async_db_session.add(malformed_job)
    with pytest.raises(IntegrityError, match="ck_reprocessing_jobs_active_payload_valid"):
        await async_db_session.commit()
    await async_db_session.rollback()

    persisted = (
        await async_db_session.execute(
            select(ReprocessingJob).where(
                ReprocessingJob.correlation_id == "corr-malformed-active-replay"
            )
        )
    ).scalar_one_or_none()
    assert persisted is None


@pytest.mark.lifecycle
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
        lease_owner="fx-integration-worker",
        lease_token="c" * 32,
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    async_db_session.add(claimed_job)
    await async_db_session.flush()

    claimed = ClaimedFxRevaluationJob(
        job_id=claimed_job.id,
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
        lease_token="c" * 32,
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
