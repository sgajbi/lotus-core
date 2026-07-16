"""Domain-focused tests for effective-dated FX correction scheduling."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, call

import pytest

from src.services.valuation_orchestrator_service.app.application.process_fx_rate_correction import (
    ProcessFxRateCorrection,
)
from src.services.valuation_orchestrator_service.app.domain.fx_revaluation import (
    DirectCurrencyPair,
    FxRateCorrection,
    PositionValuationKey,
)

pytestmark = pytest.mark.domain


def correction(effective_date: date = date(2026, 4, 10)) -> FxRateCorrection:
    """Build canonical USD/SGD correction evidence."""
    return FxRateCorrection(
        pair=DirectCurrencyPair(" usd ", "sgd"),
        effective_date=effective_date,
        content_hash="sha256:" + ("a" * 64),
        generated_at=datetime(2026, 4, 10, 8, tzinfo=timezone.utc),
    )


def use_case() -> tuple[ProcessFxRateCorrection, AsyncMock, AsyncMock]:
    """Build the use case with behavior-observable ports."""
    repository = AsyncMock()
    valuation_jobs = AsyncMock()
    return (
        ProcessFxRateCorrection(
            repository=repository,
            valuation_jobs=valuation_jobs,
        ),
        repository,
        valuation_jobs,
    )


@pytest.mark.asyncio
async def test_current_correction_queues_immediate_jobs_without_replay() -> None:
    handler, repository, valuation_jobs = use_case()
    repository.latest_business_date.return_value = date(2026, 4, 10)
    repository.find_position_keys_requiring_revaluation.return_value = [
        PositionValuationKey("P-SGD", "USD-BOND", 3),
    ]

    result = await handler.execute(correction=correction(), correlation_id="corr-fx-1")

    assert result.immediate_job_count == 1
    assert result.pair.key == "USD->SGD"
    assert result.durable_replay_staged is False
    repository.stage_durable_replay.assert_not_awaited()
    valuation_jobs.upsert_job.assert_awaited_once_with(
        portfolio_id="P-SGD",
        security_id="USD-BOND",
        valuation_date=date(2026, 4, 10),
        epoch=3,
        correlation_id="corr-fx-1",
    )


@pytest.mark.asyncio
async def test_backdated_correction_queues_visible_keys_and_preserves_replay() -> None:
    handler, repository, valuation_jobs = use_case()
    repository.latest_business_date.return_value = date(2026, 4, 15)
    repository.find_position_keys_requiring_revaluation.return_value = [
        PositionValuationKey("P1", "USD-EQUITY", 0),
        PositionValuationKey("P2", "USD-BOND", 2),
    ]
    parent = AsyncMock()
    parent.attach_mock(repository.stage_durable_replay, "stage_replay")
    parent.attach_mock(valuation_jobs.upsert_job, "upsert_job")

    result = await handler.execute(correction=correction(), correlation_id="corr-backdated")

    assert result.durable_replay_staged is True
    assert result.immediate_job_count == 2
    assert parent.mock_calls[0] == call.stage_replay(
        correction=correction(),
        correlation_id="corr-backdated",
    )
    assert valuation_jobs.upsert_job.await_count == 2


@pytest.mark.parametrize("latest_business_date", [None, date(2026, 4, 9)])
@pytest.mark.asyncio
async def test_out_of_horizon_correction_only_stages_durable_replay(
    latest_business_date: date | None,
) -> None:
    handler, repository, valuation_jobs = use_case()
    repository.latest_business_date.return_value = latest_business_date

    result = await handler.execute(correction=correction(), correlation_id="corr-future")

    assert result.immediate_job_count == 0
    repository.stage_durable_replay.assert_awaited_once()
    repository.find_position_keys_requiring_revaluation.assert_not_awaited()
    valuation_jobs.upsert_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_correction_without_visible_positions_relies_on_position_readiness() -> None:
    handler, repository, valuation_jobs = use_case()
    repository.latest_business_date.return_value = date(2026, 4, 10)
    repository.find_position_keys_requiring_revaluation.return_value = []

    result = await handler.execute(correction=correction(), correlation_id="corr-race")

    assert result.durable_replay_staged is False
    assert result.immediate_job_count == 0
    repository.stage_durable_replay.assert_not_awaited()
    valuation_jobs.upsert_job.assert_not_awaited()


def test_direct_currency_pair_rejects_identity_conversion() -> None:
    with pytest.raises(ValueError, match="two different currencies"):
        DirectCurrencyPair("USD", "usd")
