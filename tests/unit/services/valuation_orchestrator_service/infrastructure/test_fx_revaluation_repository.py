"""Unit contract tests for the PostgreSQL FX revaluation adapter."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.valuation_orchestrator_service.app.domain.fx_revaluation import (
    ClaimedFxRevaluationJob,
    DirectCurrencyPair,
    FxRateCorrection,
    RejectedFxRevaluationJob,
)
from src.services.valuation_orchestrator_service.app.infrastructure.repositories import (
    fx_revaluation_repository,
)

pytestmark = pytest.mark.asyncio


async def test_find_open_position_keys_uses_set_based_direct_pair_query() -> None:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.all.return_value = [
        MagicMock(portfolio_id="P-SGD", security_id="USD-BOND", epoch=2),
    ]
    session.execute.return_value = result
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(session)

    keys = await repository.find_open_position_keys(
        pair=DirectCurrencyPair("USD", "SGD"),
        effective_date=date(2026, 4, 10),
    )

    assert [(key.portfolio_id, key.security_id, key.epoch) for key in keys] == [
        ("P-SGD", "USD-BOND", 2)
    ]
    statement = session.execute.await_args.args[0]
    sql = str(statement)
    assert "position_history" in sql
    assert "position_state" in sql
    assert "instruments" in sql
    assert "portfolios" in sql
    assert "row_number() OVER" in sql


async def test_stage_durable_replay_uses_pair_scoped_pending_upsert() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(session)
    correction = FxRateCorrection(
        pair=DirectCurrencyPair("USD", "SGD"),
        effective_date=date(2026, 4, 10),
        content_hash="sha256:" + ("a" * 64),
        generated_at=datetime(2026, 4, 10, 8, tzinfo=timezone.utc),
    )

    await repository.stage_durable_replay(
        correction=correction,
        correlation_id="corr-fx",
    )

    quarantine_statement, quarantine_parameters = session.execute.await_args_list[0].args
    statement, parameters = session.execute.await_args_list[1].args
    quarantine_sql = str(quarantine_statement)
    sql = str(statement)
    assert "pg_input_is_valid" in quarantine_sql
    assert "status = 'FAILED'" in quarantine_sql
    assert quarantine_parameters == {
        "from_currency": "USD",
        "to_currency": "SGD",
    }
    assert "RESET_FX_WATERMARKS" in sql
    assert "ON CONFLICT ((payload->>'from_currency'), (payload->>'to_currency'))" in sql
    assert "LEAST" in sql
    assert "CAST(:generated_at AS timestamptz)" in sql
    assert "COALESCE(reprocessing_jobs.payload->>'content_hash', '')" in sql
    assert "GREATEST" in sql
    assert parameters["from_currency"] == "USD"
    assert parameters["to_currency"] == "SGD"
    assert parameters["effective_date"] == date(2026, 4, 10)
    assert parameters["content_hash"] == correction.content_hash
    assert parameters["attempt_count"] == 0
    assert parameters["correlation_id"] == "corr-fx"
    assert session.execute.await_count == 2


async def test_affected_keys_include_open_and_later_positions_without_duplicates() -> None:
    session = AsyncMock(spec=AsyncSession)
    open_result = MagicMock()
    open_result.all.return_value = [
        MagicMock(portfolio_id="P1", security_id="USD-BOND", epoch=0),
    ]
    future_result = MagicMock()
    future_result.all.return_value = [
        MagicMock(portfolio_id="P1", security_id="USD-BOND", epoch=0),
        MagicMock(portfolio_id="P2", security_id="USD-EQUITY", epoch=1),
    ]
    session.execute.side_effect = [open_result, future_result]
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(session)

    keys = await repository.find_affected_position_keys(
        pair=DirectCurrencyPair("USD", "SGD"),
        earliest_impacted_date=date(2026, 4, 10),
    )

    assert [(key.portfolio_id, key.security_id, key.epoch) for key in keys] == [
        ("P1", "USD-BOND", 0),
        ("P2", "USD-EQUITY", 1),
    ]
    assert session.execute.await_count == 2


async def test_claim_pending_jobs_uses_fx_queue_type() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(session)

    with patch(
        "src.services.valuation_orchestrator_service.app.infrastructure.repositories."
        "fx_revaluation_repository.ReprocessingJobRepository",
        autospec=ReprocessingJobRepository,
    ) as jobs:
        jobs.return_value.find_and_claim_jobs.return_value = []
        claimed = await repository.claim_pending_jobs(batch_size=25)

    assert claimed == []
    jobs.return_value.find_and_claim_jobs.assert_awaited_once_with(
        "RESET_FX_WATERMARKS",
        25,
    )


async def test_claim_pending_jobs_maps_orm_payload_to_domain_work() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(session)
    row = MagicMock(
        id=71,
        payload={
            "from_currency": "usd",
            "to_currency": "sgd",
            "earliest_impacted_date": "2026-04-10",
        },
        correlation_id="corr-71",
        attempt_count=2,
    )

    with patch(
        "src.services.valuation_orchestrator_service.app.infrastructure.repositories."
        "fx_revaluation_repository.ReprocessingJobRepository",
        autospec=ReprocessingJobRepository,
    ) as jobs:
        jobs.return_value.find_and_claim_jobs.return_value = [row]
        claimed = await repository.claim_pending_jobs(batch_size=1)

    assert claimed == [
        ClaimedFxRevaluationJob(
            job_id=71,
            pair=DirectCurrencyPair("USD", "SGD"),
            earliest_impacted_date=date(2026, 4, 10),
            correlation_id="corr-71",
            attempt_count=2,
        )
    ]


async def test_claim_pending_jobs_returns_rejected_work_for_invalid_payload() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = fx_revaluation_repository.SqlAlchemyFxRevaluationRepository(session)
    row = MagicMock(
        id=72,
        payload={"from_currency": "USD"},
        correlation_id="corr-72",
    )

    with patch(
        "src.services.valuation_orchestrator_service.app.infrastructure.repositories."
        "fx_revaluation_repository.ReprocessingJobRepository",
        autospec=ReprocessingJobRepository,
    ) as jobs:
        jobs.return_value.find_and_claim_jobs.return_value = [row]
        claimed = await repository.claim_pending_jobs(batch_size=1)

    assert len(claimed) == 1
    assert isinstance(claimed[0], RejectedFxRevaluationJob)
    assert claimed[0].job_id == 72
    assert "to_currency" in claimed[0].rejection_reason
