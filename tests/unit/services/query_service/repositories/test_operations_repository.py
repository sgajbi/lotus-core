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
    aggregate_result = MagicMock()
    aggregate_result.one.return_value = mock_row
    oldest_key_result = MagicMock()
    oldest_key_result.one_or_none.return_value = MagicMock(
        security_id="SEC-IBM",
        epoch=4,
        updated_at=datetime(2025, 8, 20, 9, 0, tzinfo=timezone.utc),
    )
    mock_db_session.execute = AsyncMock(side_effect=[aggregate_result, oldest_key_result])

    value = await repository.get_reprocessing_health_summary(
        "P1", stale_minutes=15, reference_now=reference_now
    )

    assert value.active_keys == 3
    assert value.stale_reprocessing_keys == 1
    assert value.oldest_reprocessing_watermark_date == date(2025, 8, 20)
    assert value.oldest_reprocessing_security_id == "SEC-IBM"
    assert value.oldest_reprocessing_epoch == 4
    assert value.oldest_reprocessing_updated_at == datetime(
        2025, 8, 20, 9, 0, tzinfo=timezone.utc
    )
    aggregate_stmt = mock_db_session.execute.call_args_list[0][0][0]
    aggregate_compiled = str(aggregate_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in aggregate_compiled.lower()
    assert "position_state.status = 'REPROCESSING'" in aggregate_compiled
    assert "position_state.updated_at < '2025-08-31 11:45:00+00:00'" in aggregate_compiled
    oldest_stmt = mock_db_session.execute.call_args_list[1][0][0]
    oldest_compiled = str(oldest_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "order by position_state.watermark_date asc" in oldest_compiled.lower()
    assert "position_state.security_id" in oldest_compiled


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
    aggregate_result = MagicMock()
    aggregate_result.one.return_value = mock_row
    oldest_job_result = MagicMock()
    oldest_job_result.one_or_none.return_value = MagicMock(
        id=8801,
        security_id="SEC-US-IBM",
        correlation_id="corr-val-8801",
    )
    mock_db_session.execute = AsyncMock(side_effect=[aggregate_result, oldest_job_result])

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
    assert value.oldest_open_job_id == 8801
    assert value.oldest_open_job_correlation_id == "corr-val-8801"
    assert value.oldest_open_security_id == "SEC-US-IBM"
    aggregate_stmt = mock_db_session.execute.call_args_list[0][0][0]
    aggregate_compiled = str(aggregate_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_valuation_jobs" in aggregate_compiled.lower()
    assert (
        "FILTER (WHERE portfolio_valuation_jobs.status IN ('PENDING', 'PROCESSING'))"
        in aggregate_compiled
    )
    assert "FILTER (WHERE portfolio_valuation_jobs.status = 'FAILED')" in aggregate_compiled
    assert "portfolio_valuation_jobs.updated_at < '2025-08-31 11:45:00+00:00'" in aggregate_compiled
    assert (
        "portfolio_valuation_jobs.updated_at >= '2025-08-30 12:00:00+00:00'"
        in aggregate_compiled
    )
    oldest_stmt = mock_db_session.execute.call_args_list[1][0][0]
    oldest_compiled = str(oldest_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "order by portfolio_valuation_jobs.valuation_date asc" in oldest_compiled.lower()
    assert "portfolio_valuation_jobs.id" in oldest_compiled


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
    aggregate_result = MagicMock()
    aggregate_result.one.return_value = mock_row
    oldest_job_result = MagicMock()
    oldest_job_result.one_or_none.return_value = MagicMock(
        id=4402,
        correlation_id="corr-agg-4402",
    )
    mock_db_session.execute = AsyncMock(side_effect=[aggregate_result, oldest_job_result])

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
    assert value.oldest_open_job_id == 4402
    assert value.oldest_open_job_correlation_id == "corr-agg-4402"
    assert value.oldest_open_security_id is None
    aggregate_stmt = mock_db_session.execute.call_args_list[0][0][0]
    aggregate_compiled = str(aggregate_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from portfolio_aggregation_jobs" in aggregate_compiled.lower()
    assert (
        "FILTER (WHERE portfolio_aggregation_jobs.status IN ('PENDING', 'PROCESSING'))"
        in aggregate_compiled
    )
    assert "FILTER (WHERE portfolio_aggregation_jobs.status = 'FAILED')" in aggregate_compiled
    assert (
        "portfolio_aggregation_jobs.updated_at < '2025-08-31 11:45:00+00:00'"
        in aggregate_compiled
    )
    assert (
        "portfolio_aggregation_jobs.updated_at >= '2025-08-30 12:00:00+00:00'"
        in aggregate_compiled
    )
    oldest_stmt = mock_db_session.execute.call_args_list[1][0][0]
    oldest_compiled = str(oldest_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "order by portfolio_aggregation_jobs.aggregation_date asc" in oldest_compiled.lower()
    assert "portfolio_aggregation_jobs.id" in oldest_compiled


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
    aggregate_result = MagicMock()
    aggregate_result.one.return_value = mock_row
    oldest_job_result = MagicMock()
    oldest_job_result.one_or_none.return_value = MagicMock(
        job_id="aexp_0001",
        request_fingerprint="pf-001:positions:csv",
    )
    mock_db_session.execute = AsyncMock(side_effect=[aggregate_result, oldest_job_result])

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
    assert value.oldest_open_job_id == "aexp_0001"
    assert value.oldest_open_request_fingerprint == "pf-001:positions:csv"
    aggregate_stmt = mock_db_session.execute.call_args_list[0][0][0]
    aggregate_compiled = str(aggregate_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from analytics_export_jobs" in aggregate_compiled.lower()
    assert "FILTER (WHERE analytics_export_jobs.status = 'accepted')" in aggregate_compiled
    assert "FILTER (WHERE analytics_export_jobs.status = 'running')" in aggregate_compiled
    assert "FILTER (WHERE analytics_export_jobs.status = 'failed')" in aggregate_compiled
    assert "analytics_export_jobs.updated_at < '2025-08-31 11:45:00+00:00'" in aggregate_compiled
    assert "analytics_export_jobs.updated_at >= '2025-08-30 12:00:00+00:00'" in aggregate_compiled
    oldest_stmt = mock_db_session.execute.call_args_list[1][0][0]
    oldest_compiled = str(oldest_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "order by analytics_export_jobs.created_at asc" in oldest_compiled.lower()
    assert "analytics_export_jobs.request_fingerprint" in oldest_compiled


async def test_support_job_queries_honor_job_id_filters(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    scalar_result = MagicMock()
    scalar_result.scalar_one.return_value = 0
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = []
    rows_result = MagicMock()
    rows_result.all.return_value = []
    mock_db_session.execute = AsyncMock(
        side_effect=[
            scalar_result,
            scalars_result,
            scalar_result,
            scalars_result,
            scalar_result,
            scalars_result,
            scalar_result,
            rows_result,
        ]
    )

    reference_now = datetime(2025, 8, 31, 12, 0, tzinfo=timezone.utc)

    await repository.get_valuation_jobs_count(
        "P1",
        status="PENDING",
        business_date=date(2025, 8, 31),
        security_id="SEC-US-IBM",
        job_id=8801,
        correlation_id="corr-val-8801",
    )
    await repository.get_valuation_jobs(
        "P1",
        skip=0,
        limit=10,
        status="PENDING",
        business_date=date(2025, 8, 31),
        security_id="SEC-US-IBM",
        job_id=8801,
        correlation_id="corr-val-8801",
        reference_now=reference_now,
    )
    await repository.get_aggregation_jobs_count(
        "P1",
        status="PROCESSING",
        business_date=date(2025, 8, 31),
        job_id=4402,
        correlation_id="corr-agg-4402",
    )
    await repository.get_aggregation_jobs(
        "P1",
        skip=0,
        limit=10,
        status="PROCESSING",
        business_date=date(2025, 8, 31),
        job_id=4402,
        correlation_id="corr-agg-4402",
        reference_now=reference_now,
    )
    await repository.get_analytics_export_jobs_count(
        "P1",
        status="failed",
        job_id="aexp_1234567890abcdef",
        request_fingerprint="pf-001:positions:csv",
    )
    await repository.get_analytics_export_jobs(
        "P1",
        skip=0,
        limit=10,
        status="failed",
        job_id="aexp_1234567890abcdef",
        request_fingerprint="pf-001:positions:csv",
        reference_now=reference_now,
    )
    await repository.get_reprocessing_jobs_count(
        "P1",
        status="PROCESSING",
        security_id="SEC-US-IBM",
        job_id=303,
        correlation_id="corr-replay-303",
    )
    await repository.get_reprocessing_jobs(
        "P1",
        skip=0,
        limit=10,
        status="PROCESSING",
        security_id="SEC-US-IBM",
        job_id=303,
        correlation_id="corr-replay-303",
        reference_now=reference_now,
    )

    compiled_statements = [
        str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
        for call in mock_db_session.execute.call_args_list
    ]
    assert "portfolio_valuation_jobs.valuation_date = '2025-08-31'" in compiled_statements[0]
    assert "portfolio_valuation_jobs.security_id = 'SEC-US-IBM'" in compiled_statements[0]
    assert "portfolio_valuation_jobs.id = 8801" in compiled_statements[0]
    assert "portfolio_valuation_jobs.correlation_id = 'corr-val-8801'" in compiled_statements[0]
    assert "portfolio_valuation_jobs.valuation_date = '2025-08-31'" in compiled_statements[1]
    assert "portfolio_valuation_jobs.security_id = 'SEC-US-IBM'" in compiled_statements[1]
    assert "portfolio_valuation_jobs.id = 8801" in compiled_statements[1]
    assert "portfolio_valuation_jobs.correlation_id = 'corr-val-8801'" in compiled_statements[1]
    assert "portfolio_aggregation_jobs.aggregation_date = '2025-08-31'" in compiled_statements[2]
    assert "portfolio_aggregation_jobs.id = 4402" in compiled_statements[2]
    assert "portfolio_aggregation_jobs.correlation_id = 'corr-agg-4402'" in compiled_statements[2]
    assert "portfolio_aggregation_jobs.aggregation_date = '2025-08-31'" in compiled_statements[3]
    assert "portfolio_aggregation_jobs.id = 4402" in compiled_statements[3]
    assert "portfolio_aggregation_jobs.correlation_id = 'corr-agg-4402'" in compiled_statements[3]
    assert "analytics_export_jobs.job_id = 'aexp_1234567890abcdef'" in compiled_statements[4]
    assert (
        "analytics_export_jobs.request_fingerprint = 'pf-001:positions:csv'"
        in compiled_statements[4]
    )
    assert "analytics_export_jobs.job_id = 'aexp_1234567890abcdef'" in compiled_statements[5]
    assert (
        "analytics_export_jobs.request_fingerprint = 'pf-001:positions:csv'"
        in compiled_statements[5]
    )
    assert "reprocessing_jobs.id = 303" in compiled_statements[6]
    assert "reprocessing_jobs.correlation_id = 'corr-replay-303'" in compiled_statements[6]
    assert "reprocessing_jobs.id = 303" in compiled_statements[7]
    assert "reprocessing_jobs.correlation_id = 'corr-replay-303'" in compiled_statements[7]


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


async def test_get_latest_reconciliation_run_for_portfolio_day(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_run = object()
    mock_execute_scalar_one_or_none(mock_db_session, mock_run)

    value = await repository.get_latest_reconciliation_run_for_portfolio_day(
        "P1", date(2025, 8, 30), 2
    )

    assert value is mock_run
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from financial_reconciliation_runs" in compiled.lower()
    assert "financial_reconciliation_runs.portfolio_id = 'P1'" in compiled
    assert "financial_reconciliation_runs.business_date = '2025-08-30'" in compiled
    assert "financial_reconciliation_runs.epoch = 2" in compiled
    assert "financial_reconciliation_runs.started_at DESC" in compiled


async def test_get_latest_reconciliation_run_for_portfolio_day_honors_as_of(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_run = object()
    mock_execute_scalar_one_or_none(mock_db_session, mock_run)
    as_of = datetime(2025, 8, 30, 11, 0, tzinfo=timezone.utc)

    value = await repository.get_latest_reconciliation_run_for_portfolio_day(
        "P1", date(2025, 8, 30), 2, as_of=as_of
    )

    assert value is mock_run
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "financial_reconciliation_runs.started_at <= '2025-08-30 11:00:00+00:00'" in compiled


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

    value = await repository.get_analytics_export_jobs_count(
        portfolio_id="P1",
        status="failed",
        request_fingerprint="pf-001:positions:csv",
    )

    assert value == 5
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from analytics_export_jobs" in compiled.lower()
    assert "analytics_export_jobs.status = 'failed'" in compiled
    assert "analytics_export_jobs.request_fingerprint = 'pf-001:positions:csv'" in compiled


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
        request_fingerprint="pf-001:positions:csv",
        reference_now=reference_now,
    )

    assert value == ["exp1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from analytics_export_jobs" in compiled.lower()
    assert "analytics_export_jobs.status = 'running'" in compiled
    assert "analytics_export_jobs.request_fingerprint = 'pf-001:positions:csv'" in compiled
    assert "CASE WHEN (analytics_export_jobs.status = 'failed')" in compiled
    assert "analytics_export_jobs.updated_at < '2025-08-31 11:45:00+00:00'" in compiled
    assert "analytics_export_jobs.created_at ASC" in compiled


async def test_get_reconciliation_runs_count_with_filters(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 3)

    value = await repository.get_reconciliation_runs_count(
        portfolio_id="P1",
        run_id="recon_123",
        correlation_id="corr-recon-123",
        requested_by="pipeline_orchestrator_service",
        dedupe_key="recon:transaction_cashflow:P1:2025-08-30:2",
        reconciliation_type="transaction_cashflow",
        status="FAILED",
    )

    assert value == 3
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from financial_reconciliation_runs" in compiled.lower()
    assert "financial_reconciliation_runs.run_id = 'recon_123'" in compiled
    assert "financial_reconciliation_runs.correlation_id = 'corr-recon-123'" in compiled
    assert (
        "financial_reconciliation_runs.requested_by = 'pipeline_orchestrator_service'"
        in compiled
    )
    assert (
        "financial_reconciliation_runs.dedupe_key = 'recon:transaction_cashflow:P1:2025-08-30:2'"
        in compiled
    )
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
        run_id="recon_123",
        correlation_id="corr-recon-123",
        requested_by="pipeline_orchestrator_service",
        dedupe_key="recon:transaction_cashflow:P1:2025-08-30:2",
        reconciliation_type="transaction_cashflow",
        status="COMPLETED",
    )

    assert value == ["run1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from financial_reconciliation_runs" in compiled.lower()
    assert "financial_reconciliation_runs.run_id = 'recon_123'" in compiled
    assert "financial_reconciliation_runs.correlation_id = 'corr-recon-123'" in compiled
    assert (
        "financial_reconciliation_runs.requested_by = 'pipeline_orchestrator_service'"
        in compiled
    )
    assert (
        "financial_reconciliation_runs.dedupe_key = 'recon:transaction_cashflow:P1:2025-08-30:2'"
        in compiled
    )
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

    value = await repository.get_reconciliation_findings(
        run_id="recon_123",
        limit=20,
        finding_id="rf_123",
        security_id="SEC-US-IBM",
        transaction_id="txn_0001",
    )

    assert value == ["finding1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from financial_reconciliation_findings" in compiled.lower()
    assert "financial_reconciliation_findings.run_id = 'recon_123'" in compiled
    assert "financial_reconciliation_findings.finding_id = 'rf_123'" in compiled
    assert "financial_reconciliation_findings.security_id = 'SEC-US-IBM'" in compiled
    assert "financial_reconciliation_findings.transaction_id = 'txn_0001'" in compiled
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

    value = await repository.get_reconciliation_findings_count(
        run_id="recon_123",
        finding_id="rf_123",
        security_id="SEC-US-IBM",
        transaction_id="txn_0001",
    )

    assert value == 4
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from financial_reconciliation_findings" in compiled.lower()
    assert "financial_reconciliation_findings.run_id = 'recon_123'" in compiled
    assert "financial_reconciliation_findings.finding_id = 'rf_123'" in compiled
    assert "financial_reconciliation_findings.security_id = 'SEC-US-IBM'" in compiled
    assert "financial_reconciliation_findings.transaction_id = 'txn_0001'" in compiled


async def test_get_reconciliation_finding_summary(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_row = MagicMock(total_findings=4, blocking_findings=2)
    aggregate_result = MagicMock()
    aggregate_result.one.return_value = mock_row
    top_blocking_result = MagicMock()
    top_blocking_result.one_or_none.return_value = MagicMock(
        finding_id="rf_1234567890abcdef",
        finding_type="missing_cashflow",
        security_id="SEC-US-IBM",
        transaction_id="txn_0001",
    )
    mock_db_session.execute = AsyncMock(side_effect=[aggregate_result, top_blocking_result])

    value = await repository.get_reconciliation_finding_summary(run_id="recon_123")

    assert value.total_findings == 4
    assert value.blocking_findings == 2
    assert value.top_blocking_finding_id == "rf_1234567890abcdef"
    assert value.top_blocking_finding_type == "missing_cashflow"
    assert value.top_blocking_finding_security_id == "SEC-US-IBM"
    assert value.top_blocking_finding_transaction_id == "txn_0001"
    aggregate_stmt = mock_db_session.execute.call_args_list[0][0][0]
    aggregate_compiled = str(aggregate_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from financial_reconciliation_findings" in aggregate_compiled.lower()
    assert "financial_reconciliation_findings.run_id = 'recon_123'" in aggregate_compiled
    assert (
        "FILTER (WHERE financial_reconciliation_findings.severity = 'ERROR')"
        in aggregate_compiled
    )
    top_blocking_stmt = mock_db_session.execute.call_args_list[1][0][0]
    top_blocking_compiled = str(top_blocking_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "financial_reconciliation_findings.severity = 'ERROR'" in top_blocking_compiled
    assert "financial_reconciliation_findings.created_at DESC" in top_blocking_compiled


async def test_get_portfolio_control_stages_count_with_filters(
    repository: OperationsRepository, mock_db_session: AsyncMock
):
    mock_execute_scalar_one(mock_db_session, 6)

    value = await repository.get_portfolio_control_stages_count(
        portfolio_id="P1",
        stage_id=701,
        stage_name="FINANCIAL_RECONCILIATION",
        business_date=date(2026, 3, 13),
        status="REQUIRES_REPLAY",
    )

    assert value == 6
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from pipeline_stage_state" in compiled.lower()
    assert "pipeline_stage_state.transaction_id LIKE 'portfolio-stage:%'" in compiled
    assert "pipeline_stage_state.id = 701" in compiled
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
        stage_id=701,
        stage_name="FINANCIAL_RECONCILIATION",
        business_date=date(2026, 3, 13),
        status="FAILED",
    )

    assert value == ["stage1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from pipeline_stage_state" in compiled.lower()
    assert "pipeline_stage_state.transaction_id LIKE 'portfolio-stage:%'" in compiled
    assert "pipeline_stage_state.id = 701" in compiled
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
        watermark_date=date(2025, 8, 1),
    )

    assert value == 2
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.status = 'REPROCESSING'" in compiled
    assert "position_state.security_id = 'SEC-US-IBM'" in compiled
    assert "position_state.watermark_date = '2025-08-01'" in compiled


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
        watermark_date=date(2025, 8, 1),
        reference_now=reference_now,
    )

    assert value == ["key1"]
    stmt = mock_db_session.execute.call_args[0][0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "from position_state" in compiled.lower()
    assert "position_state.status = 'REPROCESSING'" in compiled
    assert "position_state.security_id = 'SEC-US-IBM'" in compiled
    assert "position_state.watermark_date = '2025-08-01'" in compiled
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
