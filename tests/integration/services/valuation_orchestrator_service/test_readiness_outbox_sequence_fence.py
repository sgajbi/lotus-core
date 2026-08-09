"""PostgreSQL proofs for exact-scope readiness sequence fencing."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from portfolio_common.database_models import OutboxEvent, PortfolioValuationJob
from portfolio_common.valuation_job_repository import ValuationJobRepository
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position.history_repository import (  # noqa: E501
    SqlAlchemyPositionHistoryRepository,
    _position_history_replay_lock_key,
)
from tests.test_support.postgres_query_plan import plan_index_names, plan_node_types

pytestmark = pytest.mark.asyncio

PORTFOLIO_ID = "P-READINESS-SEQUENCE"
SECURITY_ID = "S-READINESS-SEQUENCE"
VALUATION_DATE = date(2026, 8, 9)


def _aggregate_id(*, valuation_date: date = VALUATION_DATE, epoch: int = 0) -> str:
    return f"{PORTFOLIO_ID}:{SECURITY_ID}:{valuation_date.isoformat()}:{epoch}"


async def _stage_readiness(
    session: AsyncSession,
    *,
    valuation_date: date = VALUATION_DATE,
    epoch: int = 0,
) -> OutboxEvent:
    event = OutboxEvent(
        aggregate_type="ValuationReadiness",
        aggregate_id=_aggregate_id(valuation_date=valuation_date, epoch=epoch),
        partition_key=f"{PORTFOLIO_ID}|{SECURITY_ID}",
        event_type="PortfolioDayReadyForValuation",
        payload={
            "portfolio_id": PORTFOLIO_ID,
            "security_id": SECURITY_ID,
            "valuation_date": valuation_date.isoformat(),
            "epoch": epoch,
        },
        topic="portfolio_security_day.valuation.ready",
        status="PENDING",
    )
    session.add(event)
    await session.flush()
    return event


async def _seed_pending_job(session: AsyncSession) -> None:
    session.add(
        PortfolioValuationJob(
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            valuation_date=VALUATION_DATE,
            epoch=0,
            status="PENDING",
            correlation_id="scheduler-backfill",
        )
    )
    await session.commit()


async def _read_job(session: AsyncSession) -> PortfolioValuationJob:
    return (
        await session.execute(
            select(PortfolioValuationJob).where(
                PortfolioValuationJob.portfolio_id == PORTFOLIO_ID,
                PortfolioValuationJob.security_id == SECURITY_ID,
                PortfolioValuationJob.valuation_date == VALUATION_DATE,
                PortfolioValuationJob.epoch == 0,
            )
        )
    ).scalar_one()


async def _apply_readiness(session: AsyncSession, *, outbox_id: int) -> None:
    await ValuationJobRepository(session).upsert_position_readiness_job(
        portfolio_id=PORTFOLIO_ID,
        security_id=SECURITY_ID,
        valuation_date=VALUATION_DATE,
        epoch=0,
        correlation_id="readiness",
        source_mutation_id=f"readiness:{outbox_id}",
        readiness_outbox_id=outbox_id,
    )
    await session.commit()


async def test_claimed_sequence_suppresses_late_delivery_for_covered_readiness(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    readiness = await _stage_readiness(async_db_session)
    readiness_id = readiness.id
    await async_db_session.commit()
    await _seed_pending_job(async_db_session)

    claimed = await ValuationRepository(async_db_session).find_and_claim_eligible_jobs(1)
    await async_db_session.commit()
    assert claimed[0].claimed_readiness_outbox_id == readiness_id

    await _apply_readiness(async_db_session, outbox_id=readiness_id)
    async_db_session.expire_all()
    job = await _read_job(async_db_session)
    assert job.status == "PROCESSING"
    assert job.requeue_requested is False
    assert job.correlation_id == "scheduler-backfill"


async def test_later_exact_scope_readiness_requeues_processing_job(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    first = await _stage_readiness(async_db_session)
    first_id = first.id
    await async_db_session.commit()
    await _seed_pending_job(async_db_session)
    await ValuationRepository(async_db_session).find_and_claim_eligible_jobs(1)
    await async_db_session.commit()

    later = await _stage_readiness(async_db_session)
    later_id = later.id
    await async_db_session.commit()
    await _apply_readiness(async_db_session, outbox_id=later_id)
    async_db_session.expire_all()

    job = await _read_job(async_db_session)
    assert later_id > first_id
    assert job.status == "PROCESSING"
    assert job.requeue_requested is True
    assert job.claimed_readiness_outbox_id == first_id


async def test_uncommitted_readiness_is_not_fabricated_as_claimed(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    first = await _stage_readiness(async_db_session)
    first_id = first.id
    await async_db_session.commit()
    await _seed_pending_job(async_db_session)
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async with session_factory() as source_session:
        later = await _stage_readiness(source_session)
        later_id = later.id
        async with session_factory() as claim_session:
            claimed = await ValuationRepository(claim_session).find_and_claim_eligible_jobs(1)
            await claim_session.commit()
            assert claimed[0].claimed_readiness_outbox_id == first_id
        await source_session.commit()

    async with session_factory() as readiness_session:
        await _apply_readiness(readiness_session, outbox_id=later_id)

    async_db_session.expire_all()
    job = await _read_job(async_db_session)
    assert job.status == "PROCESSING"
    assert job.requeue_requested is True


async def test_other_date_sequence_cannot_rearm_exact_scope_job(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    covered = await _stage_readiness(async_db_session)
    covered_id = covered.id
    await async_db_session.commit()
    await _seed_pending_job(async_db_session)
    await ValuationRepository(async_db_session).find_and_claim_eligible_jobs(1)
    await async_db_session.commit()

    other_date = await _stage_readiness(
        async_db_session,
        valuation_date=date(2026, 8, 10),
    )
    other_date_id = other_date.id
    await async_db_session.commit()
    assert other_date_id > covered_id

    await _apply_readiness(async_db_session, outbox_id=covered_id)
    async_db_session.expire_all()
    job = await _read_job(async_db_session)
    assert job.status == "PROCESSING"
    assert job.requeue_requested is False


async def test_new_sequence_rearms_completed_job_and_redelivery_is_idempotent(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    covered = await _stage_readiness(async_db_session)
    covered_id = covered.id
    await async_db_session.commit()
    await _seed_pending_job(async_db_session)
    job = await _read_job(async_db_session)
    job.status = "COMPLETE"
    job.claimed_readiness_outbox_id = covered_id
    await async_db_session.commit()

    later = await _stage_readiness(async_db_session)
    later_id = later.id
    await async_db_session.commit()
    await _apply_readiness(async_db_session, outbox_id=later_id)
    await _apply_readiness(async_db_session, outbox_id=later_id)
    async_db_session.expire_all()

    job = await _read_job(async_db_session)
    assert job.status == "PENDING"
    assert job.requeue_requested is False
    assert job.source_correction_id == f"readiness:{later_id}"


async def test_claimed_sequence_never_regresses_when_outbox_history_is_absent(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    await _seed_pending_job(async_db_session)
    job = await _read_job(async_db_session)
    job.claimed_readiness_outbox_id = 900
    await async_db_session.commit()

    claimed = await ValuationRepository(async_db_session).find_and_claim_eligible_jobs(1)
    await async_db_session.commit()

    assert claimed[0].claimed_readiness_outbox_id == 900


async def test_unverified_high_transport_sequence_cannot_poison_claimed_authority(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    covered = await _stage_readiness(async_db_session)
    covered_id = covered.id
    await async_db_session.commit()
    await _seed_pending_job(async_db_session)
    await ValuationRepository(async_db_session).find_and_claim_eligible_jobs(1)
    job = await _read_job(async_db_session)
    job.status = "COMPLETE"
    await async_db_session.commit()

    unverified_high_id = covered_id + 1_000_000
    await _apply_readiness(async_db_session, outbox_id=unverified_high_id)
    claimed = await ValuationRepository(async_db_session).find_and_claim_eligible_jobs(1)
    assert claimed[0].claimed_readiness_outbox_id == covered_id
    claimed_job = await _read_job(async_db_session)
    claimed_job.status = "COMPLETE"
    await async_db_session.commit()

    legitimate = await _stage_readiness(async_db_session)
    legitimate_id = legitimate.id
    await async_db_session.commit()
    assert covered_id < legitimate_id < unverified_high_id
    await _apply_readiness(async_db_session, outbox_id=legitimate_id)

    async_db_session.expire_all()
    job = await _read_job(async_db_session)
    assert job.status == "PENDING"
    assert job.claimed_readiness_outbox_id == covered_id


async def test_claim_scope_is_stable_under_non_iso_postgres_datestyle(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    readiness = await _stage_readiness(async_db_session)
    readiness_id = readiness.id
    await async_db_session.commit()
    await _seed_pending_job(async_db_session)

    await async_db_session.execute(text("SET LOCAL DateStyle = 'SQL, DMY'"))
    claimed = await ValuationRepository(async_db_session).find_and_claim_eligible_jobs(1)
    await async_db_session.commit()

    assert claimed[0].claimed_readiness_outbox_id == readiness_id


async def test_exact_scope_readiness_lookup_uses_aggregate_index_at_fan_in_scale(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    # Insert the target before the fan-in noise so a lucky backward primary-key scan
    # cannot satisfy the lookup cheaply; the scope index must do the selective work.
    await _stage_readiness(async_db_session)
    await async_db_session.execute(
        text(
            """
            INSERT INTO outbox_events (
                aggregate_type,
                aggregate_id,
                partition_key,
                event_type,
                payload,
                topic,
                status,
                retry_count,
                created_at
            )
            SELECT
                'ValuationReadiness',
                'P-READINESS-NOISE-' || series::text
                    || chr(58) || 'S-READINESS-NOISE'
                    || chr(58) || '2026-08-09' || chr(58) || '0',
                'P-READINESS-NOISE-' || series::text || '|S-READINESS-NOISE',
                'PortfolioDayReadyForValuation',
                json_build_object(
                    'portfolio_id', 'P-READINESS-NOISE-' || series::text,
                    'security_id', 'S-READINESS-NOISE',
                    'valuation_date', '2026-08-09',
                    'epoch', 0
                ),
                'portfolio_security_day.valuation.ready',
                'PENDING',
                0,
                now()
            FROM generate_series(1, 10000) AS series
            """
        )
    )
    await async_db_session.commit()
    await async_db_session.execute(text("ANALYZE outbox_events"))

    plan = await async_db_session.scalar(
        text(
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT coalesce(max(id), 0)
            FROM outbox_events
            WHERE aggregate_type = 'ValuationReadiness'
              AND event_type = 'PortfolioDayReadyForValuation'
              AND aggregate_id = :aggregate_id
              AND payload ->> 'portfolio_id' = :portfolio_id
              AND payload ->> 'security_id' = :security_id
              AND payload ->> 'valuation_date' = :valuation_date
              AND CAST(payload ->> 'epoch' AS INTEGER) = :epoch
            """
        ),
        {
            "aggregate_id": _aggregate_id(),
            "portfolio_id": PORTFOLIO_ID,
            "security_id": SECURITY_ID,
            "valuation_date": VALUATION_DATE.isoformat(),
            "epoch": 0,
        },
    )

    assert "ix_outbox_events_aggregate_id" in plan_index_names(plan)
    assert "Seq Scan" not in plan_node_types(plan)


async def test_payload_identity_rejects_colon_delimited_aggregate_collision(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    colliding_aggregate = f"A:B:C:{VALUATION_DATE.isoformat()}:0"
    async_db_session.add_all(
        [
            OutboxEvent(
                aggregate_type="ValuationReadiness",
                aggregate_id=colliding_aggregate,
                partition_key="A|B:C",
                event_type="PortfolioDayReadyForValuation",
                payload={
                    "portfolio_id": "A",
                    "security_id": "B:C",
                    "valuation_date": VALUATION_DATE.isoformat(),
                    "epoch": 0,
                },
                topic="portfolio_security_day.valuation.ready",
                status="PENDING",
            ),
            PortfolioValuationJob(
                portfolio_id="A:B",
                security_id="C",
                valuation_date=VALUATION_DATE,
                epoch=0,
                status="PENDING",
            ),
        ]
    )
    await async_db_session.commit()

    claimed = await ValuationRepository(async_db_session).find_and_claim_eligible_jobs(1)
    await async_db_session.commit()

    assert claimed[0].claimed_readiness_outbox_id == 0


async def test_rolled_back_sequence_gap_is_not_claimed(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    async with session_factory() as rolled_back_session:
        rolled_back = await _stage_readiness(rolled_back_session)
        rolled_back_id = rolled_back.id
        await rolled_back_session.rollback()

    committed = await _stage_readiness(async_db_session)
    committed_id = committed.id
    await async_db_session.commit()
    await _seed_pending_job(async_db_session)

    claimed = await ValuationRepository(async_db_session).find_and_claim_eligible_jobs(1)
    await async_db_session.commit()

    assert committed_id > rolled_back_id
    assert claimed[0].claimed_readiness_outbox_id == committed_id


async def test_same_position_lock_serializes_readiness_sequence_allocation(
    async_db_session: AsyncSession,
    clean_db,
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    lock_key = _position_history_replay_lock_key(PORTFOLIO_ID, SECURITY_ID, 0)

    async with session_factory() as first_session:
        await SqlAlchemyPositionHistoryRepository(first_session).acquire_replay_lock(
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            epoch=0,
        )
        first = await _stage_readiness(first_session)
        first_id = first.id
        contention_proven = asyncio.Event()

        async def stage_after_same_position_lock() -> int:
            async with session_factory() as second_session:
                acquired_early = await second_session.scalar(
                    text("SELECT pg_try_advisory_xact_lock(:lock_key)").bindparams(
                        lock_key=lock_key
                    )
                )
                assert acquired_early is False
                contention_proven.set()
                await SqlAlchemyPositionHistoryRepository(second_session).acquire_replay_lock(
                    portfolio_id=PORTFOLIO_ID,
                    security_id=SECURITY_ID,
                    epoch=0,
                )
                second = await _stage_readiness(second_session)
                second_id = second.id
                await second_session.commit()
                return second_id

        second_task = asyncio.create_task(stage_after_same_position_lock())
        await asyncio.wait_for(contention_proven.wait(), timeout=5)
        assert second_task.done() is False
        await first_session.commit()
        second_id = await asyncio.wait_for(second_task, timeout=5)

    assert second_id > first_id
