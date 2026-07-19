"""Characterize portfolio aggregation persistence and queue SQL contracts."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.database_models import PortfolioTimeseries
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_derived_state_service.app.domain.aggregation_jobs.models import (
    AggregationJobCompletionDisposition,
    AggregationJobLease,
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


def _lease() -> AggregationJobLease:
    return AggregationJobLease(
        owner="portfolio-aggregation-runtime-1",
        token="lease-token-1",
        expires_at=datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc),
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


async def test_get_current_epoch_for_portfolio_trims_portfolio_id(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    await repository.get_current_epoch_for_portfolio(" P1 ")
    compiled = str(
        mock_db_session.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True})
    )
    assert "trim(position_state.portfolio_id) = 'P1'" in compiled


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
    eligible_result.fetchall.return_value = [(1,)]
    claimed_result = MagicMock()
    claimed_result.scalars.return_value.all.return_value = [
        MagicMock(
            id=1,
            portfolio_id="P1",
            aggregation_date=date(2025, 1, 1),
            attempt_count=4,
            correlation_id=None,
            lease_owner=_lease().owner,
            lease_token=_lease().token,
            lease_expires_at=_lease().expires_at,
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
    assert claimed_jobs[0].aggregation_revision == 4


async def test_claim_eligible_jobs_returns_claimed_jobs_in_claim_order(
    repository: PortfolioAggregationRepository, mock_db_session: AsyncMock
):
    eligible_result = MagicMock()
    eligible_result.fetchall.return_value = [(1,), (2,), (3,)]
    claimed_result = MagicMock()
    claimed_result.scalars.return_value.all.return_value = [
        MagicMock(
            portfolio_id="P2",
            aggregation_date=date(2025, 1, 1),
            id=2,
            attempt_count=8,
            correlation_id=None,
            lease_owner=_lease().owner,
            lease_token=_lease().token,
            lease_expires_at=_lease().expires_at,
        ),
        MagicMock(
            portfolio_id="P1",
            aggregation_date=date(2025, 1, 2),
            id=3,
            attempt_count=7,
            correlation_id=None,
            lease_owner=_lease().owner,
            lease_token=_lease().token,
            lease_expires_at=_lease().expires_at,
        ),
        MagicMock(
            portfolio_id="P1",
            aggregation_date=date(2025, 1, 1),
            id=1,
            attempt_count=6,
            correlation_id=None,
            lease_owner=_lease().owner,
            lease_token=_lease().token,
            lease_expires_at=_lease().expires_at,
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


async def test_complete_or_requeue_job_completes_owned_job(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.side_effect = [MagicMock(rowcount=0), MagicMock(rowcount=1)]

    disposition = await repository.complete_or_requeue_job(
        job_id=7,
        lease_token="lease-token-1",
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
    mock_db_session.execute.side_effect = [MagicMock(rowcount=0), MagicMock(rowcount=0)]

    disposition = await repository.complete_or_requeue_job(
        job_id=7,
        lease_token="lease-token-1",
    )

    assert disposition is AggregationJobCompletionDisposition.LOST_OWNERSHIP


async def test_mark_job_failed_only_updates_owned_processing_job(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value = MagicMock(rowcount=1)

    updated = await repository.mark_job_failed(job_id=7, lease_token="lease-token-1")

    assert updated is True
    compiled = str(
        mock_db_session.execute.await_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "status='FAILED'" in compiled
    assert "portfolio_aggregation_jobs.status = 'PROCESSING'" in compiled


async def test_claim_eligible_jobs_persists_and_returns_lease_identity(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    lease = AggregationJobLease(
        owner="portfolio-aggregation-runtime-1",
        token="lease-token-1",
        expires_at=datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc),
    )
    eligible_result = MagicMock()
    eligible_result.fetchall.return_value = [(7,)]
    claimed_result = MagicMock()
    claimed_result.scalars.return_value.all.return_value = [
        MagicMock(
            id=7,
            portfolio_id="P1",
            aggregation_date=date(2026, 7, 15),
            attempt_count=9,
            correlation_id="corr-1",
            lease_owner=lease.owner,
            lease_token=lease.token,
            lease_expires_at=lease.expires_at,
        )
    ]
    mock_db_session.execute.side_effect = [eligible_result, claimed_result]

    claimed_jobs = await repository.claim_eligible_jobs(batch_size=5, lease=lease)

    assert claimed_jobs[0].lease == lease
    assert claimed_jobs[0].aggregation_revision == 9
    claim_statement = mock_db_session.execute.await_args_list[1].args[0]
    compiled = str(
        claim_statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "lease_owner='portfolio-aggregation-runtime-1'" in compiled
    assert "lease_token='lease-token-1'" in compiled
    assert "lease_expires_at='2026-07-15 08:30:00+00:00'" in compiled


async def test_complete_or_requeue_claim_fences_terminal_write_and_clears_lease(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.side_effect = [MagicMock(rowcount=0), MagicMock(rowcount=1)]

    disposition = await repository.complete_or_requeue_job(
        job_id=7,
        lease_token="lease-token-1",
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
    mock_db_session.execute.side_effect = [MagicMock(rowcount=0), MagicMock(rowcount=0)]

    disposition = await repository.complete_or_requeue_job(
        job_id=7,
        lease_token="expired-lease-token",
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


async def test_mark_claim_failed_fences_terminal_write_and_clears_lease(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value = MagicMock(rowcount=1)

    updated = await repository.mark_job_failed(job_id=7, lease_token="lease-token-1")

    assert updated is True
    compiled = str(
        mock_db_session.execute.await_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "portfolio_aggregation_jobs.id = 7" in compiled
    assert "portfolio_aggregation_jobs.lease_token = 'lease-token-1'" in compiled
    assert "lease_owner=NULL" in compiled
    assert "lease_token=NULL" in compiled
    assert "lease_expires_at=NULL" in compiled


async def test_recover_expired_job_leases_requeues_retryable_claim_and_clears_lease(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    now = datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc)
    expired_result = MagicMock()
    expired_result.all.return_value = [MagicMock(id=7, attempt_count=1)]
    reset_result = MagicMock(rowcount=1)
    mock_db_session.execute.side_effect = [expired_result, reset_result]

    result = await repository.recover_expired_job_leases(now=now, max_attempts=3)

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
    assert "lease_expires_at <= '2026-07-15 08:30:00+00:00'" in select_sql
    assert "updated_at <" not in select_sql
    assert "lease_expires_at <= '2026-07-15 08:30:00+00:00'" in reset_sql
    assert "lease_owner=NULL" in reset_sql
    assert "lease_token=NULL" in reset_sql
    assert "lease_expires_at=NULL" in reset_sql
    assert "failure_reason=NULL" in reset_sql


async def test_recover_expired_job_leases_fails_retry_exhausted_claim(
    repository: PortfolioAggregationRepository,
    mock_db_session: AsyncMock,
) -> None:
    now = datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc)
    expired_result = MagicMock()
    expired_result.all.return_value = [MagicMock(id=7, attempt_count=3)]
    failed_result = MagicMock(rowcount=1)
    mock_db_session.execute.side_effect = [expired_result, failed_result]

    result = await repository.recover_expired_job_leases(now=now, max_attempts=3)

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
    assert "lease_expires_at <= '2026-07-15 08:30:00+00:00'" in failed_sql
    assert "lease_owner=NULL" in failed_sql
