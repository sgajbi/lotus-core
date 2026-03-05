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
    mock_result.mappings.return_value.all.return_value = [
        {
            "id": 1,
            "portfolio_id": "PORT_001",
            "security_id": "AAPL_US",
            "valuation_date": date(2026, 3, 3),
            "epoch": 0,
            "status": "PROCESSING",
            "correlation_id": None,
            "failure_reason": None,
            "attempt_count": 1,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
        {
            "id": 2,
            "portfolio_id": "PORT_001",
            "security_id": "MSFT_US",
            "valuation_date": date(2026, 3, 3),
            "epoch": 0,
            "status": "PROCESSING",
            "correlation_id": None,
            "failure_reason": None,
            "attempt_count": 1,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        },
    ]
    mock_db_session.execute.return_value = mock_result

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_jobs_claimed"
    ) as claimed_metric:
        claimed_jobs = await repo.find_and_claim_eligible_jobs(batch_size=50)

    assert len(claimed_jobs) == 2
    claimed_metric.assert_called_once_with(2)


async def test_find_and_reset_stale_jobs_emits_reset_metric(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(101,), (102,), (103,)]
    mock_db_session.execute.return_value = mock_result

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(timeout_minutes=15)

    assert reset_count == 3
    reset_metric.assert_called_once_with(3)
