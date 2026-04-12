import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.config import KAFKA_VALUATION_JOB_REQUESTED_TOPIC
from portfolio_common.database_models import (
    InstrumentReprocessingState,
    PortfolioValuationJob,
    PositionState,
)
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.monitoring import (
    INSTRUMENT_REPROCESSING_TRIGGERS_PENDING,
    POSITION_STATE_WATERMARK_LAG_DAYS,
)
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.valuation_orchestrator_service.app.core.valuation_scheduler import (
    ValuationScheduler,
)
from src.services.valuation_orchestrator_service.app.repositories.valuation_repository import (
    ValuationRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    mock = MagicMock(spec=KafkaProducer)
    mock.flush.return_value = 0
    return mock


@pytest.fixture
def scheduler(mock_kafka_producer: MagicMock) -> ValuationScheduler:
    with patch(
        "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.get_kafka_producer",
        return_value=mock_kafka_producer,
    ):
        yield ValuationScheduler(poll_interval=0.01)


@pytest.fixture
def mock_dependencies():
    mock_repo = AsyncMock(spec=ValuationRepository)
    mock_job_repo = AsyncMock(spec=ValuationJobRepository)
    mock_job_repo.upsert_jobs.return_value = 0
    mock_state_repo = AsyncMock(spec=PositionStateRepository)
    mock_repro_job_repo = AsyncMock(spec=ReprocessingJobRepository)

    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_db_session.begin.return_value = AsyncMock()

    async def get_session_gen():
        yield mock_db_session

    with (
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.get_async_db_session",
            new=get_session_gen,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.ValuationRepository",
            return_value=mock_repo,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.ValuationJobRepository",
            return_value=mock_job_repo,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.PositionStateRepository",
            return_value=mock_state_repo,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.ReprocessingJobRepository",
            return_value=mock_repro_job_repo,
        ),
    ):
        yield {
            "repo": mock_repo,
            "job_repo": mock_job_repo,
            "state_repo": mock_state_repo,
            "repro_job_repo": mock_repro_job_repo,
        }


async def test_scheduler_creates_position_aware_backfill_jobs(
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_job_repo = mock_dependencies["job_repo"]

    latest_business_date = date(2025, 8, 12)
    first_open_date = date(2025, 8, 10)
    watermark_date = date(1970, 1, 1)
    expected_lag = (latest_business_date - watermark_date).days

    states_to_backfill = [
        PositionState(portfolio_id="P1", security_id="S1", watermark_date=watermark_date, epoch=1)
    ]

    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_states_needing_backfill.return_value = states_to_backfill
    mock_repo.get_first_open_dates_for_keys.return_value = {("P1", "S1", 1): first_open_date}
    mock_job_repo.upsert_jobs.return_value = 3

    with patch.object(POSITION_STATE_WATERMARK_LAG_DAYS, "labels") as mock_gauge_labels:
        await scheduler._create_backfill_jobs(AsyncMock())

        mock_job_repo.upsert_jobs.assert_awaited_once()
        scheduled_jobs = mock_job_repo.upsert_jobs.await_args.args[0]
        assert [job.valuation_date for job in scheduled_jobs] == [
            date(2025, 8, 10),
            date(2025, 8, 11),
            date(2025, 8, 12),
        ]
        assert scheduled_jobs[0].correlation_id == "SCHEDULER_BACKFILL:P1:S1:1:2025-08-10"
        mock_gauge_labels.assert_called_once_with(portfolio_id="P1", security_id="S1")
        mock_gauge_labels.return_value.set.assert_called_once_with(expected_lag)


async def test_scheduler_normalizes_non_reprocessing_keys_with_no_position_history(
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_state_repo = mock_dependencies["state_repo"]

    latest_business_date = date(2025, 8, 12)
    states_to_backfill = [
        PositionState(
            portfolio_id="P1",
            security_id="S1",
            watermark_date=date(2025, 8, 10),
            epoch=1,
        )
    ]

    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_states_needing_backfill.return_value = states_to_backfill
    mock_repo.get_first_open_dates_for_keys.return_value = {}

    await scheduler._create_backfill_jobs(AsyncMock())

    mock_job_repo.upsert_jobs.assert_not_called()
    mock_state_repo.bulk_update_states.assert_awaited_once_with(
        [
            {
                "portfolio_id": "P1",
                "security_id": "S1",
                "expected_epoch": 1,
                "watermark_date": latest_business_date,
                "status": "CURRENT",
            }
        ]
    )


async def test_scheduler_defers_reprocessing_keys_with_no_position_history(
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_state_repo = mock_dependencies["state_repo"]

    latest_business_date = date(2025, 8, 12)
    states_to_backfill = [
        PositionState(
            portfolio_id="P1",
            security_id="S1",
            watermark_date=date(2025, 8, 10),
            epoch=1,
            status="REPROCESSING",
        )
    ]

    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_states_needing_backfill.return_value = states_to_backfill
    mock_repo.get_first_open_dates_for_keys.return_value = {}

    await scheduler._create_backfill_jobs(AsyncMock())

    mock_job_repo.upsert_jobs.assert_not_called()
    mock_state_repo.bulk_update_states.assert_not_awaited()


async def test_scheduler_advances_watermarks(
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    latest_business_date = date(2025, 8, 15)

    lagging_states = [
        PositionState(
            portfolio_id="P1",
            security_id="S1",
            watermark_date=date(2025, 8, 10),
            epoch=1,
            status="REPROCESSING",
        ),
        PositionState(
            portfolio_id="P2",
            security_id="S2",
            watermark_date=date(2025, 8, 10),
            epoch=2,
            status="REPROCESSING",
        ),
        PositionState(
            portfolio_id="P3",
            security_id="S3",
            watermark_date=date(2025, 8, 10),
            epoch=1,
            status="REPROCESSING",
        ),
    ]
    advancable_dates = {
        ("P1", "S1"): date(2025, 8, 15),
        ("P2", "S2"): date(2025, 8, 12),
    }

    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_lagging_states.return_value = lagging_states
    mock_repo.get_terminal_reprocessing_states.return_value = []
    mock_repo.get_first_open_dates_for_keys.return_value = {
        ("P1", "S1", 1): date(2025, 8, 11),
        ("P2", "S2", 2): date(2025, 8, 11),
        ("P3", "S3", 1): date(2025, 8, 11),
    }
    mock_repo.find_contiguous_snapshot_dates.return_value = advancable_dates
    mock_state_repo.bulk_update_states.return_value = 2

    await scheduler._advance_watermarks(AsyncMock())

    mock_repo.find_contiguous_snapshot_dates.assert_awaited_once_with(
        lagging_states,
        {
            ("P1", "S1", 1): date(2025, 8, 11),
            ("P2", "S2", 2): date(2025, 8, 11),
            ("P3", "S3", 1): date(2025, 8, 11),
        },
    )
    mock_state_repo.bulk_update_states.assert_awaited_once()
    updates_arg = mock_state_repo.bulk_update_states.call_args[0][0]
    assert len(updates_arg) == 2
    update1 = next(u for u in updates_arg if u["portfolio_id"] == "P1")
    assert update1["status"] == "CURRENT"
    assert update1["expected_epoch"] == 1


async def test_scheduler_warns_when_epoch_fence_skips_some_updates(
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    latest_business_date = date(2025, 8, 15)

    lagging_states = [
        PositionState(
            portfolio_id="P1",
            security_id="S1",
            watermark_date=date(2025, 8, 10),
            epoch=1,
            status="REPROCESSING",
        ),
        PositionState(
            portfolio_id="P2",
            security_id="S2",
            watermark_date=date(2025, 8, 10),
            epoch=2,
            status="REPROCESSING",
        ),
    ]
    advancable_dates = {
        ("P1", "S1"): date(2025, 8, 15),
        ("P2", "S2"): date(2025, 8, 12),
    }

    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_lagging_states.return_value = lagging_states
    mock_repo.get_terminal_reprocessing_states.return_value = []
    mock_repo.get_first_open_dates_for_keys.return_value = {
        ("P1", "S1", 1): date(2025, 8, 11),
        ("P2", "S2", 2): date(2025, 8, 11),
    }
    mock_repo.find_contiguous_snapshot_dates.return_value = advancable_dates
    mock_state_repo.bulk_update_states.return_value = 1

    with (
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.logger.warning"
        ) as mock_warning,
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.observe_reprocessing_stale_skips"
        ) as mock_observe_stale_skips,
    ):
        await scheduler._advance_watermarks(AsyncMock())

    mock_warning.assert_called_once()
    warning_kwargs = mock_warning.call_args.kwargs
    assert warning_kwargs["extra"]["prepared_count"] == 2
    assert warning_kwargs["extra"]["updated_count"] == 1
    assert warning_kwargs["extra"]["stale_skipped_count"] == 1
    mock_observe_stale_skips.assert_called_once_with("watermark_advance", 1)


async def test_scheduler_advances_from_first_open_date_for_sentinel_watermarks(
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    latest_business_date = date(2025, 8, 15)

    lagging_states = [
        PositionState(
            portfolio_id="P1",
            security_id="S1",
            watermark_date=date(1970, 1, 1),
            epoch=1,
            status="CURRENT",
        ),
    ]

    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_lagging_states.return_value = lagging_states
    mock_repo.get_terminal_reprocessing_states.return_value = []
    mock_repo.get_first_open_dates_for_keys.return_value = {
        ("P1", "S1", 1): date(2025, 8, 10),
    }
    mock_repo.find_contiguous_snapshot_dates.return_value = {
        ("P1", "S1"): latest_business_date,
    }
    mock_state_repo.bulk_update_states.return_value = 1

    await scheduler._advance_watermarks(AsyncMock())

    mock_repo.find_contiguous_snapshot_dates.assert_awaited_once_with(
        lagging_states,
        {("P1", "S1", 1): date(2025, 8, 10)},
    )
    mock_state_repo.bulk_update_states.assert_awaited_once_with(
        [
            {
                "portfolio_id": "P1",
                "security_id": "S1",
                "expected_epoch": 1,
                "watermark_date": latest_business_date,
                "status": "CURRENT",
            }
        ]
    )


async def test_scheduler_normalizes_zombies_and_still_creates_backfill_for_live_keys(
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_job_repo = mock_dependencies["job_repo"]
    mock_state_repo = mock_dependencies["state_repo"]

    latest_business_date = date(2025, 8, 12)
    states_to_backfill = [
        PositionState(
            portfolio_id="ZOMBIE",
            security_id="NOHIST",
            watermark_date=date(1970, 1, 1),
            epoch=0,
            status="CURRENT",
        ),
        PositionState(
            portfolio_id="LIVE",
            security_id="OPENPOS",
            watermark_date=date(1970, 1, 1),
            epoch=0,
            status="CURRENT",
        ),
    ]

    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_states_needing_backfill.return_value = states_to_backfill
    mock_repo.get_first_open_dates_for_keys.return_value = {
        ("LIVE", "OPENPOS", 0): date(2025, 8, 10),
    }
    mock_state_repo.bulk_update_states.return_value = 1
    mock_job_repo.upsert_jobs.return_value = 3

    await scheduler._create_backfill_jobs(AsyncMock())

    mock_state_repo.bulk_update_states.assert_awaited_once_with(
        [
            {
                "portfolio_id": "ZOMBIE",
                "security_id": "NOHIST",
                "expected_epoch": 0,
                "watermark_date": latest_business_date,
                "status": "CURRENT",
            }
        ]
    )
    mock_job_repo.upsert_jobs.assert_awaited_once()
    scheduled_jobs = mock_job_repo.upsert_jobs.await_args.args[0]
    assert [job.valuation_date for job in scheduled_jobs] == [
        date(2025, 8, 10),
        date(2025, 8, 11),
        date(2025, 8, 12),
    ]


async def test_scheduler_updates_queue_metrics(
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    oldest_pending = datetime(2025, 8, 12, tzinfo=timezone.utc)
    mock_repo.get_job_queue_stats.return_value = {
        "pending_count": 4,
        "failed_count": 2,
        "oldest_pending_created_at": oldest_pending,
    }

    with (
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.set_control_queue_pending"
        ) as mock_set_pending,
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.set_control_queue_failed_stored"
        ) as mock_set_failed,
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.set_control_queue_oldest_pending_age_seconds"
        ) as mock_set_oldest,
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.datetime"
        ) as mock_datetime,
    ):
        mock_datetime.now.return_value = datetime(2025, 8, 12, 0, 5, tzinfo=timezone.utc)
        mock_datetime.side_effect = datetime

        await scheduler._update_queue_metrics(AsyncMock())

    mock_set_pending.assert_called_once_with("valuation", 4)
    mock_set_failed.assert_called_once_with("valuation", 2)
    mock_set_oldest.assert_called_once_with("valuation", 300.0)


async def test_scheduler_normalizes_terminal_reprocessing_states(
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    latest_business_date = date(2025, 8, 15)

    terminal_states = [
        PositionState(
            portfolio_id="P9",
            security_id="S9",
            watermark_date=latest_business_date,
            epoch=4,
            status="REPROCESSING",
        )
    ]

    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_lagging_states.return_value = []
    mock_repo.get_terminal_reprocessing_states.return_value = terminal_states
    mock_state_repo.bulk_update_states.return_value = 1

    await scheduler._advance_watermarks(AsyncMock())

    mock_state_repo.bulk_update_states.assert_awaited_once_with(
        [
            {
                "portfolio_id": "P9",
                "security_id": "S9",
                "expected_epoch": 4,
                "watermark_date": latest_business_date,
                "status": "CURRENT",
            }
        ]
    )


async def test_scheduler_warns_when_terminal_normalization_is_epoch_fenced(
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_state_repo = mock_dependencies["state_repo"]
    latest_business_date = date(2025, 8, 15)

    terminal_states = [
        PositionState(
            portfolio_id="P9",
            security_id="S9",
            watermark_date=latest_business_date,
            epoch=4,
            status="REPROCESSING",
        ),
        PositionState(
            portfolio_id="P8",
            security_id="S8",
            watermark_date=latest_business_date,
            epoch=7,
            status="REPROCESSING",
        ),
    ]

    mock_repo.get_latest_business_date.return_value = latest_business_date
    mock_repo.get_lagging_states.return_value = []
    mock_repo.get_terminal_reprocessing_states.return_value = terminal_states
    mock_state_repo.bulk_update_states.return_value = 1

    with (
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.logger.warning"
        ) as mock_warning,
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.observe_reprocessing_stale_skips"
        ) as mock_observe_stale_skips,
    ):
        await scheduler._advance_watermarks(AsyncMock())

    mock_warning.assert_called_once()
    warning_kwargs = mock_warning.call_args.kwargs
    assert warning_kwargs["extra"]["prepared_count"] == 2
    assert warning_kwargs["extra"]["updated_count"] == 1
    assert warning_kwargs["extra"]["stale_skipped_count"] == 1
    mock_observe_stale_skips.assert_called_once_with(
        "terminal_reprocessing_normalization",
        1,
    )


async def test_scheduler_dispatches_claimed_jobs(
    scheduler: ValuationScheduler,
    mock_kafka_producer: MagicMock,
):
    claimed_jobs = [
        PortfolioValuationJob(
            portfolio_id="P1",
            security_id="S1",
            valuation_date=date(2025, 8, 11),
            epoch=1,
            correlation_id="corr-1",
        ),
    ]

    await scheduler._dispatch_jobs(claimed_jobs)

    mock_kafka_producer.publish_message.assert_called_once_with(
        topic=KAFKA_VALUATION_JOB_REQUESTED_TOPIC,
        key="P1",
        value={
            "portfolio_id": "P1",
            "security_id": "S1",
            "valuation_date": "2025-08-11",
            "epoch": 1,
            "correlation_id": "corr-1",
        },
        headers=[("correlation_id", b"corr-1")],
    )
    mock_kafka_producer.flush.assert_called_once_with(timeout=10)


async def test_scheduler_omits_empty_correlation_header(
    scheduler: ValuationScheduler,
    mock_kafka_producer: MagicMock,
):
    claimed_jobs = [
        PortfolioValuationJob(
            portfolio_id="P2",
            security_id="S2",
            valuation_date=date(2025, 8, 12),
            epoch=3,
            correlation_id=None,
        ),
    ]

    await scheduler._dispatch_jobs(claimed_jobs)

    mock_kafka_producer.publish_message.assert_called_once_with(
        topic=KAFKA_VALUATION_JOB_REQUESTED_TOPIC,
        key="P2",
        value={
            "portfolio_id": "P2",
            "security_id": "S2",
            "valuation_date": "2025-08-12",
            "epoch": 3,
            "correlation_id": None,
        },
        headers=[],
    )
    mock_kafka_producer.flush.assert_called_once_with(timeout=10)


async def test_scheduler_flushes_and_raises_with_remaining_keys_on_partial_dispatch_failure(
    scheduler: ValuationScheduler,
    mock_kafka_producer: MagicMock,
):
    claimed_jobs = [
        PortfolioValuationJob(
            portfolio_id="P1",
            security_id="S1",
            valuation_date=date(2025, 8, 11),
            epoch=1,
            correlation_id="corr-1",
        ),
        PortfolioValuationJob(
            portfolio_id="P1",
            security_id="S2",
            valuation_date=date(2025, 8, 12),
            epoch=1,
            correlation_id="corr-2",
        ),
    ]
    mock_kafka_producer.publish_message.side_effect = [None, RuntimeError("broker timeout")]

    with pytest.raises(RuntimeError, match="Remaining job keys: P1\\|S2\\|2025-08-12\\|1"):
        await scheduler._dispatch_jobs(claimed_jobs)

    mock_kafka_producer.flush.assert_called_once_with(timeout=10)


async def test_scheduler_raises_on_flush_timeout(
    scheduler: ValuationScheduler,
    mock_kafka_producer: MagicMock,
):
    claimed_jobs = [
        PortfolioValuationJob(
            portfolio_id="P1",
            security_id="S1",
            valuation_date=date(2025, 8, 11),
            epoch=1,
            correlation_id="corr-1",
        ),
    ]
    mock_kafka_producer.flush.return_value = 1

    with pytest.raises(
        RuntimeError,
        match="Delivery confirmation timed out while dispatching valuation jobs",
    ):
        await scheduler._dispatch_jobs(claimed_jobs)


async def test_scheduler_reads_max_attempts_from_environment(
    mock_kafka_producer: MagicMock, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("VALUATION_SCHEDULER_POLL_INTERVAL", "9")
    monkeypatch.setenv("VALUATION_SCHEDULER_BATCH_SIZE", "17")
    monkeypatch.setenv("VALUATION_SCHEDULER_DISPATCH_ROUNDS", "4")
    monkeypatch.setenv("VALUATION_SCHEDULER_STALE_TIMEOUT_MINUTES", "12")
    monkeypatch.setenv("VALUATION_SCHEDULER_MAX_ATTEMPTS", "6")

    with patch(
        "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.get_kafka_producer",
        return_value=mock_kafka_producer,
    ):
        scheduler = ValuationScheduler()

    assert scheduler._poll_interval == 9
    assert scheduler._batch_size == 17
    assert scheduler._dispatch_rounds_per_poll == 4
    assert scheduler._stale_timeout_minutes == 12
    assert scheduler._max_attempts == 6


@patch.object(INSTRUMENT_REPROCESSING_TRIGGERS_PENDING, "set")
async def test_scheduler_updates_pending_triggers_metric(
    mock_gauge_set,
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_repo.get_instrument_reprocessing_triggers_count.return_value = 5

    await scheduler._update_reprocessing_metrics(AsyncMock())

    mock_repo.get_instrument_reprocessing_triggers_count.assert_awaited_once()
    mock_gauge_set.assert_called_once_with(5)


async def test_scheduler_creates_persistent_job_from_instrument_trigger(
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]

    triggers = [
        InstrumentReprocessingState(
            security_id="S1",
            earliest_impacted_date=date(2025, 8, 5),
            correlation_id="corr-trigger-1",
        )
    ]
    mock_repo.claim_instrument_reprocessing_triggers.return_value = triggers

    await scheduler._process_instrument_level_triggers(AsyncMock())

    mock_repro_job_repo.create_job.assert_awaited_once_with(
        job_type="RESET_WATERMARKS",
        payload={"security_id": "S1", "earliest_impacted_date": "2025-08-05"},
        correlation_id="corr-trigger-1",
    )
    mock_repo.claim_instrument_reprocessing_triggers.assert_awaited_once_with(scheduler._batch_size)


async def test_scheduler_stop_interrupts_poll_sleep(
    scheduler: ValuationScheduler,
):
    batch_started = asyncio.Event()

    async def mark_started(*args, **kwargs):
        batch_started.set()

    async def get_session_gen():
        yield AsyncMock(spec=AsyncSession)

    with (
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.get_async_db_session",
            new=get_session_gen,
        ),
        patch.object(scheduler, "_update_reprocessing_metrics", side_effect=mark_started),
        patch.object(scheduler, "_update_queue_metrics", new=AsyncMock()),
        patch.object(scheduler, "_process_instrument_level_triggers", new=AsyncMock()),
        patch.object(scheduler, "_create_backfill_jobs", new=AsyncMock()),
        patch.object(scheduler, "_advance_watermarks", new=AsyncMock()),
        patch(
            "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.ValuationRepository"
        ) as mock_repo_factory,
    ):
        mock_repo = AsyncMock()
        mock_repo.find_and_claim_eligible_jobs.return_value = []
        mock_repo.find_and_reset_stale_jobs.return_value = 0
        mock_repo_factory.return_value = mock_repo

        scheduler._poll_interval = 60
        task = asyncio.create_task(scheduler.run())
        await batch_started.wait()
        await asyncio.sleep(0)

        scheduler.stop()

        await asyncio.wait_for(task, timeout=0.2)
