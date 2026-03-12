from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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
    return MagicMock(spec=KafkaProducer)


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

    with patch.object(POSITION_STATE_WATERMARK_LAG_DAYS, "labels") as mock_gauge_labels:
        await scheduler._create_backfill_jobs(AsyncMock())

        assert mock_job_repo.upsert_job.call_count == 3
        first_call_args = mock_job_repo.upsert_job.call_args_list[0].kwargs
        assert first_call_args["valuation_date"] == date(2025, 8, 10)
        mock_gauge_labels.assert_called_once_with(portfolio_id="P1", security_id="S1")
        mock_gauge_labels.return_value.set.assert_called_once_with(expected_lag)


async def test_scheduler_skips_jobs_for_keys_with_no_position_history(
    scheduler: ValuationScheduler,
    mock_dependencies: dict,
):
    mock_repo = mock_dependencies["repo"]
    mock_job_repo = mock_dependencies["job_repo"]

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

    mock_job_repo.upsert_job.assert_not_called()


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
    mock_repo.find_contiguous_snapshot_dates.return_value = advancable_dates

    await scheduler._advance_watermarks(AsyncMock())

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
    mock_repo.find_contiguous_snapshot_dates.return_value = advancable_dates
    mock_state_repo.bulk_update_states.return_value = 1

    with patch(
        "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.logger.warning"
    ) as mock_warning:
        await scheduler._advance_watermarks(AsyncMock())

    mock_warning.assert_called_once()
    warning_kwargs = mock_warning.call_args.kwargs
    assert warning_kwargs["extra"]["prepared_count"] == 2
    assert warning_kwargs["extra"]["updated_count"] == 1
    assert warning_kwargs["extra"]["stale_skipped_count"] == 1


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

    with patch(
        "src.services.valuation_orchestrator_service.app.core.valuation_scheduler.logger.warning"
    ) as mock_warning:
        await scheduler._advance_watermarks(AsyncMock())

    mock_warning.assert_called_once()
    warning_kwargs = mock_warning.call_args.kwargs
    assert warning_kwargs["extra"]["prepared_count"] == 2
    assert warning_kwargs["extra"]["updated_count"] == 1
    assert warning_kwargs["extra"]["stale_skipped_count"] == 1


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

    mock_kafka_producer.publish_message.assert_called_once()
    mock_kafka_producer.flush.assert_called_once_with(timeout=10)


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
    mock_repo.claim_instrument_reprocessing_triggers.assert_awaited_once_with(
        scheduler._batch_size
    )
