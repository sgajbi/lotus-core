import asyncio
from datetime import date, datetime, timezone
from unittest.mock import ANY, AsyncMock, call, patch

import pytest
from portfolio_common.database_models import ReprocessingJob
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import (
    ReprocessingJobRepository,
    ReprocessingJobTransitionOutcome,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.valuation_orchestrator_service.app.core import (
    fx_revaluation_job_processor,
)
from src.services.valuation_orchestrator_service.app.core.reprocessing_worker import (
    ReprocessingJobOwnershipLostError,
    ReprocessingWorker,
)
from src.services.valuation_orchestrator_service.app.domain.fx_revaluation import (
    ClaimedFxRevaluationJob,
    DirectCurrencyPair,
)
from src.services.valuation_orchestrator_service.app.infrastructure.repositories import (
    fx_revaluation_repository,
)
from src.services.valuation_orchestrator_service.app.repositories.valuation_repository import (
    ValuationRepository,
)

pytestmark = pytest.mark.asyncio

LEASE_TOKEN = "a" * 32


def _claim_reset_jobs_in_order(repository: AsyncMock, *jobs: object) -> None:
    repository.find_and_claim_jobs.side_effect = [[job] for job in jobs] + [[]]


def _claim_fx_jobs_in_order(repository: AsyncMock, *jobs: object) -> None:
    repository.claim_pending_jobs.side_effect = [[job] for job in jobs] + [[]]


@pytest.fixture
def mock_dependencies():
    mock_valuation_repo = AsyncMock(spec=ValuationRepository)
    mock_valuation_repo.find_portfolios_first_holding_security_after_date.return_value = []
    mock_state_repo = AsyncMock(spec=PositionStateRepository)
    mock_repro_job_repo = AsyncMock(spec=ReprocessingJobRepository)
    mock_fx_revaluation_repo = AsyncMock(
        spec=fx_revaluation_repository.SqlAlchemyFxRevaluationRepository
    )
    mock_fx_revaluation_repo.claim_pending_jobs.return_value = []
    mock_repro_job_repo.get_queue_stats.return_value = {
        "pending_count": 0,
        "failed_count": 0,
        "oldest_pending_created_at": None,
    }

    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_db_session.begin.return_value = AsyncMock()

    async def get_session_gen():
        yield mock_db_session

    with (
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.ValuationRepository",
            return_value=mock_valuation_repo,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.PositionStateRepository",
            return_value=mock_state_repo,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.ReprocessingJobRepository",
            return_value=mock_repro_job_repo,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.SqlAlchemyFxRevaluationRepository",
            return_value=mock_fx_revaluation_repo,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.observe_reprocessing_worker_jobs_claimed"
        ) as mock_observe_claimed,
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.observe_reprocessing_worker_jobs_completed"
        ) as mock_observe_completed,
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.observe_reprocessing_worker_jobs_failed"
        ) as mock_observe_failed,
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.observe_reprocessing_worker_jobs_noop"
        ) as mock_observe_noop,
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.observe_reprocessing_stale_skips"
        ) as mock_observe_stale_skips,
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.observe_reprocessing_worker_lease_renewal"
        ) as mock_observe_lease_renewal,
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.reprocessing_worker_batch_timer"
        ) as mock_batch_timer,
    ):
        mock_batch_timer.return_value.__enter__.return_value = None
        mock_batch_timer.return_value.__exit__.return_value = None
        yield {
            "valuation_repo": mock_valuation_repo,
            "state_repo": mock_state_repo,
            "repro_job_repo": mock_repro_job_repo,
            "fx_revaluation_repo": mock_fx_revaluation_repo,
            "observe_claimed": mock_observe_claimed,
            "observe_completed": mock_observe_completed,
            "observe_failed": mock_observe_failed,
            "observe_noop": mock_observe_noop,
            "observe_stale_skips": mock_observe_stale_skips,
            "observe_lease_renewal": mock_observe_lease_renewal,
            "batch_timer": mock_batch_timer,
            "db_session": mock_db_session,
        }


async def test_worker_processes_fx_revaluation_jobs_in_shared_runtime(mock_dependencies):
    processor = AsyncMock(spec=fx_revaluation_job_processor.FxRevaluationJobProcessor)
    worker = ReprocessingWorker(poll_interval=0.1, fx_job_processor=processor)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_fx_revaluation_repo = mock_dependencies["fx_revaluation_repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    mock_observe_claimed = mock_dependencies["observe_claimed"]
    pending_job = ClaimedFxRevaluationJob(
        job_id=40,
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
        lease_token=LEASE_TOKEN,
    )
    mock_repro_job_repo.find_and_claim_jobs.return_value = []
    _claim_fx_jobs_in_order(mock_fx_revaluation_repo, pending_job)

    await worker._process_batch()

    mock_fx_revaluation_repo.claim_pending_jobs.assert_has_awaits(
        [
            call(
                1,
                lease_owner=ANY,
                lease_duration_seconds=900,
                excluded_job_ids=(),
            ),
            call(
                1,
                lease_owner=ANY,
                lease_duration_seconds=900,
                excluded_job_ids=(40,),
            ),
        ]
    )
    processor.process.assert_awaited_once_with(
        job=pending_job,
        jobs=mock_repro_job_repo,
        watermarks=mock_state_repo,
        revaluation=mock_fx_revaluation_repo,
        before_terminal_transition=ANY,
    )
    mock_observe_claimed.assert_called_once_with("RESET_FX_WATERMARKS", 1)


async def test_worker_processes_reset_watermarks_job(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    mock_observe_claimed = mock_dependencies["observe_claimed"]
    mock_observe_completed = mock_dependencies["observe_completed"]
    mock_observe_failed = mock_dependencies["observe_failed"]
    mock_observe_noop = mock_dependencies["observe_noop"]
    mock_batch_timer = mock_dependencies["batch_timer"]

    job_payload = {"security_id": "S1", "earliest_impacted_date": "2025-08-10"}
    pending_job = ReprocessingJob(
        id=1,
        job_type="RESET_WATERMARKS",
        payload=job_payload,
        status="PENDING",
        lease_token=LEASE_TOKEN,
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    _claim_reset_jobs_in_order(mock_repro_job_repo, pending_job)
    mock_repro_job_repo.update_job_status.return_value = ReprocessingJobTransitionOutcome.APPLIED
    mock_valuation_repo.find_portfolios_holding_security_on_date.return_value = ["P1", "P2"]
    mock_state_repo.update_watermarks_if_older.return_value = 2

    await worker._process_batch()

    mock_batch_timer.assert_called_once()
    mock_observe_claimed.assert_called_once_with("RESET_WATERMARKS", 1)
    mock_observe_completed.assert_called_once_with("RESET_WATERMARKS")
    mock_observe_failed.assert_not_called()
    mock_observe_noop.assert_not_called()
    mock_repro_job_repo.find_and_reset_stale_jobs.assert_awaited_once_with(
        max_attempts=3,
    )
    mock_repro_job_repo.find_and_claim_jobs.assert_has_awaits(
        [
            call(
                "RESET_WATERMARKS",
                1,
                lease_owner=ANY,
                lease_duration_seconds=900,
                excluded_job_ids=(),
            ),
            call(
                "RESET_WATERMARKS",
                1,
                lease_owner=ANY,
                lease_duration_seconds=900,
                excluded_job_ids=(1,),
            ),
        ]
    )
    mock_valuation_repo.find_portfolios_holding_security_on_date.assert_awaited_once_with(
        "S1",
        date(2025, 8, 10),
    )
    mock_state_repo.update_watermarks_if_older.assert_awaited_once_with(
        keys=[("P1", "S1"), ("P2", "S1")],
        new_watermark_date=date(2025, 8, 9),
    )
    mock_repro_job_repo.update_job_status.assert_awaited_once_with(
        1,
        "COMPLETE",
        lease_token=LEASE_TOKEN,
    )


async def test_worker_renews_live_lease_until_job_operation_finishes(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    worker._lease_renewal_interval_seconds = 0.001
    jobs = mock_dependencies["repro_job_repo"]
    renewal_observed = asyncio.Event()

    async def renew(*args, **kwargs):
        renewal_observed.set()
        return ReprocessingJobTransitionOutcome.APPLIED

    async def operation(_terminal_transition_started):
        await renewal_observed.wait()

    jobs.renew_lease.side_effect = renew
    job = ReprocessingJob(
        id=101,
        job_type="RESET_WATERMARKS",
        payload={},
        status="PROCESSING",
        lease_token=LEASE_TOKEN,
    )

    await worker._process_with_lease_renewal(
        job=job,
        job_type="RESET_WATERMARKS",
        operation=operation,
    )

    jobs.renew_lease.assert_awaited_once_with(
        101,
        lease_token=LEASE_TOKEN,
        lease_duration_seconds=900,
    )
    mock_dependencies["observe_lease_renewal"].assert_called_once_with(
        "RESET_WATERMARKS",
        "renewed",
    )


async def test_worker_cancels_job_transaction_when_lease_renewal_loses_ownership(
    mock_dependencies,
):
    worker = ReprocessingWorker(poll_interval=0.1)
    worker._lease_renewal_interval_seconds = 0.001
    jobs = mock_dependencies["repro_job_repo"]
    operation_cancelled = asyncio.Event()
    jobs.renew_lease.return_value = ReprocessingJobTransitionOutcome.CLAIM_MISMATCH

    async def operation(_terminal_transition_started):
        try:
            await asyncio.Event().wait()
        finally:
            operation_cancelled.set()

    job = ReprocessingJob(
        id=102,
        job_type="RESET_WATERMARKS",
        payload={},
        status="PROCESSING",
        lease_token=LEASE_TOKEN,
    )

    with pytest.raises(ReprocessingJobOwnershipLostError, match="CLAIM_MISMATCH"):
        await worker._process_with_lease_renewal(
            job=job,
            job_type="RESET_WATERMARKS",
            operation=operation,
        )

    assert operation_cancelled.is_set()
    mock_dependencies["observe_lease_renewal"].assert_called_once_with(
        "RESET_WATERMARKS",
        "ownership_lost",
    )


async def test_worker_ignores_renewal_result_unblocked_by_terminal_commit(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    worker._lease_renewal_interval_seconds = 0.001
    jobs = mock_dependencies["repro_job_repo"]
    terminal_commit_reached = asyncio.Event()

    async def renew(*_args, **_kwargs):
        await terminal_commit_reached.wait()
        return ReprocessingJobTransitionOutcome.NOT_PROCESSING

    async def operation(terminal_transition_started):
        await asyncio.sleep(0.01)
        terminal_transition_started.set()
        terminal_commit_reached.set()

    jobs.renew_lease.side_effect = renew
    job = ReprocessingJob(
        id=104,
        job_type="RESET_WATERMARKS",
        payload={},
        status="PROCESSING",
        lease_token=LEASE_TOKEN,
    )

    await worker._process_with_lease_renewal(
        job=job,
        job_type="RESET_WATERMARKS",
        operation=operation,
    )

    jobs.renew_lease.assert_awaited_once()
    mock_dependencies["observe_lease_renewal"].assert_not_called()


async def test_worker_warns_when_some_watermark_resets_are_epoch_fenced(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    mock_observe_stale_skips = mock_dependencies["observe_stale_skips"]

    job_payload = {"security_id": "S1", "earliest_impacted_date": "2025-08-10"}
    pending_job = ReprocessingJob(
        id=11,
        job_type="RESET_WATERMARKS",
        payload=job_payload,
        status="PENDING",
        lease_token=LEASE_TOKEN,
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    _claim_reset_jobs_in_order(mock_repro_job_repo, pending_job)
    mock_repro_job_repo.update_job_status.return_value = ReprocessingJobTransitionOutcome.APPLIED
    mock_valuation_repo.find_portfolios_holding_security_on_date.return_value = ["P1", "P2"]
    mock_state_repo.update_watermarks_if_older.return_value = 1

    with patch(
        "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.logger.warning"
    ) as mock_warning:
        await worker._process_batch()

    mock_warning.assert_called_once()
    warning_kwargs = mock_warning.call_args.kwargs
    assert warning_kwargs["extra"]["targeted_count"] == 2
    assert warning_kwargs["extra"]["updated_count"] == 1
    assert warning_kwargs["extra"]["stale_skipped_count"] == 1
    mock_observe_stale_skips.assert_called_once_with("reset_watermarks_fanout", 1)
    mock_repro_job_repo.update_job_status.assert_awaited_once_with(
        11,
        "COMPLETE",
        lease_token=LEASE_TOKEN,
    )


async def test_worker_marks_failed_and_emits_failure_metric(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    mock_observe_claimed = mock_dependencies["observe_claimed"]
    mock_observe_completed = mock_dependencies["observe_completed"]
    mock_observe_failed = mock_dependencies["observe_failed"]

    job_payload = {"security_id": "S1", "earliest_impacted_date": "2025-08-10"}
    pending_job = ReprocessingJob(
        id=2,
        job_type="RESET_WATERMARKS",
        payload=job_payload,
        status="PENDING",
        lease_token=LEASE_TOKEN,
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    _claim_reset_jobs_in_order(mock_repro_job_repo, pending_job)
    mock_repro_job_repo.update_job_status.return_value = ReprocessingJobTransitionOutcome.APPLIED
    mock_valuation_repo.find_portfolios_holding_security_on_date.return_value = ["P1"]
    mock_state_repo.update_watermarks_if_older.side_effect = RuntimeError("db write failed")

    await worker._process_batch()

    mock_observe_claimed.assert_called_once_with("RESET_WATERMARKS", 1)
    mock_observe_completed.assert_not_called()
    mock_observe_failed.assert_called_once_with("RESET_WATERMARKS")
    mock_repro_job_repo.update_job_status.assert_awaited_once()
    args, kwargs = mock_repro_job_repo.update_job_status.await_args
    assert args[:2] == (2, "FAILED")
    assert kwargs["lease_token"] == LEASE_TOKEN
    assert "db write failed" in kwargs["failure_reason"]
    transaction_exits = mock_dependencies["db_session"].begin.return_value.__aexit__
    assert transaction_exits.await_args_list[2].args[0] is RuntimeError


async def test_worker_records_exception_type_when_failure_message_is_empty(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    jobs = mock_dependencies["repro_job_repo"]
    jobs.update_job_status.return_value = ReprocessingJobTransitionOutcome.APPLIED
    job = ReprocessingJob(
        id=103,
        job_type="RESET_WATERMARKS",
        payload={},
        status="PROCESSING",
        lease_token=LEASE_TOKEN,
    )

    await worker._mark_reset_watermark_job_failed(job=job, exc=RuntimeError())

    jobs.update_job_status.assert_awaited_once_with(
        103,
        "FAILED",
        lease_token=LEASE_TOKEN,
        failure_reason="RuntimeError",
    )


async def test_failed_job_rolls_back_without_preventing_sibling_commit(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    jobs = mock_dependencies["repro_job_repo"]
    valuations = mock_dependencies["valuation_repo"]
    states = mock_dependencies["state_repo"]
    first = ReprocessingJob(
        id=31,
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S-FAIL", "earliest_impacted_date": "2025-08-10"},
        status="PROCESSING",
        lease_token=LEASE_TOKEN,
    )
    second = ReprocessingJob(
        id=32,
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S-COMMIT", "earliest_impacted_date": "2025-08-10"},
        status="PROCESSING",
        lease_token=LEASE_TOKEN,
    )
    _claim_reset_jobs_in_order(jobs, first, second)
    jobs.update_job_status.return_value = ReprocessingJobTransitionOutcome.APPLIED
    valuations.find_portfolios_holding_security_on_date.return_value = ["P1"]
    states.update_watermarks_if_older.side_effect = [RuntimeError("first job failed"), 1]

    await worker._process_batch()

    assert jobs.update_job_status.await_args_list[0].args == (31, "FAILED")
    assert jobs.update_job_status.await_args_list[0].kwargs["lease_token"] == LEASE_TOKEN
    assert jobs.update_job_status.await_args_list[1].args == (32, "COMPLETE")
    assert jobs.update_job_status.await_args_list[1].kwargs == {"lease_token": LEASE_TOKEN}
    assert mock_dependencies["db_session"].begin.call_count == 9
    transaction_exits = mock_dependencies["db_session"].begin.return_value.__aexit__
    assert transaction_exits.await_args_list[2].args[0] is RuntimeError


async def test_worker_claims_each_job_only_after_the_previous_job_finishes(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1, batch_size=2)
    jobs = mock_dependencies["repro_job_repo"]
    first = ReprocessingJob(id=41, job_type="RESET_WATERMARKS", payload={})
    second = ReprocessingJob(id=42, job_type="RESET_WATERMARKS", payload={})
    events: list[str] = []
    unclaimed = iter((first, second, None))
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def claim_next(*_args, **_kwargs):
        job = next(unclaimed)
        events.append("claim-empty" if job is None else f"claim-{job.id}")
        return [] if job is None else [job]

    async def process(*, job):
        events.append(f"process-{job.id}")
        if job.id == first.id:
            first_started.set()
            await release_first.wait()

    jobs.find_and_claim_jobs.side_effect = claim_next
    worker._process_reset_watermark_job = process  # type: ignore[method-assign]

    batch = asyncio.create_task(worker._process_batch())
    await first_started.wait()

    assert events == ["claim-41", "process-41"]

    release_first.set()
    await batch

    assert events == ["claim-41", "process-41", "claim-42", "process-42"]
    assert all(call_args.args[1] == 1 for call_args in jobs.find_and_claim_jobs.await_args_list)


async def test_worker_processes_each_requeued_reset_job_at_most_once_per_poll(
    mock_dependencies,
):
    worker = ReprocessingWorker(poll_interval=0.1, batch_size=2)
    jobs = mock_dependencies["repro_job_repo"]
    first = ReprocessingJob(id=61, job_type="RESET_WATERMARKS", payload={})
    second = ReprocessingJob(id=62, job_type="RESET_WATERMARKS", payload={})

    async def claim_next(*_args, excluded_job_ids, **_kwargs):
        if first.id not in excluded_job_ids:
            return [first]
        if second.id not in excluded_job_ids:
            return [second]
        return []

    jobs.find_and_claim_jobs.side_effect = claim_next
    worker._process_reset_watermark_job = AsyncMock()  # type: ignore[method-assign]

    await worker._process_batch()

    assert [
        awaited.kwargs["excluded_job_ids"] for awaited in jobs.find_and_claim_jobs.await_args_list
    ] == [(), (first.id,)]
    assert [
        awaited.kwargs["job"].id for awaited in worker._process_reset_watermark_job.await_args_list
    ] == [first.id, second.id]


async def test_worker_processes_each_requeued_fx_job_at_most_once_per_poll(
    mock_dependencies,
):
    worker = ReprocessingWorker(poll_interval=0.1, batch_size=2)
    reset_jobs = mock_dependencies["repro_job_repo"]
    fx_jobs = mock_dependencies["fx_revaluation_repo"]
    reset_jobs.find_and_claim_jobs.return_value = []
    first = ClaimedFxRevaluationJob(
        job_id=71,
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
        lease_token=LEASE_TOKEN,
    )
    second = ClaimedFxRevaluationJob(
        job_id=72,
        pair=DirectCurrencyPair("EUR", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
        lease_token=LEASE_TOKEN,
    )

    async def claim_next(*_args, excluded_job_ids, **_kwargs):
        if first.job_id not in excluded_job_ids:
            return [first]
        if second.job_id not in excluded_job_ids:
            return [second]
        return []

    fx_jobs.claim_pending_jobs.side_effect = claim_next
    worker._process_fx_revaluation_job = AsyncMock()  # type: ignore[method-assign]

    await worker._process_batch()

    assert [
        awaited.kwargs["excluded_job_ids"] for awaited in fx_jobs.claim_pending_jobs.await_args_list
    ] == [(), (first.job_id,)]
    assert [
        awaited.kwargs["job"].job_id
        for awaited in worker._process_fx_revaluation_job.await_args_list
    ] == [first.job_id, second.job_id]


async def test_malformed_reset_payload_fails_without_blocking_valid_sibling(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1, batch_size=2)
    jobs = mock_dependencies["repro_job_repo"]
    valuations = mock_dependencies["valuation_repo"]
    states = mock_dependencies["state_repo"]
    malformed = ReprocessingJob(
        id=51,
        job_type="RESET_WATERMARKS",
        payload=None,
        lease_token=LEASE_TOKEN,
    )
    valid = ReprocessingJob(
        id=52,
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S-VALID", "earliest_impacted_date": "2025-08-10"},
        lease_token=LEASE_TOKEN,
    )
    _claim_reset_jobs_in_order(jobs, malformed, valid)
    jobs.update_job_status.return_value = ReprocessingJobTransitionOutcome.APPLIED
    valuations.find_portfolios_holding_security_on_date.return_value = ["P1"]
    states.update_watermarks_if_older.return_value = 1

    await worker._process_batch()

    assert jobs.update_job_status.await_args_list[0].args == (51, "FAILED")
    assert jobs.update_job_status.await_args_list[0].kwargs["lease_token"] == LEASE_TOKEN
    assert jobs.update_job_status.await_args_list[0].kwargs["failure_reason"]
    assert jobs.update_job_status.await_args_list[1] == call(
        52,
        "COMPLETE",
        lease_token=LEASE_TOKEN,
    )
    states.update_watermarks_if_older.assert_awaited_once()


async def test_worker_resets_stale_jobs_before_claiming(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 3
    mock_repro_job_repo.find_and_claim_jobs.return_value = []

    await worker._process_batch()

    mock_repro_job_repo.find_and_reset_stale_jobs.assert_awaited_once_with(
        max_attempts=3,
    )
    mock_repro_job_repo.find_and_claim_jobs.assert_awaited_once_with(
        "RESET_WATERMARKS",
        1,
        lease_owner=ANY,
        lease_duration_seconds=900,
        excluded_job_ids=(),
    )


async def test_worker_reads_poll_and_batch_from_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REPROCESSING_WORKER_POLL_INTERVAL_SECONDS", "7")
    monkeypatch.setenv("REPROCESSING_WORKER_BATCH_SIZE", "21")
    monkeypatch.setenv("REPROCESSING_WORKER_STALE_TIMEOUT_MINUTES", "14")
    monkeypatch.setenv("REPROCESSING_WORKER_MAX_ATTEMPTS", "5")

    worker = ReprocessingWorker()

    assert worker._poll_interval == 7
    assert worker._batch_size == 21
    assert worker._stale_timeout_minutes == 14
    assert worker._max_attempts == 5


async def test_worker_updates_queue_metrics(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_repro_job_repo.get_queue_stats.return_value = {
        "pending_count": 6,
        "failed_count": 2,
        "oldest_pending_created_at": datetime(2025, 8, 12, 0, 0, tzinfo=timezone.utc),
    }

    with (
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.set_control_queue_pending"
        ) as mock_set_pending,
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.set_control_queue_failed_stored"
        ) as mock_set_failed,
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.set_control_queue_oldest_pending_age_seconds"
        ) as mock_set_oldest,
        patch(
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.datetime"
        ) as mock_datetime,
    ):
        mock_datetime.now.return_value = datetime(2025, 8, 12, 0, 10, tzinfo=timezone.utc)
        mock_datetime.side_effect = datetime

        await worker._update_queue_metrics(mock_repro_job_repo)

    mock_repro_job_repo.get_queue_stats.assert_awaited_once_with()
    mock_set_pending.assert_called_once_with("reprocessing", 6)
    mock_set_failed.assert_called_once_with("reprocessing", 2)
    mock_set_oldest.assert_called_once_with("reprocessing", 600.0)


async def test_worker_requeues_job_when_no_impacted_portfolios_are_visible_yet(
    mock_dependencies,
):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    mock_observe_noop = mock_dependencies["observe_noop"]
    mock_observe_completed = mock_dependencies["observe_completed"]
    mock_observe_stale_skips = mock_dependencies["observe_stale_skips"]

    pending_job = ReprocessingJob(
        id=19,
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S1", "earliest_impacted_date": "2025-08-10"},
        status="PENDING",
        lease_token=LEASE_TOKEN,
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    _claim_reset_jobs_in_order(mock_repro_job_repo, pending_job)
    mock_repro_job_repo.update_job_status.return_value = ReprocessingJobTransitionOutcome.APPLIED
    mock_valuation_repo.find_portfolios_holding_security_on_date.return_value = []
    mock_valuation_repo.find_portfolios_first_holding_security_after_date.return_value = []

    await worker._process_batch()

    mock_state_repo.update_watermarks_if_older.assert_not_called()
    mock_observe_noop.assert_called_once_with(
        "RESET_WATERMARKS",
        "no_impacted_portfolios",
    )
    mock_observe_completed.assert_not_called()
    mock_observe_stale_skips.assert_not_called()
    mock_repro_job_repo.update_job_status.assert_awaited_once_with(
        19,
        "PENDING",
        lease_token=LEASE_TOKEN,
    )


async def test_worker_falls_back_to_later_first_holdings_before_requeueing(
    mock_dependencies,
):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    mock_observe_completed = mock_dependencies["observe_completed"]
    mock_observe_noop = mock_dependencies["observe_noop"]

    pending_job = ReprocessingJob(
        id=20,
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S1", "earliest_impacted_date": "2025-08-10"},
        status="PENDING",
        lease_token=LEASE_TOKEN,
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    _claim_reset_jobs_in_order(mock_repro_job_repo, pending_job)
    mock_repro_job_repo.update_job_status.return_value = ReprocessingJobTransitionOutcome.APPLIED
    mock_valuation_repo.find_portfolios_holding_security_on_date.return_value = []
    mock_valuation_repo.find_portfolios_first_holding_security_after_date.return_value = ["P_LATE"]
    mock_state_repo.update_watermarks_if_older.return_value = 1

    await worker._process_batch()

    mock_valuation_repo.find_portfolios_holding_security_on_date.assert_awaited_once_with(
        "S1",
        date(2025, 8, 10),
    )
    mock_valuation_repo.find_portfolios_first_holding_security_after_date.assert_awaited_once_with(
        "S1",
        date(2025, 8, 10),
    )
    mock_state_repo.update_watermarks_if_older.assert_awaited_once_with(
        keys=[("P_LATE", "S1")],
        new_watermark_date=date(2025, 8, 9),
    )
    mock_observe_noop.assert_not_called()
    mock_observe_completed.assert_called_once_with("RESET_WATERMARKS")
    mock_repro_job_repo.update_job_status.assert_awaited_once_with(
        20,
        "COMPLETE",
        lease_token=LEASE_TOKEN,
    )


async def test_worker_unions_current_and_later_holdings_for_replay_reset(
    mock_dependencies,
):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_state_repo = mock_dependencies["state_repo"]

    pending_job = ReprocessingJob(
        id=23,
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S1", "earliest_impacted_date": "2025-08-10"},
        status="PENDING",
        lease_token=LEASE_TOKEN,
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    _claim_reset_jobs_in_order(mock_repro_job_repo, pending_job)
    mock_repro_job_repo.update_job_status.return_value = ReprocessingJobTransitionOutcome.APPLIED
    mock_valuation_repo.find_portfolios_holding_security_on_date.return_value = ["P_SHORT"]
    mock_valuation_repo.find_portfolios_first_holding_security_after_date.return_value = [
        "P_LATE",
        "P_SHORT",
    ]
    mock_state_repo.update_watermarks_if_older.return_value = 2

    await worker._process_batch()

    mock_valuation_repo.find_portfolios_first_holding_security_after_date.assert_awaited_once_with(
        "S1",
        date(2025, 8, 10),
    )
    mock_state_repo.update_watermarks_if_older.assert_awaited_once_with(
        keys=[("P_LATE", "S1"), ("P_SHORT", "S1")],
        new_watermark_date=date(2025, 8, 9),
    )
    mock_repro_job_repo.update_job_status.assert_awaited_once_with(
        23,
        "COMPLETE",
        lease_token=LEASE_TOKEN,
    )


async def test_worker_skips_completion_metric_when_terminal_ownership_is_lost(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    mock_observe_completed = mock_dependencies["observe_completed"]
    mock_observe_stale_skips = mock_dependencies["observe_stale_skips"]

    pending_job = ReprocessingJob(
        id=21,
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S1", "earliest_impacted_date": "2025-08-10"},
        status="PENDING",
        lease_token=LEASE_TOKEN,
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    _claim_reset_jobs_in_order(mock_repro_job_repo, pending_job)
    mock_repro_job_repo.update_job_status.return_value = (
        ReprocessingJobTransitionOutcome.LEASE_EXPIRED
    )
    mock_valuation_repo.find_portfolios_holding_security_on_date.return_value = ["P1"]
    mock_state_repo.update_watermarks_if_older.return_value = 1

    await worker._process_batch()

    mock_observe_completed.assert_not_called()
    mock_observe_stale_skips.assert_called_once_with(
        "reset_watermarks_terminal_ownership_lost",
        1,
    )
    transaction_exits = mock_dependencies["db_session"].begin.return_value.__aexit__
    assert transaction_exits.await_args_list[2].args[0] is ReprocessingJobOwnershipLostError


async def test_worker_emits_requeue_ownership_metric_when_requeue_ownership_is_lost(
    mock_dependencies,
):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    mock_observe_completed = mock_dependencies["observe_completed"]
    mock_observe_stale_skips = mock_dependencies["observe_stale_skips"]

    pending_job = ReprocessingJob(
        id=22,
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S1", "earliest_impacted_date": "2025-08-10"},
        status="PENDING",
        lease_token=LEASE_TOKEN,
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    _claim_reset_jobs_in_order(mock_repro_job_repo, pending_job)
    mock_repro_job_repo.update_job_status.return_value = (
        ReprocessingJobTransitionOutcome.CLAIM_MISMATCH
    )
    mock_valuation_repo.find_portfolios_holding_security_on_date.return_value = []
    mock_valuation_repo.find_portfolios_first_holding_security_after_date.return_value = []

    await worker._process_batch()

    mock_state_repo.update_watermarks_if_older.assert_not_called()
    mock_observe_completed.assert_not_called()
    mock_observe_stale_skips.assert_called_once_with(
        "reset_watermarks_requeue_ownership_lost",
        1,
    )


async def test_worker_processes_job_under_job_correlation_context(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_state_repo = mock_dependencies["state_repo"]

    observed_correlation_ids: list[str] = []

    async def capture_find_portfolios(*args, **kwargs):
        observed_correlation_ids.append(correlation_id_var.get())
        return ["P1"]

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    _claim_reset_jobs_in_order(
        mock_repro_job_repo,
        ReprocessingJob(
            id=17,
            job_type="RESET_WATERMARKS",
            payload={"security_id": "S1", "earliest_impacted_date": "2025-08-10"},
            status="PENDING",
            lease_token=LEASE_TOKEN,
            correlation_id="corr-reset-17",
        ),
    )
    mock_valuation_repo.find_portfolios_holding_security_on_date.side_effect = (
        capture_find_portfolios
    )
    mock_state_repo.update_watermarks_if_older.return_value = 1

    token = correlation_id_var.set("<not-set>")
    try:
        await worker._process_batch()
    finally:
        correlation_id_var.reset(token)

    assert observed_correlation_ids == ["corr-reset-17"]
    assert correlation_id_var.get() == "<not-set>"


async def test_worker_stop_interrupts_poll_sleep():
    worker = ReprocessingWorker(poll_interval=60)
    batch_started = asyncio.Event()

    async def process_once():
        batch_started.set()

    worker._process_batch = process_once  # type: ignore[method-assign]

    task = asyncio.create_task(worker.run())
    await batch_started.wait()
    await asyncio.sleep(0)

    worker.stop()

    await asyncio.wait_for(task, timeout=0.2)
