import re
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.valuation_job_contracts import ValuationJobTransitionOutcome
from sqlalchemy.dialects import postgresql
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
    compiled_query = str(claim_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "NOT (EXISTS" not in compiled_query
    assert (
        "portfolio_valuation_jobs.epoch = (SELECT portfolio_valuation_jobs_1.epoch" in compiled_query
    )
    assert "ORDER BY portfolio_valuation_jobs_1.epoch DESC" in compiled_query
    assert "LIMIT 1" in compiled_query
    assert (
        "ORDER BY portfolio_valuation_jobs.portfolio_id ASC, "
        "portfolio_valuation_jobs.security_id ASC, "
        "portfolio_valuation_jobs.valuation_date ASC, "
        "portfolio_valuation_jobs.epoch DESC"
    ) in compiled_query
    compact_query = compiled_query.replace(" ", "").replace("\n", "")
    assert "claimed_readiness_outbox_id=greatest(" in compact_query
    assert re.search(r"valuation_claim_token='[0-9a-f]{32}'", compact_query)
    assert "valuation_lease_owner='valuation-repository-" in compact_query
    assert "valuation_lease_expires_at=(clock_timestamp()+make_interval(" in compact_query
    assert "coalesce((SELECTmax(outbox_events.id)" in compact_query
    assert "outbox_events.aggregate_type = 'ValuationReadiness'" in compiled_query
    assert "outbox_events.event_type = 'PortfolioDayReadyForValuation'" in compiled_query
    assert "to_char(portfolio_valuation_jobs.valuation_date, 'YYYY-MM-DD')" in compiled_query
    assert "outbox_events.payload['portfolio_id']" in compiled_query


async def test_find_and_reset_stale_jobs_emits_reset_metric(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    select_result = MagicMock()
    select_result.all.return_value = [
        MagicMock(id=101, attempt_count=1, has_newer_epoch=False),
        MagicMock(id=102, attempt_count=1, has_newer_epoch=False),
        MagicMock(id=103, attempt_count=1, has_newer_epoch=False),
    ]
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(101,), (102,), (103,)]
    mock_db_session.execute.side_effect = [select_result, mock_result]

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(max_attempts=3)

    assert reset_count == 3
    reset_metric.assert_called_once_with(3)


async def test_stale_valuation_recovery_bounds_selection_and_chunks_reset_updates(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    first_result = MagicMock()
    first_result.fetchall.return_value = [(job_id,) for job_id in range(1, 1_001)]
    second_result = MagicMock()
    second_result.fetchall.return_value = [(1_001,)]
    mock_db_session.execute.side_effect = [first_result, second_result]

    reset_count = await repo._reset_retryable_stale_jobs(list(range(1_001, 0, -1)))

    assert reset_count == 1_001
    assert mock_db_session.execute.await_count == 2
    statement_lengths = [
        len(call.args[0].compile().params["id_1"])
        for call in mock_db_session.execute.await_args_list
    ]
    assert statement_lengths == [1_000, 1]
    assert len(mock_db_session.execute.await_args_list[0].args[0].compile().params) == 7

    select_result = MagicMock()
    select_result.all.return_value = []
    mock_db_session.reset_mock()
    mock_db_session.execute.side_effect = None
    mock_db_session.execute.return_value = select_result
    await repo._find_stale_job_rows()
    compiled_select = str(
        mock_db_session.execute.await_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "ORDER BY portfolio_valuation_jobs.valuation_lease_expires_at ASC" in compiled_select
    assert "LIMIT 1000" in compiled_select
    assert "FOR UPDATE SKIP LOCKED" in compiled_select


async def test_stale_valuation_recovery_logs_counts_without_identifier_collections(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    mock_db_session.execute.return_value = MagicMock()

    with patch("portfolio_common.valuation_repository_base.logger.warning") as warning:
        await repo._mark_over_limit_stale_jobs_failed([3, 2, 2, 1], max_attempts=3)

    extra = warning.call_args.kwargs["extra"]
    assert extra["job_count"] == 3
    assert "job_ids" not in extra


async def test_find_and_reset_stale_jobs_marks_over_limit_rows_failed(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    select_result = MagicMock()
    select_result.all.return_value = [MagicMock(id=201, attempt_count=3, has_newer_epoch=False)]
    failed_result = MagicMock()
    mock_db_session.execute.side_effect = [select_result, failed_result]

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(max_attempts=3)

    assert reset_count == 0
    reset_metric.assert_not_called()


async def test_stale_recovery_preserves_superseding_source_correction_after_attempt_limit(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    select_result = MagicMock()
    select_result.all.return_value = [
        MagicMock(
            id=202,
            attempt_count=3,
            has_newer_epoch=False,
            requeue_requested=True,
        )
    ]
    reset_result = MagicMock()
    reset_result.fetchall.return_value = [(202,)]
    mock_db_session.execute.side_effect = [select_result, reset_result]

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(max_attempts=3)

    assert reset_count == 1
    reset_metric.assert_called_once_with(1)
    reset_stmt = mock_db_session.execute.await_args_list[1].args[0]
    reset_sql = str(reset_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "SET status='PENDING', requeue_requested=false" in reset_sql


async def test_find_and_reset_stale_jobs_skips_superseded_rows_without_emitting_reset_metric(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    select_result = MagicMock()
    select_result.all.return_value = [MagicMock(id=301, attempt_count=1, has_newer_epoch=True)]
    skipped_result = MagicMock()
    mock_db_session.execute.side_effect = [select_result, skipped_result]

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(max_attempts=3)

    assert reset_count == 0
    reset_metric.assert_not_called()


async def test_find_and_reset_stale_jobs_rechecks_processing_state_before_reset(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    select_result = MagicMock()
    select_result.all.return_value = [MagicMock(id=101, attempt_count=1, has_newer_epoch=False)]
    update_result = MagicMock()
    update_result.fetchall.return_value = []
    mock_db_session.execute.side_effect = [select_result, update_result]

    with patch(
        "src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository.observe_valuation_worker_stale_resets"
    ) as reset_metric:
        reset_count = await repo.find_and_reset_stale_jobs(max_attempts=3)

    assert reset_count == 0
    reset_metric.assert_not_called()
    update_stmt = mock_db_session.execute.await_args_list[1].args[0]
    compiled_query = str(update_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_valuation_jobs.status = 'PROCESSING'" in compiled_query
    assert (
        "portfolio_valuation_jobs.valuation_lease_expires_at <= clock_timestamp()" in compiled_query
    )


async def test_recover_dispatch_failed_jobs_requeues_retryable_and_fails_exhausted_rows(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    failed_result = MagicMock()
    failed_result.rowcount = 1
    pending_result = MagicMock()
    pending_result.rowcount = 2
    mock_db_session.execute.side_effect = [failed_result, pending_result]

    result = await repo.recover_dispatch_failed_jobs(
        [(101, "a" * 32), (102, "b" * 32), (103, "c" * 32)],
        max_attempts=3,
        failure_reason="Scheduler dispatch publish failed before queueing record keys: key-1",
    )

    assert result == {"pending_count": 2, "failed_count": 1}
    failed_stmt = mock_db_session.execute.await_args_list[0].args[0]
    pending_stmt = mock_db_session.execute.await_args_list[1].args[0]
    failed_sql = str(failed_stmt.compile(compile_kwargs={"literal_binds": True}))
    pending_sql = str(pending_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "UPDATE portfolio_valuation_jobs" in failed_sql
    assert "SET status='FAILED'" in failed_sql
    assert "failure_reason='Scheduler dispatch publish failed" in failed_sql
    assert "portfolio_valuation_jobs.status = 'PROCESSING'" in failed_sql
    assert "portfolio_valuation_jobs.valuation_lease_expires_at > clock_timestamp()" in failed_sql
    assert "portfolio_valuation_jobs.valuation_claim_token" in failed_sql
    assert "portfolio_valuation_jobs.attempt_count >= 3" in failed_sql
    assert "portfolio_valuation_jobs.requeue_requested IS false" in failed_sql

    assert "UPDATE portfolio_valuation_jobs" in pending_sql
    assert "SET status='PENDING'" in pending_sql
    assert "portfolio_valuation_jobs.status = 'PROCESSING'" in pending_sql
    assert "portfolio_valuation_jobs.attempt_count < 3" in pending_sql
    assert "portfolio_valuation_jobs.requeue_requested IS true" in pending_sql
    assert "requeue_requested=false" in pending_sql


async def test_recover_dispatch_failed_jobs_chunks_and_aggregates_unique_claims(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    results = []
    for rowcount in (10, 990, 1, 0):
        result = MagicMock()
        result.rowcount = rowcount
        results.append(result)
    mock_db_session.execute.side_effect = results
    claims = [(job_id, f"token-{job_id:05d}") for job_id in reversed(range(1_001))]
    claims.append(claims[0])

    recovered = await repo.recover_dispatch_failed_jobs(
        claims,
        max_attempts=3,
        failure_reason="Dispatch failed.",
    )

    assert recovered == {"pending_count": 990, "failed_count": 11}
    assert mock_db_session.execute.await_count == 4


async def test_recover_dispatch_failed_jobs_rejects_conflicting_claim_tokens_before_io(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    with pytest.raises(ValueError, match="conflicting valuation claim tokens"):
        await repo.recover_dispatch_failed_jobs(
            [(101, "first-token"), (101, "different-token")],
            max_attempts=3,
            failure_reason="Dispatch failed.",
        )

    mock_db_session.execute.assert_not_awaited()


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
    assert "portfolio_valuation_jobs.status IN ('PENDING', 'FAILED')" in compiled_query


async def test_get_lagging_states_uses_scheduler_order(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = result

    states = await repo.get_lagging_states(date(2026, 3, 27), limit=25)

    assert states == []
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "position_state.watermark_date < '2026-03-27'" in compiled_query
    assert "position_state.status IN ('CURRENT', 'REPROCESSING')" in compiled_query
    assert (
        "ORDER BY position_state.updated_at ASC, position_state.portfolio_id ASC, "
        "position_state.security_id ASC"
    ) in compiled_query
    assert "LIMIT 25" in compiled_query


async def test_get_terminal_reprocessing_states_uses_scheduler_order(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = result

    states = await repo.get_terminal_reprocessing_states(date(2026, 3, 27), limit=25)

    assert states == []
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "position_state.status = 'REPROCESSING'" in compiled_query
    assert "position_state.watermark_date >= '2026-03-27'" in compiled_query
    assert (
        "ORDER BY position_state.updated_at ASC, position_state.portfolio_id ASC, "
        "position_state.security_id ASC"
    ) in compiled_query
    assert "LIMIT 25" in compiled_query


async def test_get_states_needing_backfill_uses_scheduler_order(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = result

    states = await repo.get_states_needing_backfill(date(2026, 3, 27), limit=25)

    assert states == []
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert (
        "JOIN instruments ON trim(instruments.security_id) = trim(position_state.security_id)"
        in compiled_query
    )
    assert "position_state.watermark_date < '2026-03-27'" in compiled_query
    assert "position_state.status IN ('CURRENT', 'REPROCESSING')" in compiled_query
    assert (
        "ORDER BY position_state.updated_at ASC, position_state.portfolio_id ASC, "
        "position_state.security_id ASC"
    ) in compiled_query
    assert "LIMIT 25" in compiled_query


async def test_find_contiguous_snapshot_dates_skips_database_for_empty_states(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    contiguous_dates = await repo.find_contiguous_snapshot_dates([])

    assert contiguous_dates == {}
    mock_db_session.execute.assert_not_awaited()


async def test_find_contiguous_snapshot_dates_returns_empty_without_any_valuation_date(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    state = MagicMock()
    repo.get_latest_business_date = AsyncMock(return_value=None)

    contiguous_dates = await repo.find_contiguous_snapshot_dates([state])

    assert contiguous_dates == {}
    repo.get_latest_business_date.assert_awaited_once_with()
    mock_db_session.execute.assert_not_awaited()


async def test_get_first_open_dates_skips_database_for_empty_keys(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    first_open_dates = await repo.get_first_open_dates_for_keys([])

    assert first_open_dates == {}
    mock_db_session.execute.assert_not_awaited()


async def test_get_first_open_dates_chunks_and_deduplicates_large_key_sets(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    first_rows = [
        MagicMock(
            portfolio_id=f"P-{index:05d}",
            security_id=f"S-{index:05d}",
            epoch=1,
            first_open_date=date(2026, 1, 1),
        )
        for index in range(1_000)
    ]
    second_rows = [
        MagicMock(
            portfolio_id="P-01000",
            security_id="S-01000",
            epoch=1,
            first_open_date=date(2026, 1, 2),
        )
    ]
    first_result = MagicMock()
    first_result.__iter__.return_value = iter(first_rows)
    second_result = MagicMock()
    second_result.__iter__.return_value = iter(second_rows)
    mock_db_session.execute.side_effect = [first_result, second_result]
    keys = [(row.portfolio_id, row.security_id, row.epoch) for row in reversed(first_rows)]
    keys.extend([("P-01000", "S-01000", 1), keys[0]])

    first_open_dates = await repo.get_first_open_dates_for_keys(keys)

    assert len(first_open_dates) == 1_001
    assert first_open_dates[("P-01000", "S-01000", 1)] == date(2026, 1, 2)
    assert mock_db_session.execute.await_count == 2


async def test_find_contiguous_snapshot_dates_chunks_large_state_sets(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    states = [
        MagicMock(
            portfolio_id=f"P-{index:05d}",
            security_id=f"S-{index:05d}",
            epoch=1,
        )
        for index in reversed(range(1_001))
    ]
    first_result = MagicMock()
    first_result.__iter__.return_value = iter(
        [
            MagicMock(
                portfolio_id=f"P-{index:05d}",
                security_id=f"S-{index:05d}",
                contiguous_date=date(2026, 8, 19),
            )
            for index in range(1_000)
        ]
    )
    second_result = MagicMock()
    second_result.__iter__.return_value = iter(
        [
            MagicMock(
                portfolio_id="P-01000",
                security_id="S-01000",
                contiguous_date=date(2026, 8, 20),
            )
        ]
    )
    mock_db_session.execute.side_effect = [first_result, second_result]
    first_open_dates = {
        (state.portfolio_id, state.security_id, state.epoch): date(2026, 1, 1) for state in states
    }

    contiguous_dates = await repo.find_contiguous_snapshot_dates(
        states,
        first_open_dates,
        latest_valuation_date=date(2026, 8, 20),
    )

    assert len(contiguous_dates) == 1_001
    assert contiguous_dates[("P-01000", "S-01000")] == date(2026, 8, 20)
    assert mock_db_session.execute.await_count == 2
    parameter_counts = [
        len(
            call.args[0]
            .compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"render_postcompile": True},
            )
            .params
        )
        for call in mock_db_session.execute.await_args_list
    ]
    assert parameter_counts == [7_011, 18]


async def test_find_contiguous_snapshot_dates_rejects_conflicting_epochs_before_io(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    repo.get_latest_business_date = AsyncMock()
    states = [
        MagicMock(portfolio_id="P-1", security_id="S-1", epoch=1),
        MagicMock(portfolio_id="P-1", security_id="S-1", epoch=2),
    ]

    with pytest.raises(ValueError, match="conflicting position-state epochs"):
        await repo.find_contiguous_snapshot_dates(
            states,
        )

    repo.get_latest_business_date.assert_not_awaited()
    mock_db_session.execute.assert_not_awaited()


async def test_find_contiguous_snapshot_dates_snapshots_first_open_authority_before_await(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    states = [
        MagicMock(
            portfolio_id=f"P-{index:05d}",
            security_id=f"S-{index:05d}",
            epoch=1,
        )
        for index in range(1_001)
    ]
    final_key = ("P-01000", "S-01000", 1)
    first_open_dates = {final_key: date(2026, 1, 2)}

    async def mutate_after_first_statement(_statement):
        if mock_db_session.execute.await_count == 1:
            first_open_dates.clear()
        result = MagicMock()
        result.__iter__.return_value = iter([])
        return result

    mock_db_session.execute.side_effect = mutate_after_first_statement

    with patch(
        "portfolio_common.valuation_repository_base.build_contiguous_snapshot_dates_stmt",
        return_value=MagicMock(),
    ) as build_statement:
        await repo.find_contiguous_snapshot_dates(
            states,
            first_open_dates,
            latest_valuation_date=date(2026, 8, 20),
        )

    assert mock_db_session.execute.await_count == 2
    assert build_statement.call_args_list[1].args[1] == {final_key: date(2026, 1, 2)}


async def test_get_fx_rate_normalizes_currency_codes_and_uses_functional_index_predicates(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db_session.execute.return_value = result

    fx_rate = await repo.get_fx_rate(
        from_currency=" eur ",
        to_currency=" usd ",
        a_date=date(2026, 3, 27),
    )

    assert fx_rate is None
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "upper(trim(fx_rates.from_currency)) = 'EUR'" in compiled_query
    assert "upper(trim(fx_rates.to_currency)) = 'USD'" in compiled_query
    assert "fx_rates.rate_date <= '2026-03-27'" in compiled_query
    assert "ORDER BY fx_rates.rate_date DESC, fx_rates.id DESC" in compiled_query


async def test_get_instrument_trims_security_id_before_query(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db_session.execute.return_value = result

    instrument = await repo.get_instrument(" SEC_A ")

    assert instrument is None
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(instruments.security_id) = 'SEC_A'" in compiled_query


async def test_get_portfolio_trims_portfolio_id_before_query(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db_session.execute.return_value = result

    portfolio = await repo.get_portfolio(" PORT_001 ")

    assert portfolio is None
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(portfolios.portfolio_id) = 'PORT_001'" in compiled_query


async def test_get_portfolios_by_ids_trims_portfolio_ids_and_skips_blanks(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = result

    portfolios = await repo.get_portfolios_by_ids([" PORT_001 ", "", " PORT_002 "])

    assert portfolios == []
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(portfolios.portfolio_id) IN ('PORT_001', 'PORT_002')" in compiled_query


async def test_get_portfolios_by_ids_skips_empty_identifier_list(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    portfolios = await repo.get_portfolios_by_ids([" ", ""])

    assert portfolios == []
    mock_db_session.execute.assert_not_awaited()


async def test_get_last_position_history_before_date_trims_portfolio_and_security_ids(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db_session.execute.return_value = result

    history = await repo.get_last_position_history_before_date(
        " PORT_001 ", " SEC_A ", date(2026, 3, 27), 42
    )

    assert history is None
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(position_history.portfolio_id) = 'PORT_001'" in compiled_query
    assert "trim(position_history.security_id) = 'SEC_A'" in compiled_query
    assert "position_history.position_date <= '2026-03-27'" in compiled_query
    assert "position_history.epoch = 42" in compiled_query


async def test_update_job_status_trims_portfolio_and_security_ids(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalar_one_or_none.return_value = "COMPLETED"
    mock_db_session.execute.return_value = result

    outcome = await repo.update_job_status(
        portfolio_id=" PORT_001 ",
        security_id=" SEC_A ",
        valuation_date=date(2026, 3, 27),
        epoch=42,
        status="COMPLETED",
        expected_claim_token="a" * 32,
    )

    assert outcome is ValuationJobTransitionOutcome.TERMINAL_APPLIED
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(portfolio_valuation_jobs.portfolio_id) = 'PORT_001'" in compiled_query
    assert "trim(portfolio_valuation_jobs.security_id) = 'SEC_A'" in compiled_query
    assert "portfolio_valuation_jobs.valuation_date = '2026-03-27'" in compiled_query
    assert "portfolio_valuation_jobs.epoch = 42" in compiled_query
    assert "portfolio_valuation_jobs.status = 'PROCESSING'" in compiled_query
    assert (
        "portfolio_valuation_jobs.valuation_claim_token IS NOT DISTINCT FROM "
        "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'"
    ) in compiled_query
    assert "valuation_claim_token=NULL" in compiled_query.replace(" ", "")
    assert "portfolio_valuation_jobs.requeue_requested IS true" in compiled_query
    assert "RETURNING portfolio_valuation_jobs.status" in compiled_query
    assert stmt.get_execution_options()["synchronize_session"] is False


@pytest.mark.parametrize(
    ("applied_status", "expected_outcome"),
    [
        ("PENDING", ValuationJobTransitionOutcome.REQUEUED),
        (None, ValuationJobTransitionOutcome.NOT_OWNED),
    ],
)
async def test_update_job_status_classifies_non_terminal_outcomes(
    mock_db_session: AsyncMock,
    applied_status: str | None,
    expected_outcome: ValuationJobTransitionOutcome,
) -> None:
    repo = ValuationRepository(mock_db_session)
    result = MagicMock()
    result.scalar_one_or_none.return_value = applied_status
    mock_db_session.execute.return_value = result

    outcome = await repo.update_job_status(
        portfolio_id="PORT_001",
        security_id="SEC_A",
        valuation_date=date(2026, 3, 27),
        epoch=42,
        status="COMPLETE",
    )

    assert outcome is expected_outcome


async def test_update_job_status_rejects_unsupported_applied_status(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)
    result = MagicMock()
    result.scalar_one_or_none.return_value = "SKIPPED_SUPERSEDED"
    mock_db_session.execute.return_value = result

    with pytest.raises(RuntimeError, match="unsupported applied status"):
        await repo.update_job_status(
            portfolio_id="PORT_001",
            security_id="SEC_A",
            valuation_date=date(2026, 3, 27),
            epoch=42,
            status="COMPLETE",
        )


async def test_get_latest_price_for_position_trims_security_id_before_query(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db_session.execute.return_value = result

    market_price = await repo.get_latest_price_for_position(
        security_id=" SEC_A ",
        position_date=date(2026, 3, 27),
    )

    assert market_price is None
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(market_prices.security_id) = 'SEC_A'" in compiled_query
    assert "market_prices.price_date <= '2026-03-27'" in compiled_query
    assert "ORDER BY market_prices.price_date DESC" in compiled_query


async def test_get_next_price_date_trims_security_id_before_query(
    mock_db_session: AsyncMock,
) -> None:
    repo = ValuationRepository(mock_db_session)

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    mock_db_session.execute.return_value = result

    next_price_date = await repo.get_next_price_date(
        security_id=" SEC_A ",
        after_date=date(2026, 3, 27),
    )

    assert next_price_date is None
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "trim(market_prices.security_id) = 'SEC_A'" in compiled_query
    assert "market_prices.price_date > '2026-03-27'" in compiled_query
    assert "ORDER BY market_prices.price_date ASC" in compiled_query
    assert "LIMIT 1" in compiled_query
