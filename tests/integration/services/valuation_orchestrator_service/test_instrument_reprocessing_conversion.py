"""PostgreSQL proofs for lossless instrument-trigger conversion."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from portfolio_common.database_models import (
    InstrumentReprocessingState,
    ReprocessingJob,
)
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.valuation_orchestrator_service.app.core import (
    instrument_reprocessing_coordinator,
)
from src.services.valuation_orchestrator_service.app.repositories import (
    instrument_reprocessing_conversion_repository as conversion_repository,
)
from src.services.valuation_orchestrator_service.app.repositories import (
    instrument_reprocessing_state_repository,
)

pytestmark = pytest.mark.asyncio


async def _convert_pending_triggers(
    session: AsyncSession,
) -> conversion_repository.InstrumentTriggerConversionResult:
    coordinator = instrument_reprocessing_coordinator.InstrumentReprocessingCoordinator(
        batch_size=25
    )
    return await coordinator.process_instrument_level_triggers(
        conversion_repository=conversion_repository.InstrumentReprocessingConversionRepository(
            session
        ),
    )


async def _wait_for_backend_lock(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    backend_pid: int,
    expected_wait_event: str | None = None,
) -> None:
    for _ in range(100):
        async with session_factory() as observer:
            wait_state = (
                await observer.execute(
                    text(
                        """
                        SELECT wait_event_type, wait_event
                        FROM pg_stat_activity
                        WHERE pid = :backend_pid
                        """
                    ),
                    {"backend_pid": backend_pid},
                )
            ).one_or_none()
        if (
            wait_state is not None
            and wait_state.wait_event_type == "Lock"
            and (expected_wait_event is None or wait_state.wait_event == expected_wait_event)
        ):
            return
        await asyncio.sleep(0.02)
    expected = "a lock" if expected_wait_event is None else f"a {expected_wait_event} lock"
    raise AssertionError(f"backend {backend_pid} did not enter {expected} wait")


async def _await_task_with_cleanup(task: asyncio.Task[None], *, timeout: float = 5) -> None:
    """Bound a spawned race task and always reap it after cancellation."""
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except TimeoutError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


async def _reap_task_if_needed(task: asyncio.Task[None]) -> None:
    """Finish an active task or consume a completed task's terminal exception."""
    if not task.done():
        await _await_task_with_cleanup(task)
    elif not task.cancelled():
        task.exception()


async def test_conversion_preserves_earlier_update_arriving_while_trigger_is_locked(
    clean_db, async_db_session: AsyncSession
) -> None:
    async_db_session.add(
        InstrumentReprocessingState(
            security_id="S-CONVERSION-RACE",
            earliest_impacted_date=date(2025, 8, 10),
            correlation_id="corr-later",
        )
    )
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    trigger_claimed = asyncio.Event()
    release_conversion = asyncio.Event()

    class PausingJobRepository(ReprocessingJobRepository):
        async def stage_reset_watermarks_job(self, *args, **kwargs):
            trigger_claimed.set()
            await release_conversion.wait()
            return await super().stage_reset_watermarks_job(*args, **kwargs)

    async def convert_later_trigger() -> None:
        async with session_factory() as session, session.begin():
            coordinator = instrument_reprocessing_coordinator.InstrumentReprocessingCoordinator(
                batch_size=1
            )
            repository = conversion_repository.InstrumentReprocessingConversionRepository(session)
            repository._job_repository = PausingJobRepository(session)
            await coordinator.process_instrument_level_triggers(
                conversion_repository=repository,
            )

    conversion_task = asyncio.create_task(convert_later_trigger())
    updater_task: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(trigger_claimed.wait(), timeout=5)

        # Hold the updater's connection explicitly so its backend can be observed while blocked.
        async with session_factory() as updater_session:
            updater_pid = int(await updater_session.scalar(text("SELECT pg_backend_pid()")))
            updater_repository = (
                instrument_reprocessing_state_repository.InstrumentReprocessingStateRepository(
                    updater_session
                )
            )
            updater_task = asyncio.create_task(
                updater_repository.upsert_state(
                    "S-CONVERSION-RACE",
                    date(2025, 8, 5),
                    correlation_id="corr-earlier",
                )
            )
            await _wait_for_backend_lock(
                session_factory=session_factory,
                backend_pid=updater_pid,
            )
            release_conversion.set()
            await _await_task_with_cleanup(conversion_task)
            await _await_task_with_cleanup(updater_task)
            await updater_session.commit()
    finally:
        release_conversion.set()
        await _reap_task_if_needed(conversion_task)
        if updater_task is not None:
            await _reap_task_if_needed(updater_task)

    async with session_factory() as conversion_session, conversion_session.begin():
        await _convert_pending_triggers(conversion_session)

    async with session_factory() as verification_session:
        triggers = list(
            (
                await verification_session.scalars(
                    select(InstrumentReprocessingState).where(
                        InstrumentReprocessingState.security_id == "S-CONVERSION-RACE"
                    )
                )
            ).all()
        )
        jobs = list(
            (
                await verification_session.scalars(
                    select(ReprocessingJob).where(
                        ReprocessingJob.job_type == "RESET_WATERMARKS",
                        ReprocessingJob.payload["security_id"].as_string() == "S-CONVERSION-RACE",
                    )
                )
            ).all()
        )

    assert triggers == []
    assert len(jobs) == 1
    assert jobs[0].status == "PENDING"
    assert jobs[0].payload["earliest_impacted_date"] == "2025-08-05"
    assert jobs[0].correlation_id == "corr-earlier"


async def test_stale_recovery_and_trigger_conversion_share_global_identity_lock_order(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    now = datetime.now(timezone.utc)
    async_db_session.add_all(
        [
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": "BBBB", "earliest_impacted_date": "2025-08-10"},
                status="PROCESSING",
                attempt_count=1,
                lease_owner="stale-b",
                lease_token="b" * 32,
                lease_expires_at=now - timedelta(minutes=2),
            ),
            ReprocessingJob(
                job_type="RESET_WATERMARKS",
                payload={"security_id": "A", "earliest_impacted_date": "2025-08-09"},
                status="PROCESSING",
                attempt_count=1,
                lease_owner="stale-a",
                lease_token="a" * 32,
                lease_expires_at=now - timedelta(minutes=1),
            ),
            InstrumentReprocessingState(
                security_id="A",
                earliest_impacted_date=date(2025, 8, 5),
                correlation_id="corr-trigger-a",
            ),
            InstrumentReprocessingState(
                security_id="BBBB",
                earliest_impacted_date=date(2025, 8, 6),
                correlation_id="corr-trigger-b",
            ),
        ]
    )
    await async_db_session.commit()
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    stale_locks_acquired = asyncio.Event()
    release_stale_recovery = asyncio.Event()
    conversion_pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    class PausingStaleRecoveryRepository(ReprocessingJobRepository):
        async def _lock_effective_dated_replay_identities(self, identity_keys):
            await super()._lock_effective_dated_replay_identities(identity_keys)
            stale_locks_acquired.set()
            await release_stale_recovery.wait()

    async def recover_stale_jobs() -> int:
        async with session_factory() as session, session.begin():
            return await PausingStaleRecoveryRepository(session).find_and_reset_stale_jobs(
                max_attempts=3
            )

    async def convert_triggers() -> conversion_repository.InstrumentTriggerConversionResult:
        async with session_factory() as session, session.begin():
            conversion_pid_ready.set_result(
                int(await session.scalar(text("SELECT pg_backend_pid()")))
            )
            return await _convert_pending_triggers(session)

    stale_task = asyncio.create_task(recover_stale_jobs())
    conversion_task = None
    try:
        await asyncio.wait_for(stale_locks_acquired.wait(), timeout=5)
        conversion_task = asyncio.create_task(convert_triggers())
        conversion_pid = await asyncio.wait_for(conversion_pid_ready, timeout=5)
        await _wait_for_backend_lock(
            session_factory=session_factory,
            backend_pid=conversion_pid,
            expected_wait_event="advisory",
        )
        release_stale_recovery.set()
        assert await asyncio.wait_for(stale_task, timeout=5) == 2
        result = await asyncio.wait_for(conversion_task, timeout=5)
    finally:
        release_stale_recovery.set()
        for task in (stale_task, conversion_task):
            if task is not None and not task.done():
                task.cancel()
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)

    assert result == conversion_repository.InstrumentTriggerConversionResult(
        claimed_count=2,
        created_count=0,
        coalesced_pending_count=2,
    )
    async_db_session.expire_all()
    jobs = list(
        (
            await async_db_session.scalars(
                select(ReprocessingJob).order_by(ReprocessingJob.id.asc())
            )
        ).all()
    )
    assert [job.status for job in jobs] == ["COMPLETE", "COMPLETE", "PENDING", "PENDING"]
    pending_by_security = {
        job.payload["security_id"]: job for job in jobs if job.status == "PENDING"
    }
    assert pending_by_security["A"].payload["earliest_impacted_date"] == "2025-08-05"
    assert pending_by_security["BBBB"].payload["earliest_impacted_date"] == "2025-08-06"


async def test_conversion_failure_rolls_trigger_deletion_back(
    clean_db, async_db_session: AsyncSession
) -> None:
    async_db_session.add(
        InstrumentReprocessingState(
            security_id="S-CONVERSION-ROLLBACK",
            earliest_impacted_date=date(2025, 8, 7),
            correlation_id="corr-rollback",
        )
    )
    await async_db_session.commit()

    class FailingJobRepository(ReprocessingJobRepository):
        async def stage_reset_watermarks_job(self, *args, **kwargs):
            raise RuntimeError("injected reset-watermarks staging failure")

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    with pytest.raises(RuntimeError, match="injected reset-watermarks staging failure"):
        async with session_factory() as session, session.begin():
            coordinator = instrument_reprocessing_coordinator.InstrumentReprocessingCoordinator(
                batch_size=1
            )
            repository = conversion_repository.InstrumentReprocessingConversionRepository(session)
            repository._job_repository = FailingJobRepository(session)
            await coordinator.process_instrument_level_triggers(
                conversion_repository=repository,
            )

    async with session_factory() as verification_session:
        trigger = (
            await verification_session.scalars(
                select(InstrumentReprocessingState).where(
                    InstrumentReprocessingState.security_id == "S-CONVERSION-ROLLBACK"
                )
            )
        ).one()
        jobs = list(
            (
                await verification_session.scalars(
                    select(ReprocessingJob).where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                )
            ).all()
        )

    assert trigger.earliest_impacted_date == date(2025, 8, 7)
    assert jobs == []


async def test_conversion_keeps_independent_securities_parallel(
    clean_db, async_db_session: AsyncSession
) -> None:
    async_db_session.add_all(
        [
            InstrumentReprocessingState(
                security_id="S-CONVERSION-LOCKED",
                earliest_impacted_date=date(2025, 8, 1),
                correlation_id="corr-locked",
            ),
            InstrumentReprocessingState(
                security_id="S-CONVERSION-PARALLEL",
                earliest_impacted_date=date(2025, 8, 2),
                correlation_id="corr-parallel",
            ),
        ]
    )
    await async_db_session.commit()

    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    first_trigger_claimed = asyncio.Event()
    release_first_conversion = asyncio.Event()

    class PausingJobRepository(ReprocessingJobRepository):
        async def stage_reset_watermarks_job(self, *args, **kwargs):
            first_trigger_claimed.set()
            await release_first_conversion.wait()
            return await super().stage_reset_watermarks_job(*args, **kwargs)

    async def convert_locked_security() -> None:
        async with session_factory() as session, session.begin():
            repository = conversion_repository.InstrumentReprocessingConversionRepository(session)
            repository._job_repository = PausingJobRepository(session)
            await repository.convert_pending_triggers(batch_size=1)

    first_conversion = asyncio.create_task(convert_locked_security())
    try:
        await asyncio.wait_for(first_trigger_claimed.wait(), timeout=5)
        async with session_factory() as parallel_session, parallel_session.begin():
            parallel_result = await asyncio.wait_for(
                conversion_repository.InstrumentReprocessingConversionRepository(
                    parallel_session
                ).convert_pending_triggers(batch_size=1),
                timeout=2,
            )

        assert parallel_result.claimed_count == 1
        assert parallel_result.created_count == 1
    finally:
        release_first_conversion.set()
        await _await_task_with_cleanup(first_conversion)

    async with session_factory() as verification_session:
        jobs = list(
            (
                await verification_session.scalars(
                    select(ReprocessingJob)
                    .where(ReprocessingJob.job_type == "RESET_WATERMARKS")
                    .order_by(ReprocessingJob.payload["security_id"].as_string())
                )
            ).all()
        )

    assert [job.payload["security_id"] for job in jobs] == [
        "S-CONVERSION-LOCKED",
        "S-CONVERSION-PARALLEL",
    ]


async def test_conversion_coalesces_earlier_trigger_into_one_pending_job(
    clean_db, async_db_session: AsyncSession
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)
    conversion_results: list[conversion_repository.InstrumentTriggerConversionResult] = []

    for impacted_date, correlation_id in (
        (date(2025, 8, 10), "corr-later"),
        (date(2025, 8, 4), "corr-earlier"),
    ):
        async with session_factory() as session, session.begin():
            await instrument_reprocessing_state_repository.InstrumentReprocessingStateRepository(
                session
            ).upsert_state(
                "S-CONVERSION-PENDING",
                impacted_date,
                correlation_id=correlation_id,
            )
        async with session_factory() as session, session.begin():
            conversion_results.append(await _convert_pending_triggers(session))

    async with session_factory() as verification_session:
        jobs = list(
            (
                await verification_session.scalars(
                    select(ReprocessingJob).where(
                        ReprocessingJob.job_type == "RESET_WATERMARKS",
                        ReprocessingJob.payload["security_id"].as_string()
                        == "S-CONVERSION-PENDING",
                    )
                )
            ).all()
        )

    assert len(jobs) == 1
    assert jobs[0].status == "PENDING"
    assert jobs[0].payload["earliest_impacted_date"] == "2025-08-04"
    assert jobs[0].correlation_id == "corr-earlier"
    assert [result.created_count for result in conversion_results] == [1, 0]
    assert [result.coalesced_pending_count for result in conversion_results] == [0, 1]


async def test_conversion_preserves_follow_up_generation_after_job_is_processing(
    clean_db, async_db_session: AsyncSession
) -> None:
    session_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async with session_factory() as session, session.begin():
        await instrument_reprocessing_state_repository.InstrumentReprocessingStateRepository(
            session
        ).upsert_state(
            "S-CONVERSION-PROCESSING",
            date(2025, 8, 10),
            correlation_id="corr-processing",
        )
    async with session_factory() as session, session.begin():
        await _convert_pending_triggers(session)
    async with session_factory() as session, session.begin():
        claimed = await ReprocessingJobRepository(session).find_and_claim_jobs(
            "RESET_WATERMARKS",
            batch_size=1,
        )
        assert len(claimed) == 1

    async with session_factory() as session, session.begin():
        await instrument_reprocessing_state_repository.InstrumentReprocessingStateRepository(
            session
        ).upsert_state(
            "S-CONVERSION-PROCESSING",
            date(2025, 8, 3),
            correlation_id="corr-follow-up",
        )
    async with session_factory() as session, session.begin():
        await _convert_pending_triggers(session)

    async with session_factory() as verification_session:
        jobs = list(
            (
                await verification_session.scalars(
                    select(ReprocessingJob)
                    .where(
                        ReprocessingJob.job_type == "RESET_WATERMARKS",
                        ReprocessingJob.payload["security_id"].as_string()
                        == "S-CONVERSION-PROCESSING",
                    )
                    .order_by(ReprocessingJob.id.asc())
                )
            ).all()
        )

    assert [(job.status, job.payload["earliest_impacted_date"]) for job in jobs] == [
        ("PROCESSING", "2025-08-10"),
        ("PENDING", "2025-08-03"),
    ]
    assert jobs[0].correlation_id == "corr-processing"
    assert jobs[1].correlation_id == "corr-follow-up"
