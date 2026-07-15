"""Tests for durable FX revaluation job terminal semantics."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository

from src.services.valuation_orchestrator_service.app.core.fx_revaluation_job_processor import (
    FxRevaluationJobProcessor,
)
from src.services.valuation_orchestrator_service.app.domain.fx_revaluation import (
    ClaimedFxRevaluationJob,
    DirectCurrencyPair,
    FxReplayExecution,
    RejectedFxRevaluationJob,
)
from src.services.valuation_orchestrator_service.app.infrastructure.repositories import (
    fx_revaluation_repository,
)

pytestmark = pytest.mark.asyncio


def job() -> ClaimedFxRevaluationJob:
    """Build one claimed direct-pair replay job."""
    return ClaimedFxRevaluationJob(
        job_id=41,
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
        correlation_id="corr-fx-job",
        attempt_count=1,
    )


@pytest.fixture
def dependencies():
    return {
        "jobs": AsyncMock(spec=ReprocessingJobRepository),
        "watermarks": AsyncMock(spec=PositionStateRepository),
        "revaluation": AsyncMock(spec=fx_revaluation_repository.SqlAlchemyFxRevaluationRepository),
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


async def test_no_affected_positions_complete_after_bounded_visibility_retry(
    dependencies: dict,
) -> None:
    execution = FxReplayExecution(
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
        targeted_key_count=0,
        updated_key_count=0,
    )
    bounded_job = ClaimedFxRevaluationJob(
        job_id=42,
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
        correlation_id="corr-no-impact",
        attempt_count=3,
    )
    dependencies["jobs"].update_job_status.return_value = True
    with patch(
        "src.services.valuation_orchestrator_service.app.core."
        "fx_revaluation_job_processor.ProcessFxRevaluationJob.execute",
        return_value=execution,
    ):
        await FxRevaluationJobProcessor(no_impact_attempt_limit=3).process(
            job=bounded_job,
            **dependencies,
        )

    dependencies["jobs"].update_job_status.assert_awaited_once_with(42, "COMPLETE")


async def test_invalid_payload_fails_job_with_supportable_reason(dependencies: dict) -> None:
    invalid = RejectedFxRevaluationJob(
        job_id=41,
        rejection_reason="invalid_fx_revaluation_job_payload: missing to_currency",
        correlation_id="corr-fx-job",
    )
    dependencies["jobs"].update_job_status.return_value = True

    await FxRevaluationJobProcessor().process(job=invalid, **dependencies)

    args, kwargs = dependencies["jobs"].update_job_status.await_args
    assert args == (41, "FAILED")
    assert kwargs["failure_reason"] == ("invalid_fx_revaluation_job_payload: missing to_currency")


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
