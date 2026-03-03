# tests/unit/services/calculators/position_valuation_calculator/core/test_reprocessing_worker.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import ReprocessingJob
from src.services.calculators.position_valuation_calculator.app.core.reprocessing_worker import ReprocessingWorker
from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import ValuationRepository
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.reprocessing_job_repository import ReprocessingJobRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_dependencies():
    """Mocks all repository dependencies for the ReprocessingWorker."""
    mock_valuation_repo = AsyncMock(spec=ValuationRepository)
    mock_state_repo = AsyncMock(spec=PositionStateRepository)
    mock_repro_job_repo = AsyncMock(spec=ReprocessingJobRepository)
    
    mock_db_session = AsyncMock(spec=AsyncSession)
    mock_transaction = AsyncMock()
    mock_db_session.begin.return_value = mock_transaction
    
    async def get_session_gen():
        yield mock_db_session

    with patch(
        "src.services.calculators.position_valuation_calculator.app.core.reprocessing_worker.get_async_db_session", new=get_session_gen
    ), patch(
        "src.services.calculators.position_valuation_calculator.app.core.reprocessing_worker.ValuationRepository", return_value=mock_valuation_repo
    ), patch(
        "src.services.calculators.position_valuation_calculator.app.core.reprocessing_worker.PositionStateRepository", return_value=mock_state_repo
    ), patch(
        "src.services.calculators.position_valuation_calculator.app.core.reprocessing_worker.ReprocessingJobRepository", return_value=mock_repro_job_repo
    ):
        yield {
            "valuation_repo": mock_valuation_repo,
            "state_repo": mock_state_repo,
            "repro_job_repo": mock_repro_job_repo
        }

async def test_worker_processes_reset_watermarks_job(mock_dependencies):
    """
    GIVEN a pending RESET_WATERMARKS job
    WHEN the worker processes a batch
    THEN it should fan-out the watermark updates and mark the job as complete.
    """
    # ARRANGE
    worker = ReprocessingWorker(poll_interval=0.1) # Short poll for test
    mock_repro_job_repo = mock_dependencies["repro_job_repo"]
    mock_valuation_repo = mock_dependencies["valuation_repo"]
    mock_state_repo = mock_dependencies["state_repo"]

    job_payload = {"security_id": "S1", "earliest_impacted_date": "2025-08-10"}
    pending_job = ReprocessingJob(
        id=1, job_type="RESET_WATERMARKS", payload=job_payload, status="PENDING"
    )
    
    mock_repro_job_repo.find_and_claim_jobs.return_value = [pending_job]
    mock_valuation_repo.find_portfolios_for_security.return_value = ["P1", "P2"]
    mock_state_repo.update_watermarks_if_older.return_value = 2

    # ACT
    await worker._process_batch() # Call the internal method for one deterministic cycle

    # ASSERT
    # 1. Claimed the job
    mock_repro_job_repo.find_and_claim_jobs.assert_awaited_once_with('RESET_WATERMARKS', 10)

    # 2. Fanned out the work
    mock_valuation_repo.find_portfolios_for_security.assert_awaited_once_with("S1")
    mock_state_repo.update_watermarks_if_older.assert_awaited_once_with(
        keys=[("P1", "S1"), ("P2", "S1")],
        new_watermark_date=date(2025, 8, 9) # date - 1 day
    )
    
    # 3. Marked the job as complete
    mock_repro_job_repo.update_job_status.assert_awaited_once_with(1, "COMPLETE")


async def test_worker_reads_poll_and_batch_from_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REPROCESSING_WORKER_POLL_INTERVAL_SECONDS", "7")
    monkeypatch.setenv("REPROCESSING_WORKER_BATCH_SIZE", "21")

    worker = ReprocessingWorker()

    assert worker._poll_interval == 7
    assert worker._batch_size == 21
