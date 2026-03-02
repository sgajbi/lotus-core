from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.services.operations_service import OperationsService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_ops_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.portfolio_exists.return_value = True
    return repo


@pytest.fixture
def service(mock_ops_repo: AsyncMock) -> OperationsService:
    with patch(
        "src.services.query_service.app.services.operations_service.OperationsRepository",
        return_value=mock_ops_repo,
    ):
        return OperationsService(AsyncMock(spec=AsyncSession))


async def test_get_support_overview(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_latest_business_date.return_value = date(2025, 8, 30)
    mock_ops_repo.get_current_portfolio_epoch.return_value = 2
    mock_ops_repo.get_active_reprocessing_keys_count.return_value = 1
    mock_ops_repo.get_pending_valuation_jobs_count.return_value = 4
    mock_ops_repo.get_processing_valuation_jobs_count.return_value = 2
    mock_ops_repo.get_stale_processing_valuation_jobs_count.return_value = 1
    mock_ops_repo.get_oldest_pending_valuation_date.return_value = date(2025, 8, 20)
    mock_ops_repo.get_pending_aggregation_jobs_count.return_value = 1
    mock_ops_repo.get_latest_transaction_date.return_value = date(2025, 9, 2)
    mock_ops_repo.get_position_snapshot_history_mismatch_count.return_value = 0
    mock_ops_repo.get_latest_transaction_date_as_of.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch.return_value = date(2025, 8, 30)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch_as_of.return_value = date(2025, 8, 30)

    response = await service.get_support_overview("P1")

    assert response.portfolio_id == "P1"
    assert response.business_date == date(2025, 8, 30)
    assert response.current_epoch == 2
    assert response.active_reprocessing_keys == 1
    assert response.pending_valuation_jobs == 4
    assert response.processing_valuation_jobs == 2
    assert response.stale_processing_valuation_jobs == 1
    assert response.oldest_pending_valuation_date == date(2025, 8, 20)
    assert response.valuation_backlog_age_days == 10
    assert response.pending_aggregation_jobs == 1
    assert response.latest_transaction_date == date(2025, 9, 2)
    assert response.latest_booked_transaction_date == date(2025, 8, 30)
    assert response.latest_position_snapshot_date == date(2025, 8, 30)
    assert response.latest_booked_position_snapshot_date == date(2025, 8, 30)
    assert response.position_snapshot_history_mismatch_count == 0


async def test_get_lineage_raises_when_state_missing(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_position_state.return_value = None

    with pytest.raises(ValueError, match="Lineage state not found"):
        await service.get_lineage("P1", "S1")


async def test_get_lineage_success(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_position_state.return_value = type(
        "PositionStateStub",
        (),
        {"epoch": 3, "watermark_date": date(2025, 8, 1), "status": "CURRENT"},
    )()
    mock_ops_repo.get_latest_position_history_date.return_value = date(2025, 8, 31)
    mock_ops_repo.get_latest_daily_snapshot_date.return_value = date(2025, 8, 31)
    mock_ops_repo.get_latest_valuation_job.return_value = type(
        "ValuationJobStub",
        (),
        {"valuation_date": date(2025, 8, 31), "status": "DONE"},
    )()

    response = await service.get_lineage("P1", "S1")

    assert response.portfolio_id == "P1"
    assert response.security_id == "S1"
    assert response.epoch == 3
    assert response.latest_position_history_date == date(2025, 8, 31)
    assert response.latest_daily_snapshot_date == date(2025, 8, 31)
    assert response.latest_valuation_job_status == "DONE"


async def test_get_lineage_keys(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_lineage_keys_count.return_value = 1
    mock_ops_repo.get_lineage_keys.return_value = [
        type(
            "PositionStateStub",
            (),
            {
                "security_id": "S1",
                "epoch": 2,
                "watermark_date": date(2025, 8, 1),
                "status": "CURRENT",
            },
        )()
    ]

    response = await service.get_lineage_keys(
        "P1", skip=0, limit=10, reprocessing_status="CURRENT", security_id=None
    )

    assert response.total == 1
    assert response.items[0].security_id == "S1"
    assert response.items[0].reprocessing_status == "CURRENT"


async def test_get_valuation_jobs(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_valuation_jobs_count.return_value = 1
    mock_ops_repo.get_valuation_jobs.return_value = [
        type(
            "ValuationJobStub",
            (),
            {
                "security_id": "S1",
                "valuation_date": date(2025, 8, 31),
                "status": "PENDING",
                "epoch": 1,
                "attempt_count": 0,
                "failure_reason": None,
            },
        )()
    ]

    response = await service.get_valuation_jobs("P1", skip=0, limit=20, status="PENDING")

    assert response.total == 1
    assert response.items[0].job_type == "VALUATION"
    assert response.items[0].security_id == "S1"
    assert response.items[0].business_date == date(2025, 8, 31)


async def test_get_aggregation_jobs(service: OperationsService, mock_ops_repo: AsyncMock):
    mock_ops_repo.get_aggregation_jobs_count.return_value = 1
    mock_ops_repo.get_aggregation_jobs.return_value = [
        type(
            "AggregationJobStub",
            (),
            {"aggregation_date": date(2025, 8, 31), "status": "PROCESSING"},
        )()
    ]

    response = await service.get_aggregation_jobs("P1", skip=0, limit=20, status="PROCESSING")

    assert response.total == 1
    assert response.items[0].job_type == "AGGREGATION"
    assert response.items[0].business_date == date(2025, 8, 31)


async def test_get_support_overview_raises_when_portfolio_missing(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.portfolio_exists.return_value = False

    with pytest.raises(ValueError, match="Portfolio with id P404 not found"):
        await service.get_support_overview("P404")


async def test_get_support_overview_without_business_date(
    service: OperationsService, mock_ops_repo: AsyncMock
):
    mock_ops_repo.get_latest_business_date.return_value = None
    mock_ops_repo.get_current_portfolio_epoch.return_value = 1
    mock_ops_repo.get_active_reprocessing_keys_count.return_value = 0
    mock_ops_repo.get_pending_valuation_jobs_count.return_value = 0
    mock_ops_repo.get_processing_valuation_jobs_count.return_value = 0
    mock_ops_repo.get_stale_processing_valuation_jobs_count.return_value = 0
    mock_ops_repo.get_oldest_pending_valuation_date.return_value = None
    mock_ops_repo.get_pending_aggregation_jobs_count.return_value = 0
    mock_ops_repo.get_latest_transaction_date.return_value = date(2025, 8, 31)
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch.return_value = date(2025, 8, 31)
    mock_ops_repo.get_position_snapshot_history_mismatch_count.return_value = 0

    response = await service.get_support_overview("P1")

    assert response.business_date is None
    assert response.valuation_backlog_age_days is None
    assert response.latest_booked_transaction_date is None
    assert response.latest_booked_position_snapshot_date is None
    mock_ops_repo.get_latest_transaction_date_as_of.assert_not_awaited()
    mock_ops_repo.get_latest_snapshot_date_for_current_epoch_as_of.assert_not_awaited()
