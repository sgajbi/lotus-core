"""Characterize portfolio aggregation persistence and queue SQL contracts."""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import PortfolioTimeseries
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_derived_state_service.app.domain.aggregation_jobs.models import (
    AggregationJobCompletionDisposition,
    AggregationJobFailureDisposition,
    AggregationJobLease,
    AggregationJobLeaseClaim,
    ExpiredAggregationJobRecovery,
)
from src.services.portfolio_derived_state_service.app.infrastructure import (
    portfolio_aggregation_repository,
)

PortfolioAggregationRepository = portfolio_aggregation_repository.PortfolioAggregationRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.fetchall.return_value = []
    result.all.return_value = []
    result.rowcount = 1
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> PortfolioAggregationRepository:
    return PortfolioAggregationRepository(mock_db_session)


LEASE_EXPIRES_AT = datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc)


def _lease() -> AggregationJobLeaseClaim:
    return AggregationJobLeaseClaim(
        owner="portfolio-aggregation-runtime-1",
        token="lease-token-1",
        duration_seconds=300,
    )


async def test_get_portfolio_trims_portfolio_id(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    row = MagicMock(portfolio_id="P1", base_currency="SGD")
    mock_db_session.execute.return_value.scalars.return_value.first.return_value = row

    await repository.get_portfolio(" P1 ")
    compiled = str(
        mock_db_session.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "WHERE trim(portfolios.portfolio_id) = 'P1'" in compiled


async def test_get_portfolio_returns_immutable_aggregation_scope(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    row = MagicMock(portfolio_id="P1", base_currency="SGD")
    mock_db_session.execute.return_value.scalars.return_value.first.return_value = row

    portfolio = await repository.get_portfolio("P1")

    assert portfolio is not None
    assert portfolio.portfolio_id == "P1"
    assert portfolio.base_currency == "SGD"
    assert portfolio is not row


async def test_upsert_portfolio_timeseries(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    record = PortfolioTimeseries(portfolio_id="P1", date=date(2025, 1, 10), epoch=1)
    await repository.upsert_portfolio_timeseries(record)
    compiled = str(
        mock_db_session.execute.call_args[0][0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "INSERT INTO portfolio_timeseries" in compiled
    assert "ON CONFLICT (portfolio_id, date, epoch) DO UPDATE" in compiled


async def test_claim_eligible_jobs_does_not_require_prior_portfolio_day(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    await repository.claim_eligible_jobs(batch_size=5, lease=_lease())

    executed_stmt = mock_db_session.execute.call_args_list[0][0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert (
        "portfolio_timeseries.date = portfolio_aggregation_jobs.aggregation_date"
        not in compiled_query
    )
    assert "date < portfolio_aggregation_jobs.aggregation_date" not in compiled_query
    assert "FROM portfolio_timeseries, portfolio_aggregation_jobs" not in compiled_query


async def test_claim_eligible_jobs_completeness_gate_stays_correlated(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    await repository.claim_eligible_jobs(batch_size=5, lease=_lease())

    executed_stmt = mock_db_session.execute.call_args_list[0][0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "FROM daily_position_snapshots, portfolio_aggregation_jobs" not in compiled_query
    assert "FROM position_timeseries, portfolio_aggregation_jobs" not in compiled_query
    assert (
        "daily_position_snapshots.date <= portfolio_aggregation_jobs.aggregation_date"
        in compiled_query
    )
    assert "max(daily_position_snapshots.epoch)" in compiled_query
    assert "daily_position_snapshots.epoch <= portfolio_aggregation_jobs.target_epoch" not in (
        compiled_query
    )
    assert ".updated_at >= daily_position_snapshots_" in compiled_query
    assert "position_timeseries_" in compiled_query


async def test_claim_eligible_jobs_has_no_legacy_count_window_gate(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    await repository.claim_eligible_jobs(batch_size=5, lease=_lease())

    executed_stmt = mock_db_session.execute.call_args_list[0][0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()

    assert "count(" not in compiled_query
    assert "row_number() over" not in compiled_query


async def test_claim_eligible_jobs_uses_deterministic_claim_order(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    await repository.claim_eligible_jobs(batch_size=5, lease=_lease())

    executed_stmt = mock_db_session.execute.call_args_list[0][0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "portfolio_aggregation_jobs.status = 'PENDING'" in compiled_query
    assert (
        "ORDER BY portfolio_aggregation_jobs.portfolio_id, "
        "portfolio_aggregation_jobs.aggregation_date, portfolio_aggregation_jobs.id"
    ) in compiled_query


async def test_claim_eligible_jobs_increments_attempt_count(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    eligible_result = MagicMock()
    eligible_result.fetchall.return_value = [(1, 3, True)]
    claimed_result = MagicMock()
    claimed_result.scalars.return_value.all.return_value = [
        MagicMock(
            id=1,
            portfolio_id="P1",
            aggregation_date=date(2025, 1, 1),
            attempt_count=4,
            target_epoch=3,
            source_revision=2,
            correlation_id=None,
            lease_owner=_lease().owner,
            lease_token=_lease().token,
            lease_expires_at=LEASE_EXPIRES_AT,
        )
    ]
    mock_db_session.execute.side_effect = [eligible_result, claimed_result]

    claimed_jobs = await repository.claim_eligible_jobs(batch_size=5, lease=_lease())

    executed_stmt = mock_db_session.execute.await_args_list[1].args[0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "UPDATE portfolio_aggregation_jobs" in compiled_query
    assert "SET status='PROCESSING'" in compiled_query
    assert "attempt_count=(portfolio_aggregation_jobs.attempt_count + 1)" in compiled_query
    assert "target_epoch=greatest(portfolio_aggregation_jobs.target_epoch" in compiled_query
    assert "CASE portfolio_aggregation_jobs.id WHEN 1 THEN 3" in compiled_query
    assert "CASE portfolio_aggregation_jobs.id WHEN 1 THEN true" in compiled_query
    assert "source_revision=CASE WHEN" in compiled_query
    assert claimed_jobs[0].aggregation_revision == 4


async def test_claim_eligible_jobs_returns_claimed_jobs_in_claim_order(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    eligible_result = MagicMock()
    eligible_result.fetchall.return_value = [(1, 3, False), (2, 3, False), (3, 3, False)]
    claimed_result = MagicMock()
    claimed_result.scalars.return_value.all.return_value = [
        MagicMock(
            portfolio_id="P2",
            aggregation_date=date(2025, 1, 1),
            id=2,
            attempt_count=8,
            target_epoch=3,
            source_revision=4,
            correlation_id=None,
            lease_owner=_lease().owner,
            lease_token=_lease().token,
            lease_expires_at=LEASE_EXPIRES_AT,
        ),
        MagicMock(
            portfolio_id="P1",
            aggregation_date=date(2025, 1, 2),
            id=3,
            attempt_count=7,
            target_epoch=3,
            source_revision=4,
            correlation_id=None,
            lease_owner=_lease().owner,
            lease_token=_lease().token,
            lease_expires_at=LEASE_EXPIRES_AT,
        ),
        MagicMock(
            portfolio_id="P1",
            aggregation_date=date(2025, 1, 1),
            id=1,
            attempt_count=6,
            target_epoch=3,
            source_revision=4,
            correlation_id=None,
            lease_owner=_lease().owner,
            lease_token=_lease().token,
            lease_expires_at=LEASE_EXPIRES_AT,
        ),
    ]
    mock_db_session.execute.side_effect = [eligible_result, claimed_result]

    claimed_jobs = await repository.claim_eligible_jobs(batch_size=5, lease=_lease())

    assert [(job.portfolio_id, job.aggregation_date, job.id) for job in claimed_jobs] == [
        ("P1", date(2025, 1, 1), 1),
        ("P1", date(2025, 1, 2), 3),
        ("P2", date(2025, 1, 1), 2),
    ]
    assert [job.aggregation_revision for job in claimed_jobs] == [6, 7, 8]


async def test_get_job_queue_stats_returns_pending_failed_and_oldest_pending(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    result = MagicMock()
    result.one.return_value = MagicMock(
        pending_count=4,
        failed_count=1,
        oldest_pending_created_at=date(2025, 1, 1),
    )
    mock_db_session.execute.return_value = result

    queue_stats = await repository.get_job_queue_stats()

    assert queue_stats == {
        "pending_count": 4,
        "failed_count": 1,
        "oldest_pending_created_at": date(2025, 1, 1),
    }
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "portfolio_aggregation_jobs.status IN ('PENDING', 'FAILED')" in compiled_query


async def test_get_all_position_timeseries_for_date_uses_latest_position_epoch_within_target_epoch(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    await repository.get_all_position_timeseries_for_date("P1", date(2025, 1, 10), 14)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(
        executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "position_timeseries.date <= '2025-01-10'" in compiled_query
    assert "position_timeseries.epoch <= 14" in compiled_query
    assert (
        "row_number() OVER (PARTITION BY trim(position_timeseries.security_id) "
        "ORDER BY position_timeseries.date DESC, position_timeseries.epoch DESC)" in compiled_query
    )
    assert "trim(position_timeseries.portfolio_id) = 'P1'" in compiled_query
    assert "trim(position_timeseries.portfolio_id) = anon_1.portfolio_id" in compiled_query
    assert "trim(position_timeseries.security_id) = anon_1.security_id" in compiled_query
    assert "anon_1.rn = 1" in compiled_query


async def test_get_all_position_timeseries_for_date_returns_immutable_records(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    row = MagicMock(
        portfolio_id="P1",
        security_id="S1",
        date=date(2025, 1, 10),
        epoch=14,
        bod_market_value=Decimal("100"),
        bod_cashflow_portfolio=Decimal("1"),
        eod_cashflow_portfolio=Decimal("2"),
        eod_market_value=Decimal("110"),
        fees=Decimal("3"),
        calculation_lineage=None,
    )
    mock_db_session.execute.return_value.scalars.return_value.all.return_value = [row]

    records = await repository.get_all_position_timeseries_for_date("P1", date(2025, 1, 10), 14)

    assert records[0].security_id == "S1"
    assert records[0].eod_market_value == Decimal("110")
    assert records[0] is not row


async def test_complete_or_requeue_job_requeues_late_material_input(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    requeued = MagicMock(rowcount=1)
    mock_db_session.execute.return_value = requeued

    disposition = await repository.complete_or_requeue_job(
        job_id=7,
        lease_token="lease-token-1",
        target_epoch=4,
        source_revision=5,
    )

    assert disposition is AggregationJobCompletionDisposition.REQUEUED
    mock_db_session.execute.assert_awaited_once()
    compiled = str(
        mock_db_session.execute.await_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "status='PENDING'" in compiled
    assert "portfolio_aggregation_jobs.failure_reason = 'REPROCESS_REQUESTED'" in compiled
    assert "portfolio_aggregation_jobs.lease_token = 'lease-token-1'" in compiled
    assert "portfolio_aggregation_jobs.lease_expires_at > clock_timestamp()" in compiled


async def test_complete_or_requeue_job_completes_owned_job(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.side_effect = [MagicMock(rowcount=0), MagicMock(rowcount=1)]

    disposition = await repository.complete_or_requeue_job(
        job_id=7,
        lease_token="lease-token-1",
        target_epoch=4,
        source_revision=5,
    )

    assert disposition is AggregationJobCompletionDisposition.COMPLETE
    complete_statement = mock_db_session.execute.await_args_list[1].args[0]
    compiled = str(
        complete_statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "status='COMPLETE'" in compiled
    assert "portfolio_aggregation_jobs.status = 'PROCESSING'" in compiled


async def test_complete_or_requeue_job_reports_lost_ownership(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.side_effect = [
        MagicMock(rowcount=0),
        MagicMock(rowcount=0),
        MagicMock(rowcount=0),
    ]

    disposition = await repository.complete_or_requeue_job(
        job_id=7,
        lease_token="lease-token-1",
        target_epoch=4,
        source_revision=5,
    )

    assert disposition is AggregationJobCompletionDisposition.LOST_OWNERSHIP


async def test_complete_or_requeue_job_rechecks_supersession_after_terminal_race(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.side_effect = [
        MagicMock(rowcount=0),
        MagicMock(rowcount=0),
        MagicMock(rowcount=1),
    ]

    disposition = await repository.complete_or_requeue_job(
        job_id=7,
        lease_token="lease-token-1",
        target_epoch=4,
        source_revision=5,
    )

    assert disposition is AggregationJobCompletionDisposition.REQUEUED
    assert mock_db_session.execute.await_count == 3


async def test_fail_or_requeue_job_fails_only_current_owned_processing_job(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.side_effect = [MagicMock(rowcount=0), MagicMock(rowcount=1)]

    disposition = await repository.fail_or_requeue_job(
        job_id=7,
        lease_token="lease-token-1",
        target_epoch=4,
        source_revision=5,
    )

    assert disposition is AggregationJobFailureDisposition.FAILED
    compiled = str(
        mock_db_session.execute.await_args_list[1]
        .args[0]
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "status='FAILED'" in compiled
    assert "portfolio_aggregation_jobs.status = 'PROCESSING'" in compiled


async def test_fail_or_requeue_job_requeues_superseded_source_identity(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value = MagicMock(rowcount=1)

    disposition = await repository.fail_or_requeue_job(
        job_id=7,
        lease_token="lease-token-1",
        target_epoch=4,
        source_revision=5,
    )

    assert disposition is AggregationJobFailureDisposition.REQUEUED
    mock_db_session.execute.assert_awaited_once()
    compiled = str(
        mock_db_session.execute.await_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "status='PENDING'" in compiled
    assert "portfolio_aggregation_jobs.target_epoch != 4" in compiled
    assert "portfolio_aggregation_jobs.source_revision != 5" in compiled
    assert "daily_position_snapshots_1.epoch > 4" in compiled
    assert "position_timeseries_1.updated_at >= daily_position_snapshots_1.updated_at" in compiled


async def test_fail_or_requeue_job_rechecks_supersession_after_terminal_race(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.side_effect = [
        MagicMock(rowcount=0),
        MagicMock(rowcount=0),
        MagicMock(rowcount=1),
    ]

    disposition = await repository.fail_or_requeue_job(
        job_id=7,
        lease_token="lease-token-1",
        target_epoch=4,
        source_revision=5,
    )

    assert disposition is AggregationJobFailureDisposition.REQUEUED
    assert mock_db_session.execute.await_count == 3


async def test_claim_eligible_jobs_persists_and_returns_lease_identity(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    lease = AggregationJobLeaseClaim(
        owner="portfolio-aggregation-runtime-1",
        token="lease-token-1",
        duration_seconds=300,
    )
    eligible_result = MagicMock()
    eligible_result.fetchall.return_value = [(7, 4, False)]
    claimed_result = MagicMock()
    claimed_result.scalars.return_value.all.return_value = [
        MagicMock(
            id=7,
            portfolio_id="P1",
            aggregation_date=date(2026, 7, 15),
            attempt_count=9,
            target_epoch=4,
            source_revision=5,
            correlation_id="corr-1",
            lease_owner=lease.owner,
            lease_token=lease.token,
            lease_expires_at=LEASE_EXPIRES_AT,
        )
    ]
    mock_db_session.execute.side_effect = [eligible_result, claimed_result]

    claimed_jobs = await repository.claim_eligible_jobs(batch_size=5, lease=lease)

    assert claimed_jobs[0].lease == AggregationJobLease(
        owner=lease.owner,
        token=lease.token,
        expires_at=LEASE_EXPIRES_AT,
    )
    assert claimed_jobs[0].aggregation_revision == 9
    assert claimed_jobs[0].target_epoch == 4
    assert claimed_jobs[0].source_revision == 5
    claim_statement = mock_db_session.execute.await_args_list[1].args[0]
    compiled = str(
        claim_statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "lease_owner='portfolio-aggregation-runtime-1'" in compiled
    assert "lease_token='lease-token-1'" in compiled
    assert "lease_expires_at=(clock_timestamp() + make_interval" in compiled


async def test_complete_or_requeue_claim_fences_terminal_write_and_clears_lease(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.side_effect = [MagicMock(rowcount=0), MagicMock(rowcount=1)]

    disposition = await repository.complete_or_requeue_job(
        job_id=7,
        lease_token="lease-token-1",
        target_epoch=4,
        source_revision=5,
    )

    assert disposition is AggregationJobCompletionDisposition.COMPLETE
    complete_statement = mock_db_session.execute.await_args_list[1].args[0]
    compiled = str(
        complete_statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "portfolio_aggregation_jobs.id = 7" in compiled
    assert "portfolio_aggregation_jobs.lease_token = 'lease-token-1'" in compiled
    assert "lease_owner=NULL" in compiled
    assert "lease_token=NULL" in compiled
    assert "lease_expires_at=NULL" in compiled


async def test_complete_or_requeue_claim_reports_lost_ownership_after_reclaim(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.side_effect = [
        MagicMock(rowcount=0),
        MagicMock(rowcount=0),
        MagicMock(rowcount=0),
    ]

    disposition = await repository.complete_or_requeue_job(
        job_id=7,
        lease_token="expired-lease-token",
        target_epoch=4,
        source_revision=5,
    )

    assert disposition is AggregationJobCompletionDisposition.LOST_OWNERSHIP
    for call in mock_db_session.execute.await_args_list:
        compiled = str(
            call.args[0].compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        assert "portfolio_aggregation_jobs.lease_token = 'expired-lease-token'" in compiled
        assert "portfolio_aggregation_jobs.lease_expires_at > clock_timestamp()" in compiled


async def test_fail_current_claim_fences_terminal_write_and_clears_lease(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.side_effect = [MagicMock(rowcount=0), MagicMock(rowcount=1)]

    disposition = await repository.fail_or_requeue_job(
        job_id=7,
        lease_token="lease-token-1",
        target_epoch=4,
        source_revision=5,
    )

    assert disposition is AggregationJobFailureDisposition.FAILED
    compiled = str(
        mock_db_session.execute.await_args_list[1]
        .args[0]
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "portfolio_aggregation_jobs.id = 7" in compiled
    assert "portfolio_aggregation_jobs.lease_token = 'lease-token-1'" in compiled
    assert "portfolio_aggregation_jobs.lease_expires_at > clock_timestamp()" in compiled
    assert "lease_owner=NULL" in compiled
    assert "lease_token=NULL" in compiled
    assert "lease_expires_at=NULL" in compiled


async def test_recover_expired_job_leases_requeues_retryable_claim_and_clears_lease(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    expired_result = MagicMock()
    expired_result.all.return_value = [MagicMock(id=7, attempt_count=1, failure_reason=None)]
    reset_result = MagicMock(rowcount=1)
    mock_db_session.execute.side_effect = [expired_result, reset_result]

    result = await repository.recover_expired_job_leases(max_attempts=3)

    assert result == ExpiredAggregationJobRecovery(requeued_count=1, failed_count=0)
    select_sql = str(
        mock_db_session.execute.await_args_list[0]
        .args[0]
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    reset_sql = str(
        mock_db_session.execute.await_args_list[1]
        .args[0]
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "lease_expires_at <= clock_timestamp()" in select_sql
    assert "updated_at <" not in select_sql
    assert "lease_expires_at <= clock_timestamp()" in reset_sql
    assert "lease_owner=NULL" in reset_sql
    assert "lease_token=NULL" in reset_sql
    assert "lease_expires_at=NULL" in reset_sql
    assert "failure_reason=NULL" in reset_sql
    assert "ORDER BY portfolio_aggregation_jobs.lease_expires_at ASC" in select_sql
    assert "portfolio_aggregation_jobs.id ASC" in select_sql
    assert "LIMIT 1000" in select_sql
    assert "FOR UPDATE SKIP LOCKED" in select_sql


async def test_recover_expired_job_leases_fails_retry_exhausted_claim(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    expired_result = MagicMock()
    expired_result.all.return_value = [MagicMock(id=7, attempt_count=3, failure_reason=None)]
    failed_result = MagicMock(rowcount=1)
    reset_result = MagicMock(rowcount=0)
    mock_db_session.execute.side_effect = [expired_result, failed_result, reset_result]

    result = await repository.recover_expired_job_leases(max_attempts=3)

    assert result == ExpiredAggregationJobRecovery(requeued_count=0, failed_count=1)
    failed_sql = str(
        mock_db_session.execute.await_args_list[1]
        .args[0]
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "status='FAILED'" in failed_sql
    assert "lease expired after max attempts" in failed_sql
    assert "coalesce(portfolio_aggregation_jobs.failure_reason, '') !=" in failed_sql
    assert "lease_expires_at <= clock_timestamp()" in failed_sql
    assert "lease_owner=NULL" in failed_sql
    assert mock_db_session.execute.await_count == 2


async def test_recover_expired_job_leases_requeues_unattempted_superseded_revision(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    expired_result = MagicMock()
    expired_result.all.return_value = [
        MagicMock(
            id=7,
            attempt_count=3,
            failure_reason="REPROCESS_REQUESTED",
        )
    ]
    reset_result = MagicMock(rowcount=1)
    mock_db_session.execute.side_effect = [expired_result, reset_result]

    result = await repository.recover_expired_job_leases(max_attempts=3)

    assert result == ExpiredAggregationJobRecovery(requeued_count=1, failed_count=0)
    reset_sql = str(
        mock_db_session.execute.await_args_list[1]
        .args[0]
        .compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "status='PENDING'" in reset_sql
    assert "failure_reason=NULL" in reset_sql


async def test_recover_expired_job_leases_uses_disjoint_failed_and_requeue_updates(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    expired_result = MagicMock()
    expired_result.all.return_value = [
        MagicMock(id=9, attempt_count=3, failure_reason=None),
        MagicMock(id=7, attempt_count=1, failure_reason=None),
        MagicMock(id=8, attempt_count=3, failure_reason="REPROCESS_REQUESTED"),
    ]
    failed_result = MagicMock(rowcount=1)
    reset_result = MagicMock(rowcount=2)
    mock_db_session.execute.side_effect = [expired_result, failed_result, reset_result]

    result = await repository.recover_expired_job_leases(max_attempts=3)

    assert result == ExpiredAggregationJobRecovery(requeued_count=2, failed_count=1)
    failed_statement = mock_db_session.execute.await_args_list[1].args[0]
    reset_statement = mock_db_session.execute.await_args_list[2].args[0]
    failed_ids = next(
        value for value in failed_statement.compile().params.values() if isinstance(value, list)
    )
    reset_ids = next(
        value for value in reset_statement.compile().params.values() if isinstance(value, list)
    )
    assert failed_ids == [9]
    assert reset_ids == [7, 8]


async def test_requeue_expired_job_leases_chunks_and_aggregates_counts(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    first = MagicMock(rowcount=1_000)
    second = MagicMock(rowcount=1)
    mock_db_session.execute.side_effect = [first, second]

    sentinel_job_id = 1_000
    with caplog.at_level(logging.INFO):
        count = await repository._requeue_expired_job_leases(
            [*range(1_001), sentinel_job_id, 0],
        )

    assert count == 1_001
    assert mock_db_session.execute.await_count == 2
    chunk_sizes = [
        len(
            next(
                value for value in call.args[0].compile().params.values() if isinstance(value, list)
            )
        )
        for call in mock_db_session.execute.await_args_list
    ]
    assert chunk_sizes == [1_000, 1]
    batch_records = [
        record
        for record in caplog.records
        if getattr(record, "event_name", None) == "database_statement_batch"
    ]
    assert len(batch_records) == 1
    record = batch_records[0]
    assert record.operation == "aggregation_stale_requeue_update"
    assert record.item_count == 1_001
    assert record.chunk_count == 2
    assert record.max_rows_per_statement == 1_000
    for attribute in ("job_id", "job_ids", "portfolio_id", "security_id"):
        assert not hasattr(record, attribute)
    assert str(sentinel_job_id) not in record.getMessage()
