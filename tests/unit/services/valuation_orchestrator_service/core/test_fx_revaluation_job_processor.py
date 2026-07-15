"""Tests for durable FX revaluation job terminal semantics."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import ReprocessingJob
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository

from src.services.valuation_orchestrator_service.app.core.fx_revaluation_job_processor import (
    FxRevaluationJobProcessor,
)
from src.services.valuation_orchestrator_service.app.domain.fx_revaluation import (
    DirectCurrencyPair,
    FxReplayExecution,
)
from src.services.valuation_orchestrator_service.app.infrastructure.repositories import (
    fx_revaluation_repository,
)

pytestmark = pytest.mark.asyncio


def job() -> ReprocessingJob:
    """Build one claimed direct-pair replay job."""
    return ReprocessingJob(
        id=41,
        job_type="RESET_FX_WATERMARKS",
        payload={
            "from_currency": "USD",
            "to_currency": "SGD",
            "earliest_impacted_date": "2026-04-10",
        },
        status="PROCESSING",
        correlation_id="corr-fx-job",
    )


@pytest.fixture
def dependencies():
    return {
        "jobs": AsyncMock(spec=ReprocessingJobRepository),
        "watermarks": AsyncMock(spec=PositionStateRepository),
        "revaluation": AsyncMock(
            spec=fx_revaluation_repository.SqlAlchemyFxRevaluationRepository
        ),
    }


async def test_successful_replay_completes_under_job_correlation(
    dependencies: dict,
) -> None:
    observed_correlation: list[str] = []

    async def execute(**_kwargs):
        observed_correlation.append(correlation_id_var.get())
        return FxReplayExecution(
            pair=DirectCurrencyPair("USD", "SGD"),
            earliest_impacted_date=date(2026, 4, 10),
            targeted_key_count=2,
            updated_key_count=2,
        )

    dependencies["jobs"].update_job_status.return_value = True
    with patch(
        "src.services.valuation_orchestrator_service.app.core."
        "fx_revaluation_job_processor.ProcessFxRevaluationJob.execute",
        side_effect=execute,
    ):
        await FxRevaluationJobProcessor().process(job=job(), **dependencies)

    assert observed_correlation == ["corr-fx-job"]
    dependencies["jobs"].update_job_status.assert_awaited_once_with(41, "COMPLETE")


async def test_readiness_race_requeues_job_without_completing(dependencies: dict) -> None:
    execution = FxReplayExecution(
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
        targeted_key_count=0,
        updated_key_count=0,
    )
    dependencies["jobs"].update_job_status.return_value = True
    with patch(
        "src.services.valuation_orchestrator_service.app.core."
        "fx_revaluation_job_processor.ProcessFxRevaluationJob.execute",
        return_value=execution,
    ):
        await FxRevaluationJobProcessor().process(job=job(), **dependencies)

    dependencies["jobs"].update_job_status.assert_awaited_once_with(41, "PENDING")


async def test_invalid_payload_fails_job_with_supportable_reason(dependencies: dict) -> None:
    invalid = job()
    invalid.payload = {"from_currency": "USD"}
    dependencies["jobs"].update_job_status.return_value = True

    await FxRevaluationJobProcessor().process(job=invalid, **dependencies)

    args, kwargs = dependencies["jobs"].update_job_status.await_args
    assert args == (41, "FAILED")
    assert "to_currency" in kwargs["failure_reason"]


async def test_completion_ownership_loss_is_observed(dependencies: dict) -> None:
    execution = FxReplayExecution(
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
        targeted_key_count=1,
        updated_key_count=1,
    )
    dependencies["jobs"].update_job_status.return_value = False
    with (
        patch(
            "src.services.valuation_orchestrator_service.app.core."
            "fx_revaluation_job_processor.ProcessFxRevaluationJob.execute",
            return_value=execution,
        ),
        patch(
            "src.services.valuation_orchestrator_service.app.core."
            "fx_revaluation_job_processor.observe_reprocessing_stale_skips"
        ) as observe_stale,
    ):
        await FxRevaluationJobProcessor().process(job=job(), **dependencies)

    observe_stale.assert_called_once_with("fx_revaluation_complete_ownership_lost", 1)
