import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import ReprocessingJob
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.valuation_orchestrator_service.app.core.reprocessing_worker import (
    ReprocessingWorker,
)
from src.services.valuation_orchestrator_service.app.repositories.valuation_repository import (
    ValuationRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_dependencies():
    mock_valuation_repo = AsyncMock(spec=ValuationRepository)
    mock_state_repo = AsyncMock(spec=PositionStateRepository)
    mock_repro_job_repo = AsyncMock(spec=ReprocessingJobRepository)
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
            "src.services.valuation_orchestrator_service.app.core.reprocessing_worker.reprocessing_worker_batch_timer"
        ) as mock_batch_timer,
    ):
        mock_batch_timer.return_value.__enter__.return_value = None
        mock_batch_timer.return_value.__exit__.return_value = None
        yield {
            "valuation_repo": mock_valuation_repo,
            "state_repo": mock_state_repo,
            "repro_job_repo": mock_repro_job_repo,
            "observe_claimed": mock_observe_claimed,
            "observe_completed": mock_observe_completed,
            "observe_failed": mock_observe_failed,
            "observe_noop": mock_observe_noop,
            "observe_stale_skips": mock_observe_stale_skips,
            "batch_timer": mock_batch_timer,
        }


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
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    mock_repro_job_repo.find_and_claim_jobs.return_value = [pending_job]
    mock_repro_job_repo.update_job_status.return_value = True
    mock_valuation_repo.find_portfolios_holding_security_on_date.return_value = ["P1", "P2"]
    mock_state_repo.update_watermarks_if_older.return_value = 2

    await worker._process_batch()

    mock_batch_timer.assert_called_once()
    mock_observe_claimed.assert_called_once_with("RESET_WATERMARKS", 1)
    mock_observe_completed.assert_called_once_with("RESET_WATERMARKS")
    mock_observe_failed.assert_not_called()
    mock_observe_noop.assert_not_called()
    mock_repro_job_repo.find_and_reset_stale_jobs.assert_awaited_once_with(
        timeout_minutes=15,
        max_attempts=3,
    )
    mock_repro_job_repo.find_and_claim_jobs.assert_awaited_once_with("RESET_WATERMARKS", 10)
    mock_valuation_repo.find_portfolios_holding_security_on_date.assert_awaited_once_with(
        "S1",
        date(2025, 8, 10),
    )
    mock_state_repo.update_watermarks_if_older.assert_awaited_once_with(
        keys=[("P1", "S1"), ("P2", "S1")],
        new_watermark_date=date(2025, 8, 9),
    )
    mock_repro_job_repo.update_job_status.assert_awaited_once_with(1, "COMPLETE")


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
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    mock_repro_job_repo.find_and_claim_jobs.return_value = [pending_job]
    mock_repro_job_repo.update_job_status.return_value = True
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
    mock_repro_job_repo.update_job_status.assert_awaited_once_with(11, "COMPLETE")


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
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    mock_repro_job_repo.find_and_claim_jobs.return_value = [pending_job]
    mock_repro_job_repo.update_job_status.return_value = True
    mock_valuation_repo.find_portfolios_holding_security_on_date.return_value = ["P1"]
    mock_state_repo.update_watermarks_if_older.side_effect = RuntimeError("db write failed")

    await worker._process_batch()

    mock_observe_claimed.assert_called_once_with("RESET_WATERMARKS", 1)
    mock_observe_completed.assert_not_called()
    mock_observe_failed.assert_called_once_with("RESET_WATERMARKS")
    mock_repro_job_repo.update_job_status.assert_awaited_once()
    args, kwargs = mock_repro_job_repo.update_job_status.await_args
    assert args[:2] == (2, "FAILED")
    assert "db write failed" in kwargs["failure_reason"]


async def test_worker_resets_stale_jobs_before_claiming(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 3
    mock_repro_job_repo.find_and_claim_jobs.return_value = []

    await worker._process_batch()

    mock_repro_job_repo.find_and_reset_stale_jobs.assert_awaited_once_with(
        timeout_minutes=15,
        max_attempts=3,
    )
    mock_repro_job_repo.find_and_claim_jobs.assert_awaited_once_with("RESET_WATERMARKS", 10)


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

    mock_set_pending.assert_called_once_with("reprocessing", 6)
    mock_set_failed.assert_called_once_with("reprocessing", 2)
    mock_set_oldest.assert_called_once_with("reprocessing", 600.0)


async def test_worker_emits_noop_metric_when_no_impacted_portfolios(mock_dependencies):
    worker = ReprocessingWorker(poll_interval=0.1)
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    mock_observe_noop = mock_dependencies["observe_noop"]
    mock_observe_completed = mock_dependencies["observe_completed"]

    pending_job = ReprocessingJob(
        id=19,
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S1", "earliest_impacted_date": "2025-08-10"},
        status="PENDING",
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    mock_repro_job_repo.find_and_claim_jobs.return_value = [pending_job]
    mock_repro_job_repo.update_job_status.return_value = True
    mock_valuation_repo.find_portfolios_holding_security_on_date.return_value = []

    await worker._process_batch()

    mock_state_repo.update_watermarks_if_older.assert_not_called()
    mock_observe_noop.assert_called_once_with(
        "RESET_WATERMARKS",
        "no_impacted_portfolios",
    )
    mock_observe_completed.assert_called_once_with("RESET_WATERMARKS")
    mock_repro_job_repo.update_job_status.assert_awaited_once_with(19, "COMPLETE")


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
    )

    mock_repro_job_repo.find_and_reset_stale_jobs.return_value = 0
    mock_repro_job_repo.find_and_claim_jobs.return_value = [pending_job]
    mock_repro_job_repo.update_job_status.return_value = False
    mock_valuation_repo.find_portfolios_holding_security_on_date.return_value = ["P1"]
    mock_state_repo.update_watermarks_if_older.return_value = 1

    await worker._process_batch()

    mock_observe_completed.assert_not_called()
    mock_observe_stale_skips.assert_called_once_with(
        "reset_watermarks_terminal_ownership_lost",
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
    mock_repro_job_repo.find_and_claim_jobs.return_value = [
        ReprocessingJob(
            id=17,
            job_type="RESET_WATERMARKS",
            payload={"security_id": "S1", "earliest_impacted_date": "2025-08-10"},
            status="PENDING",
            correlation_id="corr-reset-17",
        )
    ]
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
