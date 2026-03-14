from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.operations_repository import (
    OperationsRepository,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> OperationsRepository:
    return OperationsRepository(mock_db_session)


def mock_execute_scalar_one_or_none(mock_db_session: AsyncMock, value):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    mock_db_session.execute = AsyncMock(return_value=mock_result)


def mock_execute_scalar_one(mock_db_session: AsyncMock, value):
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = value
    mock_db_session.execute = AsyncMock(return_value=mock_result)


async def test_get_current_portfolio_epoch(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, 3)

    value = await repository.get_current_portfolio_epoch("P1")

    assert value == 3
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(position_state.epoch)" in compiled.lower()
    assert "position_state.portfolio_id = 'P1'" in compiled


async def test_get_active_reprocessing_keys_count(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 2)

    value = await repository.get_active_reprocessing_keys_count("P1")

    assert value == 2
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.status = 'REPROCESSING'" in compiled


async def test_get_reprocessing_health_summary(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    reference_now = datetime(2025, 8, 31, 12, 0, tzinfo=timezone.utc)
    mock_row = MagicMock(
        active_keys=3,
        stale_reprocessing_keys=1,
        oldest_reprocessing_watermark_date=date(2025, 8, 20),
    )
    mock_result = MagicMock()
    mock_result.one.return_value = mock_row
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_reprocessing_health_summary(
        "P1", stale_minutes=15, reference_now=reference_now
    )

    assert value.active_keys == 3
    assert value.stale_reprocessing_keys == 1
    assert value.oldest_reprocessing_watermark_date == date(2025, 8, 20)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.status = 'REPROCESSING'" in compiled
    assert "position_state.updated_at < '2025-08-31 11:45:00+00:00'" in compiled


async def test_get_valuation_job_health_summary(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    reference_now = datetime(2025, 8, 31, 12, 0, tzinfo=timezone.utc)
    mock_row = MagicMock(
        pending_jobs=4,
        processing_jobs=2,
        stale_processing_jobs=1,
        failed_jobs=3,
        failed_jobs_last_hours=1,
        oldest_open_job_date=date(2025, 8, 1),
    )
    mock_result = MagicMock()
    mock_result.one.return_value = mock_row
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_valuation_job_health_summary(
        "P1",
        stale_minutes=15,
        failed_window_hours=24,
        reference_now=reference_now,
    )

    assert value.pending_jobs == 4
    assert value.processing_jobs == 2
    assert value.stale_processing_jobs == 1
    assert value.failed_jobs == 3
    assert value.failed_jobs_last_hours == 1
    assert value.oldest_open_job_date == date(2025, 8, 1)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_valuation_jobs" in compiled.lower()
    assert "FILTER (WHERE portfolio_valuation_jobs.status IN ('PENDING', 'PROCESSING'))" in compiled
    assert "FILTER (WHERE portfolio_valuation_jobs.status = 'FAILED')" in compiled
    assert "portfolio_valuation_jobs.updated_at < '2025-08-31 11:45:00+00:00'" in compiled
    assert "portfolio_valuation_jobs.updated_at >= '2025-08-30 12:00:00+00:00'" in compiled


async def test_get_aggregation_job_health_summary(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    reference_now = datetime(2025, 8, 31, 12, 0, tzinfo=timezone.utc)
    mock_row = MagicMock(
        pending_jobs=5,
        processing_jobs=1,
        stale_processing_jobs=0,
        failed_jobs=2,
        failed_jobs_last_hours=1,
        oldest_open_job_date=date(2025, 8, 10),
    )
    mock_result = MagicMock()
    mock_result.one.return_value = mock_row
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_aggregation_job_health_summary(
        "P1",
        stale_minutes=15,
        failed_window_hours=24,
        reference_now=reference_now,
    )

    assert value.pending_jobs == 5
    assert value.processing_jobs == 1
    assert value.stale_processing_jobs == 0
    assert value.failed_jobs == 2
    assert value.failed_jobs_last_hours == 1
    assert value.oldest_open_job_date == date(2025, 8, 10)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_aggregation_jobs" in compiled.lower()
    assert (
        "FILTER (WHERE portfolio_aggregation_jobs.status IN ('PENDING', 'PROCESSING'))" in compiled
    )
    assert "FILTER (WHERE portfolio_aggregation_jobs.status = 'FAILED')" in compiled
    assert "portfolio_aggregation_jobs.updated_at < '2025-08-31 11:45:00+00:00'" in compiled
    assert "portfolio_aggregation_jobs.updated_at >= '2025-08-30 12:00:00+00:00'" in compiled


async def test_get_analytics_export_job_health_summary(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    reference_now = datetime(2025, 8, 31, 12, 0, tzinfo=timezone.utc)
    mock_row = MagicMock(
        accepted_jobs=2,
        running_jobs=1,
        stale_running_jobs=1,
        failed_jobs=3,
        failed_jobs_last_hours=2,
        oldest_open_job_created_at=datetime(2025, 8, 10, 9, 0, tzinfo=timezone.utc),
    )
    mock_result = MagicMock()
    mock_result.one.return_value = mock_row
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_analytics_export_job_health_summary(
        "P1",
        stale_minutes=15,
        failed_window_hours=24,
        reference_now=reference_now,
    )

    assert value.accepted_jobs == 2
    assert value.running_jobs == 1
    assert value.stale_running_jobs == 1
    assert value.failed_jobs == 3
    assert value.failed_jobs_last_hours == 2
    assert value.oldest_open_job_created_at == datetime(2025, 8, 10, 9, 0, tzinfo=timezone.utc)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from analytics_export_jobs" in compiled.lower()
    assert "FILTER (WHERE analytics_export_jobs.status = 'accepted')" in compiled
    assert "FILTER (WHERE analytics_export_jobs.status = 'running')" in compiled
    assert "FILTER (WHERE analytics_export_jobs.status = 'failed')" in compiled
    assert "analytics_export_jobs.updated_at < '2025-08-31 11:45:00+00:00'" in compiled
    assert "analytics_export_jobs.updated_at >= '2025-08-30 12:00:00+00:00'" in compiled


async def test_get_latest_transaction_date(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 31))

    value = await repository.get_latest_transaction_date("P1")

    assert value == date(2025, 8, 31)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(date(transactions.transaction_date))" in compiled.lower()
    assert "transactions.portfolio_id = 'P1'" in compiled


async def test_get_latest_transaction_date_as_of(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 15))

    value = await repository.get_latest_transaction_date_as_of("P1", date(2025, 8, 20))

    assert value == date(2025, 8, 15)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "date(transactions.transaction_date) <= '2025-08-20'" in compiled


async def test_get_latest_business_date(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2026, 3, 1))

    value = await repository.get_latest_business_date()

    assert value == date(2026, 3, 1)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from business_dates" in compiled.lower()


async def test_get_latest_snapshot_date_for_current_epoch(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 30))

    value = await repository.get_latest_snapshot_date_for_current_epoch("P1")

    assert value == date(2025, 8, 30)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from daily_position_snapshots" in compiled.lower()
    assert "join position_state on" in compiled.lower()
    assert "daily_position_snapshots.epoch = position_state.epoch" in compiled


async def test_get_latest_snapshot_date_for_current_epoch_as_of(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 12))

    value = await repository.get_latest_snapshot_date_for_current_epoch_as_of(
        "P1", date(2025, 8, 20)
    )

    assert value == date(2025, 8, 12)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "daily_position_snapshots.date <= '2025-08-20'" in compiled


async def test_get_position_snapshot_history_mismatch_count(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 0)

    value = await repository.get_position_snapshot_history_mismatch_count("P1")

    assert value == 0
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from (select position_history.portfolio_id" in compiled.lower()
    assert "left outer join" in compiled.lower()
    assert "daily_position_snapshots" in compiled.lower()


async def test_get_position_state(repository: OperationsRepository, mock_db_session: AsyncMock):
    mock_state = object()
    mock_execute_scalar_one_or_none(mock_db_session, mock_state)

    value = await repository.get_position_state("P1", "S1")

    assert value is mock_state
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.security_id = 'S1'" in compiled


async def test_get_latest_position_history_date(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 20))

    value = await repository.get_latest_position_history_date("P1", "S1", 2)

    assert value == date(2025, 8, 20)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(position_history.position_date)" in compiled.lower()
    assert "position_history.epoch = 2" in compiled


async def test_get_latest_daily_snapshot_date(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one_or_none(mock_db_session, date(2025, 8, 22))

    value = await repository.get_latest_daily_snapshot_date("P1", "S1", 2)

    assert value == date(2025, 8, 22)
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "max(daily_position_snapshots.date)" in compiled.lower()
    assert "daily_position_snapshots.epoch = 2" in compiled


async def test_get_latest_valuation_job(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_job = object()
    mock_execute_scalar_one_or_none(mock_db_session, mock_job)

    value = await repository.get_latest_valuation_job("P1", "S1", 2)

    assert value is mock_job
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_valuation_jobs" in compiled.lower()
    assert "portfolio_valuation_jobs.epoch = 2" in compiled
    assert (
        "ORDER BY portfolio_valuation_jobs.valuation_date DESC, portfolio_valuation_jobs.id DESC"
        in compiled
    )


async def test_get_lineage_keys_count_with_filters(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 5)

    value = await repository.get_lineage_keys_count(
        portfolio_id="P1", reprocessing_status="CURRENT", security_id="S1"
    )

    assert value == 5
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.status = 'CURRENT'" in compiled
    assert "position_state.security_id = 'S1'" in compiled


async def test_get_lineage_keys_query(repository: OperationsRepository, mock_db_session: AsyncMock):
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = ["k1", "k2"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_lineage_keys(portfolio_id="P1", skip=5, limit=10)

    assert value == ["k1", "k2"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "CASE WHEN (position_state.status = 'REPROCESSING') THEN 0" in compiled
    assert "max(position_history.position_date)" in compiled
    assert "DESC NULLS LAST" in compiled
    assert "position_state.security_id ASC" in compiled
    assert "LIMIT 10 OFFSET 5" in compiled
    assert "latest_position_history_date" in compiled
    assert "latest_daily_snapshot_date" in compiled
    assert "latest_valuation_job_date" in compiled
    assert "latest_valuation_job_status" in compiled


async def test_get_valuation_jobs_count_with_status(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 7)

    value = await repository.get_valuation_jobs_count(portfolio_id="P1", status="PENDING")

    assert value == 7
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_valuation_jobs" in compiled.lower()
    assert "portfolio_valuation_jobs.status = 'PENDING'" in compiled


async def test_get_valuation_jobs_query(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    reference_now = datetime(2025, 8, 31, 12, 0, tzinfo=timezone.utc)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["job1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_valuation_jobs(
        portfolio_id="P1",
        skip=0,
        limit=20,
        status=None,
        reference_now=reference_now,
    )

    assert value == ["job1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "CASE WHEN (portfolio_valuation_jobs.status = 'FAILED')" in compiled
    assert "portfolio_valuation_jobs.updated_at < '2025-08-31 11:45:00+00:00'" in compiled
    assert "portfolio_valuation_jobs.valuation_date ASC" in compiled
    assert "LIMIT 20 OFFSET 0" in compiled


async def test_get_aggregation_jobs_count_with_status(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 4)

    value = await repository.get_aggregation_jobs_count(portfolio_id="P1", status="PROCESSING")

    assert value == 4
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_aggregation_jobs" in compiled.lower()
    assert "portfolio_aggregation_jobs.status = 'PROCESSING'" in compiled


async def test_get_aggregation_jobs_query(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    reference_now = datetime(2025, 8, 31, 12, 0, tzinfo=timezone.utc)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["agg1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_aggregation_jobs(
        portfolio_id="P1",
        skip=2,
        limit=5,
        status=None,
        reference_now=reference_now,
    )

    assert value == ["agg1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "CASE WHEN (portfolio_aggregation_jobs.status = 'FAILED')" in compiled
    assert "portfolio_aggregation_jobs.updated_at < '2025-08-31 11:45:00+00:00'" in compiled
    assert "portfolio_aggregation_jobs.aggregation_date ASC" in compiled
    assert "LIMIT 5 OFFSET 2" in compiled


async def test_portfolio_exists_true(repository: OperationsRepository, mock_db_session: AsyncMock):
    mock_execute_scalar_one_or_none(mock_db_session, "P1")

    exists = await repository.portfolio_exists("P1")

    assert exists is True


async def test_portfolio_exists_false(repository: OperationsRepository, mock_db_session: AsyncMock):
    mock_execute_scalar_one_or_none(mock_db_session, None)

    exists = await repository.portfolio_exists("P404")

    assert exists is False


async def test_get_latest_financial_reconciliation_control_stage(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_stage = object()
    mock_execute_scalar_one_or_none(mock_db_session, mock_stage)

    value = await repository.get_latest_financial_reconciliation_control_stage("P1")

    assert value is mock_stage
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from pipeline_stage_state" in compiled.lower()
    assert "pipeline_stage_state.stage_name = 'FINANCIAL_RECONCILIATION'" in compiled
    assert "ORDER BY pipeline_stage_state.business_date DESC" in compiled


async def test_get_lineage_keys_query_with_filters(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = ["k1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_lineage_keys(
        portfolio_id="P1", skip=0, limit=10, reprocessing_status="CURRENT", security_id="S1"
    )

    assert value == ["k1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "position_state.status = 'CURRENT'" in compiled
    assert "position_state.security_id = 'S1'" in compiled


async def test_get_valuation_jobs_query_with_status(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["job1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_valuation_jobs(
        portfolio_id="P1", skip=0, limit=20, status="PENDING"
    )

    assert value == ["job1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_valuation_jobs.status = 'PENDING'" in compiled


async def test_get_aggregation_jobs_query_with_status(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["agg1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_aggregation_jobs(
        portfolio_id="P1", skip=0, limit=20, status="PROCESSING"
    )

    assert value == ["agg1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_aggregation_jobs.status = 'PROCESSING'" in compiled


async def test_get_analytics_export_jobs_count_with_status(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 5)

    value = await repository.get_analytics_export_jobs_count(portfolio_id="P1", status="failed")

    assert value == 5
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from analytics_export_jobs" in compiled.lower()
    assert "analytics_export_jobs.status = 'failed'" in compiled


async def test_get_analytics_export_jobs_query(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    reference_now = datetime(2025, 8, 31, 12, 0, tzinfo=timezone.utc)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["exp1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_analytics_export_jobs(
        portfolio_id="P1",
        skip=1,
        limit=3,
        status="running",
        reference_now=reference_now,
    )

    assert value == ["exp1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from analytics_export_jobs" in compiled.lower()
    assert "analytics_export_jobs.status = 'running'" in compiled
    assert "CASE WHEN (analytics_export_jobs.status = 'failed')" in compiled
    assert "analytics_export_jobs.updated_at < '2025-08-31 11:45:00+00:00'" in compiled
    assert "analytics_export_jobs.created_at ASC" in compiled


async def test_get_reconciliation_runs_count_with_filters(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 3)

    value = await repository.get_reconciliation_runs_count(
        portfolio_id="P1",
        reconciliation_type="transaction_cashflow",
        status="FAILED",
    )

    assert value == 3
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from financial_reconciliation_runs" in compiled.lower()
    assert "financial_reconciliation_runs.reconciliation_type = 'transaction_cashflow'" in compiled
    assert "financial_reconciliation_runs.status = 'FAILED'" in compiled


async def test_get_reconciliation_runs_query(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["run1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_reconciliation_runs(
        portfolio_id="P1",
        skip=2,
        limit=5,
        reconciliation_type="transaction_cashflow",
        status="COMPLETED",
    )

    assert value == ["run1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from financial_reconciliation_runs" in compiled.lower()
    assert "financial_reconciliation_runs.reconciliation_type = 'transaction_cashflow'" in compiled
    assert "financial_reconciliation_runs.status = 'COMPLETED'" in compiled
    assert (
        "CASE WHEN (financial_reconciliation_runs.status IN ('FAILED', 'REQUIRES_REPLAY'))"
        in compiled
    )
    assert "financial_reconciliation_runs.started_at DESC" in compiled
    assert "LIMIT 5 OFFSET 2" in compiled


async def test_get_reconciliation_findings_query(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["finding1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_reconciliation_findings(run_id="recon_123", limit=20)

    assert value == ["finding1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from financial_reconciliation_findings" in compiled.lower()
    assert "financial_reconciliation_findings.run_id = 'recon_123'" in compiled
    assert "CASE WHEN (financial_reconciliation_findings.severity = 'ERROR') THEN 0" in compiled
    assert "financial_reconciliation_findings.created_at DESC" in compiled
    assert "LIMIT 20" in compiled


async def test_get_reconciliation_run_query(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_run = object()
    mock_execute_scalar_one_or_none(mock_db_session, mock_run)

    value = await repository.get_reconciliation_run(portfolio_id="P1", run_id="recon_123")

    assert value is mock_run
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from financial_reconciliation_runs" in compiled.lower()
    assert "financial_reconciliation_runs.portfolio_id = 'P1'" in compiled
    assert "financial_reconciliation_runs.run_id = 'recon_123'" in compiled


async def test_get_reconciliation_findings_count(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 4)

    value = await repository.get_reconciliation_findings_count(run_id="recon_123")

    assert value == 4
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from financial_reconciliation_findings" in compiled.lower()
    assert "financial_reconciliation_findings.run_id = 'recon_123'" in compiled


async def test_get_portfolio_control_stages_count_with_filters(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 6)

    value = await repository.get_portfolio_control_stages_count(
        portfolio_id="P1",
        stage_name="FINANCIAL_RECONCILIATION",
        business_date=date(2026, 3, 13),
        status="REQUIRES_REPLAY",
    )

    assert value == 6
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from pipeline_stage_state" in compiled.lower()
    assert "pipeline_stage_state.transaction_id LIKE 'portfolio-stage:%'" in compiled
    assert "pipeline_stage_state.stage_name = 'FINANCIAL_RECONCILIATION'" in compiled
    assert "pipeline_stage_state.business_date = '2026-03-13'" in compiled
    assert "pipeline_stage_state.status = 'REQUIRES_REPLAY'" in compiled


async def test_get_portfolio_control_stages_query(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["stage1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_portfolio_control_stages(
        portfolio_id="P1",
        skip=1,
        limit=10,
        stage_name="FINANCIAL_RECONCILIATION",
        business_date=date(2026, 3, 13),
        status="FAILED",
    )

    assert value == ["stage1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from pipeline_stage_state" in compiled.lower()
    assert "pipeline_stage_state.transaction_id LIKE 'portfolio-stage:%'" in compiled
    assert "pipeline_stage_state.stage_name = 'FINANCIAL_RECONCILIATION'" in compiled
    assert "pipeline_stage_state.business_date = '2026-03-13'" in compiled
    assert "pipeline_stage_state.status = 'FAILED'" in compiled
    assert "CASE WHEN (pipeline_stage_state.status IN ('FAILED', 'REQUIRES_REPLAY'))" in compiled
    assert "pipeline_stage_state.business_date DESC" in compiled
    assert "LIMIT 10 OFFSET 1" in compiled


async def test_get_reprocessing_keys_count_with_filters(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 2)

    value = await repository.get_reprocessing_keys_count(
        portfolio_id="P1",
        status="REPROCESSING",
        security_id="SEC-US-IBM",
    )

    assert value == 2
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.status = 'REPROCESSING'" in compiled
    assert "position_state.security_id = 'SEC-US-IBM'" in compiled


async def test_get_reprocessing_keys_query(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    reference_now = datetime(2025, 8, 31, 12, 0, tzinfo=timezone.utc)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["key1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_reprocessing_keys(
        portfolio_id="P1",
        skip=3,
        limit=7,
        status="REPROCESSING",
        security_id="SEC-US-IBM",
        reference_now=reference_now,
    )

    assert value == ["key1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.status = 'REPROCESSING'" in compiled
    assert "position_state.security_id = 'SEC-US-IBM'" in compiled
    assert "CASE WHEN (position_state.status = 'REPROCESSING'" in compiled
    assert "position_state.updated_at < '2025-08-31 11:45:00+00:00'" in compiled
    assert "position_state.updated_at ASC" in compiled
    assert "LIMIT 7 OFFSET 3" in compiled


async def test_get_reprocessing_jobs_query_uses_reference_now(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    reference_now = datetime(2025, 8, 31, 12, 0, tzinfo=timezone.utc)
    mock_result = MagicMock()
    mock_result.all.return_value = ["job1"]
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    value = await repository.get_reprocessing_jobs(
        portfolio_id="P1",
        skip=0,
        limit=10,
        status="PROCESSING",
        security_id="SEC-US-IBM",
        reference_now=reference_now,
    )

    assert value == ["job1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "reprocessing_jobs.job_type = 'RESET_WATERMARKS'" in compiled
    assert "reprocessing_jobs.status = 'PROCESSING'" in compiled
    assert "from position_history join position_state on" in compiled.lower()
    assert "position_history.position_date <=" in compiled.lower()
    assert "CAST(reprocessing_jobs.payload['earliest_impacted_date'] AS DATE)" in compiled
    assert "anon_1.quantity > 0" in compiled
    assert "reprocessing_jobs.updated_at < '2025-08-31 11:45:00+00:00'" in compiled
    assert "LIMIT 10 OFFSET 0" in compiled


async def test_get_reprocessing_jobs_count_uses_date_aware_scope(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 2)

    value = await repository.get_reprocessing_jobs_count(
        portfolio_id="P1",
        status="PROCESSING",
        security_id="SEC-US-IBM",
    )

    assert value == 2
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from reprocessing_jobs" in compiled.lower()
    assert "reprocessing_jobs.job_type = 'RESET_WATERMARKS'" in compiled
    assert "from position_history join position_state on" in compiled.lower()
    assert "position_history.position_date <=" in compiled.lower()
    assert "CAST(reprocessing_jobs.payload['earliest_impacted_date'] AS DATE)" in compiled
    assert "anon_1.quantity > 0" in compiled
    assert "reprocessing_jobs.status = 'PROCESSING'" in compiled
