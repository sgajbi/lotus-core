from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    return session


async def test_find_and_claim_eligible_jobs_emits_claim_metric(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        MagicMock(
            portfolio_id="PORT_001",
            security_id="AAPL_US",
            valuation_date=date(2026, 3, 3),
            epoch=0,
        ),
        MagicMock(
            portfolio_id="PORT_001",
            security_id="MSFT_US",
            valuation_date=date(2026, 3, 3),
            epoch=0,
        ),
    ]
    mock_db_session.execute.return_value = mock_result

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_jobs_claimed"
    ) as claimed_metric:
        claimed_jobs = await repo.find_and_claim_eligible_jobs(batch_size=50)

    assert len(claimed_jobs) == 2
    claimed_metric.assert_called_once_with(2)

    claim_stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(
        claim_stmt.compile(compile_kwargs={"literal_binds": True})
    )
    assert "NOT (EXISTS" in compiled_query
    assert "portfolio_valuation_jobs_1.epoch > portfolio_valuation_jobs.epoch" in compiled_query


async def test_find_and_reset_stale_jobs_emits_reset_metric(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    select_result = MagicMock()
    select_result.all.return_value = [
        MagicMock(id=101, attempt_count=1),
        MagicMock(id=102, attempt_count=1),
        MagicMock(id=103, attempt_count=1),
    ]
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(101,), (102,), (103,)]
    mock_db_session.execute.side_effect = [select_result, mock_result]

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15, max_attempts=3)

    assert reset_count == 3
    reset_metric.assert_called_once_with(3)


async def test_find_and_reset_stale_jobs_marks_over_limit_rows_failed(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    select_result = MagicMock()
    select_result.all.return_value = [MagicMock(id=201, attempt_count=3)]
    failed_result = MagicMock()
    mock_db_session.execute.side_effect = [select_result, failed_result]

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15, max_attempts=3)

    assert reset_count == 0
    reset_metric.assert_not_called()


async def test_find_and_reset_stale_jobs_rechecks_processing_state_before_reset(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    select_result = MagicMock()
    select_result.all.return_value = [MagicMock(id=101, attempt_count=1)]
    update_result = MagicMock()
    update_result.fetchall.return_value = []
    mock_db_session.execute.side_effect = [select_result, update_result]

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15, max_attempts=3)

    assert reset_count == 0
    reset_metric.assert_not_called()
    update_stmt = mock_db_session.execute.await_args_list[1].args[0]
    compiled_query = str(update_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_valuation_jobs.status = 'PROCESSING'" in compiled_query


async def test_get_job_queue_stats_returns_pending_failed_and_oldest_pending(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    oldest_pending = datetime(2026, 3, 3, tzinfo=timezone.utc)

    row = MagicMock(
        pending_count=5,
        failed_count=2,
        oldest_pending_created_at=oldest_pending,
    )
    result = MagicMock()
    result.one.return_value = row
    mock_db_session.execute.return_value = result

    queue_stats = await repo.get_job_queue_stats()

    assert queue_stats == {
        "pending_count": 5,
        "failed_count": 2,
        "oldest_pending_created_at": oldest_pending,
    }
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_valuation_jobs_1.epoch > portfolio_valuation_jobs.epoch" in compiled_query
