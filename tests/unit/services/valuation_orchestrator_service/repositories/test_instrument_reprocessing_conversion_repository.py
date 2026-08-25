from datetime import date
from unittest.mock import AsyncMock

import pytest
from portfolio_common.database_models import InstrumentReprocessingState, ReprocessingJob
from portfolio_common.reprocessing_job_repository import (
    ReprocessingJobRepository,
    ResetWatermarksStageOutcome,
    ResetWatermarksStageResult,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.valuation_orchestrator_service.app.repositories import (
    instrument_reprocessing_conversion_repository as conversion_repository,
)
from src.services.valuation_orchestrator_service.app.repositories.valuation_repository import (
    ValuationRepository,
)


@pytest.mark.asyncio
async def test_convert_pending_triggers_reports_created_and_coalesced_outcomes() -> None:
    repository = conversion_repository.InstrumentReprocessingConversionRepository(
        AsyncMock(spec=AsyncSession)
    )
    trigger_repository = AsyncMock(spec=ValuationRepository)
    job_repository = AsyncMock(spec=ReprocessingJobRepository)
    repository._trigger_repository = trigger_repository
    repository._job_repository = job_repository
    trigger_repository.claim_instrument_reprocessing_triggers.return_value = [
        InstrumentReprocessingState(
            security_id="BOND-1",
            earliest_impacted_date=date(2025, 1, 2),
            correlation_id="corr-bond-1",
        ),
        InstrumentReprocessingState(
            security_id="BOND-2",
            earliest_impacted_date=date(2025, 1, 3),
            correlation_id="corr-bond-2",
        ),
    ]
    job_repository.stage_reset_watermarks_job.side_effect = [
        ResetWatermarksStageResult(
            job=ReprocessingJob(id=1),
            outcome=ResetWatermarksStageOutcome.CREATED,
        ),
        ResetWatermarksStageResult(
            job=ReprocessingJob(id=2),
            outcome=ResetWatermarksStageOutcome.COALESCED_PENDING,
        ),
    ]

    result = await repository.convert_pending_triggers(batch_size=25)

    assert result == conversion_repository.InstrumentTriggerConversionResult(
        claimed_count=2,
        created_count=1,
        coalesced_pending_count=1,
    )
    trigger_repository.claim_instrument_reprocessing_triggers.assert_awaited_once_with(25)
    job_repository.lock_reset_watermarks_replay_identities.assert_awaited_once_with(
        ["BOND-1", "BOND-2"]
    )
    assert job_repository.mock_calls[0].args == (["BOND-1", "BOND-2"],)
    assert job_repository.stage_reset_watermarks_job.await_count == 2


@pytest.mark.asyncio
async def test_convert_pending_triggers_returns_zero_result_without_job_writes() -> None:
    repository = conversion_repository.InstrumentReprocessingConversionRepository(
        AsyncMock(spec=AsyncSession)
    )
    trigger_repository = AsyncMock(spec=ValuationRepository)
    job_repository = AsyncMock(spec=ReprocessingJobRepository)
    repository._trigger_repository = trigger_repository
    repository._job_repository = job_repository
    trigger_repository.claim_instrument_reprocessing_triggers.return_value = []

    result = await repository.convert_pending_triggers(batch_size=10)

    assert result == conversion_repository.InstrumentTriggerConversionResult(0, 0, 0)
    job_repository.lock_reset_watermarks_replay_identities.assert_not_awaited()
    job_repository.stage_reset_watermarks_job.assert_not_awaited()


def test_conversion_result_rejects_unaccounted_claims() -> None:
    with pytest.raises(
        ValueError,
        match="Every claimed trigger must have one durable staging outcome",
    ):
        conversion_repository.InstrumentTriggerConversionResult(
            claimed_count=2,
            created_count=1,
            coalesced_pending_count=0,
        )
