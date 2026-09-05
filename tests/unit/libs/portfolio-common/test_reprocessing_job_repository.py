from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from portfolio_common.reprocessing_job_repository import (
    _REPLAY_TEXT_TRIM_CHARS,
    ReprocessingJobRepository,
    ReprocessingJobTransitionOutcome,
    ResetWatermarksStageOutcome,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

LEASE_TOKEN = "a" * 32
LEASE_EXPIRES_AT = datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc)


@pytest.fixture
def mock_db_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> ReprocessingJobRepository:
    return ReprocessingJobRepository(db=mock_db_session)


async def test_find_and_claim_jobs_uses_atomic_skip_locked_update(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    identity_result = MagicMock()
    identity_result.scalars.return_value.all.return_value = []
    normalize_result = MagicMock()
    normalize_result.scalar_one.return_value = 0
    mock_db_session.execute.side_effect = [
        MagicMock(),
        identity_result,
        MagicMock(),
        MagicMock(),
        normalize_result,
        mock_result,
    ]

    await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=25)

    assert mock_db_session.execute.await_count == 6
    query = mock_db_session.execute.await_args_list[5].args[0]
    params = mock_db_session.execute.await_args_list[5].args[1]
    query_text = str(query)

    assert "UPDATE reprocessing_jobs" in query_text
    assert "FOR UPDATE SKIP LOCKED" in query_text
    assert "WITH candidates AS MATERIALIZED" in query_text
    assert "RETURNING target.*" in query_text
    assert params["job_type"] == "RESET_WATERMARKS"
    assert params["batch_size"] == 25
    assert params["excluded_job_ids"] == []
    assert params["lease_owner"].startswith("reprocessing-repository-")
    assert len(params["lease_token"]) == 32
    assert params["lease_duration_seconds"] == 900
    assert "lease_expires_at = clock_timestamp()" in query_text
    assert "make_interval(secs => :lease_duration_seconds)" in query_text
    assert "(payload->>'earliest_impacted_date') ASC" in query_text


@pytest.mark.parametrize(
    ("lease_owner", "lease_duration_seconds", "message"),
    [
        (" ", 900, "lease owner"),
        ("worker", 0, "lease duration"),
    ],
)
async def test_find_and_claim_jobs_rejects_invalid_lease_authority(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
    lease_owner: str,
    lease_duration_seconds: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        await repository.find_and_claim_jobs(
            "RESET_WATERMARKS",
            batch_size=1,
            lease_owner=lease_owner,
            lease_duration_seconds=lease_duration_seconds,
        )

    mock_db_session.execute.assert_not_awaited()


async def test_find_and_claim_jobs_uses_default_created_at_order_for_other_job_types(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result

    await repository.find_and_claim_jobs("OTHER_JOB", batch_size=10)

    query = mock_db_session.execute.await_args.args[0]
    query_text = str(query)

    assert "ORDER BY created_at ASC, id ASC" in query_text
    assert "(payload->>'earliest_impacted_date')::date ASC" not in query_text


async def test_find_and_claim_fx_jobs_prioritizes_earliest_impacted_date(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result

    await repository.find_and_claim_jobs("RESET_FX_WATERMARKS", batch_size=10)

    query = mock_db_session.execute.await_args.args[0]
    assert "(payload->>'earliest_impacted_date') ASC" in str(query)


async def test_find_and_claim_fx_jobs_defers_invalid_date_rejection(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {
            "id": 20,
            "job_type": "RESET_FX_WATERMARKS",
            "payload": {
                "from_currency": "USD",
                "to_currency": "SGD",
                "earliest_impacted_date": "not-a-date",
            },
            "status": "PROCESSING",
            "attempt_count": 1,
            "last_attempted_at": None,
            "failure_reason": None,
            "created_at": None,
            "updated_at": None,
            "lease_token": LEASE_TOKEN,
            "lease_expires_at": LEASE_EXPIRES_AT,
        },
        {
            "id": 10,
            "job_type": "RESET_FX_WATERMARKS",
            "payload": {
                "from_currency": "USD",
                "to_currency": "SGD",
                "earliest_impacted_date": "2026-04-10",
            },
            "status": "PROCESSING",
            "attempt_count": 1,
            "last_attempted_at": None,
            "failure_reason": None,
            "created_at": None,
            "updated_at": None,
            "lease_token": LEASE_TOKEN,
            "lease_expires_at": LEASE_EXPIRES_AT,
        },
    ]
    mock_db_session.execute.return_value = mock_result

    claimed = await repository.find_and_claim_jobs("RESET_FX_WATERMARKS", batch_size=2)

    assert [job.id for job in claimed] == [10, 20]
    assert all(job.lease_token == LEASE_TOKEN for job in claimed)


async def test_normalize_pending_reset_watermarks_duplicates_uses_set_based_cleanup(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    identity_result = MagicMock()
    identity_result.scalars.return_value.all.return_value = ["BOND-B", "BOND-A", "BOND-A"]
    normalize_result = MagicMock()
    normalize_result.scalar_one.return_value = 2
    mock_db_session.execute.side_effect = [
        MagicMock(),
        identity_result,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        normalize_result,
    ]

    deleted_count = await repository.normalize_pending_reset_watermarks_duplicates()

    assert deleted_count == 2
    assert mock_db_session.execute.await_count == 7
    identity_stmt = mock_db_session.execute.await_args_list[1].args[0]
    assert "SELECT DISTINCT" in str(identity_stmt)
    assert "ORDER BY security_id" in str(identity_stmt)
    assert "IS DISTINCT FROM btrim" in str(identity_stmt)
    assert "replay_control_pattern" in str(identity_stmt)
    lock_parameters = [call.args[1] for call in mock_db_session.execute.await_args_list[2:4]]
    assert lock_parameters == [
        {"identity_key": "RESET_WATERMARKS|6:BOND-A"},
        {"identity_key": "RESET_WATERMARKS|6:BOND-B"},
    ]
    quarantine_unsafe_stmt = mock_db_session.execute.await_args_list[4].args[0]
    assert "unsafe identity representation" in str(quarantine_unsafe_stmt)
    assert "pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN TRUE" in str(
        quarantine_unsafe_stmt
    )
    collision_stmt = mock_db_session.execute.await_args_list[5].args[0]
    assert "identity collision" in str(collision_stmt)
    assert "WHEN pg_input_is_valid(collision.payload::text, 'jsonb') IS NOT TRUE THEN FALSE" in str(
        collision_stmt
    )
    stmt = mock_db_session.execute.await_args_list[6].args[0]
    stmt_text = str(stmt)
    assert "WITH valid_candidates AS MATERIALIZED" in stmt_text
    assert "pg_input_is_valid" in stmt_text
    assert "earliest_impacted_date' !~ :python_iso_date_pattern" in stmt_text
    assert "btrim(payload->>'security_id', :trim_chars)" in stmt_text
    assert mock_db_session.execute.await_args.args[1] == {"trim_chars": _REPLAY_TEXT_TRIM_CHARS}
    assert stmt.compile().params["python_iso_date_pattern"]
    assert "DELETE FROM reprocessing_jobs" in stmt_text
    assert "jsonb_set" in stmt_text


async def test_normalize_pending_reset_watermarks_duplicates_emits_metric(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    identity_result = MagicMock()
    identity_result.scalars.return_value.all.return_value = []
    normalize_result = MagicMock()
    normalize_result.scalar_one.return_value = 3
    mock_db_session.execute.side_effect = [
        MagicMock(),
        identity_result,
        MagicMock(),
        MagicMock(),
        normalize_result,
    ]

    with patch(
        "portfolio_common.reprocessing_job_repository.observe_reprocessing_duplicates_normalized"
    ) as mock_observe:
        deleted_count = await repository.normalize_pending_reset_watermarks_duplicates()

    assert deleted_count == 3
    mock_observe.assert_called_once_with("reset_watermarks_pending_jobs", 3)


async def test_find_and_claim_jobs_normalizes_reset_watermarks_duplicates_before_claim(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    normalize_result = MagicMock()
    normalize_result.scalar_one.return_value = 1
    claim_result = MagicMock()
    claim_result.mappings.return_value.all.return_value = []
    identity_result = MagicMock()
    identity_result.scalars.return_value.all.return_value = []
    collision_result = MagicMock()
    mock_db_session.execute.side_effect = [
        MagicMock(),
        identity_result,
        MagicMock(),
        collision_result,
        normalize_result,
        claim_result,
    ]

    await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=10)

    assert mock_db_session.execute.await_count == 6
    collision_stmt = mock_db_session.execute.await_args_list[3].args[0]
    normalize_stmt = mock_db_session.execute.await_args_list[4].args[0]
    claim_stmt = mock_db_session.execute.await_args_list[5].args[0]
    assert "identity collision" in str(collision_stmt)
    assert "WITH valid_candidates AS MATERIALIZED" in str(normalize_stmt)
    assert "UPDATE reprocessing_jobs" in str(claim_stmt)


async def test_find_and_claim_jobs_can_skip_repeated_reset_watermark_normalization(
    mock_db_session,
) -> None:
    repository = ReprocessingJobRepository(mock_db_session)
    claim_result = MagicMock()
    claim_result.mappings.return_value.all.return_value = []
    mock_db_session.execute.return_value = claim_result

    await repository.find_and_claim_jobs(
        "RESET_WATERMARKS",
        batch_size=1,
        normalize_reset_watermark_duplicates=False,
    )

    mock_db_session.execute.assert_awaited_once()
    claim_stmt = mock_db_session.execute.await_args.args[0]
    assert "WITH candidates AS MATERIALIZED" in str(claim_stmt)


async def test_find_and_claim_jobs_maps_rows_to_models(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {
            "id": 10,
            "job_type": "RESET_WATERMARKS",
            "payload": {"security_id": "AAPL", "earliest_impacted_date": "2025-01-05"},
            "status": "PROCESSING",
            "attempt_count": 1,
            "last_attempted_at": None,
            "failure_reason": None,
            "created_at": None,
            "updated_at": None,
            "lease_token": LEASE_TOKEN,
            "lease_expires_at": LEASE_EXPIRES_AT,
        }
    ]
    mock_db_session.execute.return_value = mock_result

    claimed = await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=1)

    assert len(claimed) == 1
    assert claimed[0].id == 10
    assert claimed[0].status == "PROCESSING"
    with pytest.raises((AttributeError, TypeError)):
        claimed[0].status = "COMPLETE"  # type: ignore[misc]


async def test_find_and_claim_jobs_preserves_malformed_payload_for_per_job_rejection(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    normalize_result = MagicMock()
    normalize_result.scalar_one.return_value = 0
    claim_result = MagicMock()
    claim_result.mappings.return_value.all.return_value = [
        {
            "id": 11,
            "job_type": "RESET_WATERMARKS",
            "payload": None,
            "status": "PROCESSING",
            "attempt_count": 1,
            "created_at": datetime(2026, 8, 25, tzinfo=timezone.utc),
            "lease_token": LEASE_TOKEN,
            "lease_expires_at": LEASE_EXPIRES_AT,
        },
        {
            "id": 12,
            "job_type": "RESET_WATERMARKS",
            "payload": {"security_id": "AAPL", "earliest_impacted_date": "2025-01-05"},
            "status": "PROCESSING",
            "attempt_count": 1,
            "created_at": datetime(2026, 8, 25, tzinfo=timezone.utc),
            "lease_token": LEASE_TOKEN,
            "lease_expires_at": LEASE_EXPIRES_AT,
        },
    ]
    identity_result = MagicMock()
    identity_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.side_effect = [
        MagicMock(),
        identity_result,
        MagicMock(),
        MagicMock(),
        normalize_result,
        claim_result,
    ]

    claimed = await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=2)

    assert [job.id for job in claimed] == [12, 11]
    assert claimed[1].payload is None


async def test_find_and_claim_jobs_returns_reset_watermarks_in_priority_order(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    normalize_result = MagicMock()
    normalize_result.scalar_one.return_value = 0
    claim_result = MagicMock()
    claim_result.mappings.return_value.all.return_value = [
        {
            "id": 30,
            "job_type": "RESET_WATERMARKS",
            "payload": {"security_id": "S1", "earliest_impacted_date": "2025-01-07"},
            "status": "PROCESSING",
            "attempt_count": 1,
            "last_attempted_at": None,
            "failure_reason": None,
            "created_at": None,
            "updated_at": None,
            "lease_token": LEASE_TOKEN,
            "lease_expires_at": LEASE_EXPIRES_AT,
        },
        {
            "id": 20,
            "job_type": "RESET_WATERMARKS",
            "payload": {"security_id": "S2", "earliest_impacted_date": "2025-01-05"},
            "status": "PROCESSING",
            "attempt_count": 1,
            "last_attempted_at": None,
            "failure_reason": None,
            "created_at": None,
            "updated_at": None,
            "lease_token": LEASE_TOKEN,
            "lease_expires_at": LEASE_EXPIRES_AT,
        },
    ]
    identity_result = MagicMock()
    identity_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.side_effect = [
        MagicMock(),
        identity_result,
        MagicMock(),
        MagicMock(),
        normalize_result,
        claim_result,
    ]

    claimed = await repository.find_and_claim_jobs("RESET_WATERMARKS", batch_size=10)

    assert [job.payload["security_id"] for job in claimed] == ["S2", "S1"]


async def test_find_and_reset_stale_jobs_resets_processing_rows(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    stale_rows = [
        MagicMock(id=10, attempt_count=1),
        MagicMock(id=11, attempt_count=2),
    ]
    repository._claim_stale_job_cohort = AsyncMock(return_value=stale_rows)
    mock_update_result = MagicMock()
    mock_update_result.rowcount = 2
    mock_db_session.execute.return_value = mock_update_result

    reset_count = await repository.find_and_reset_stale_jobs(max_attempts=3)

    assert reset_count == 2
    assert mock_db_session.execute.await_count == 1
    update_stmt = mock_db_session.execute.await_args.args[0]
    assert "UPDATE reprocessing_jobs SET status=:status" in str(update_stmt)
    assert "reprocessing_jobs.status = :status_1" in str(update_stmt)
    assert "reprocessing_jobs.lease_expires_at <= clock_timestamp()" in str(update_stmt)


async def test_stale_reprocessing_recovery_bounds_selection_and_chunks_reset_updates(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    first_result = MagicMock(rowcount=1_000)
    second_result = MagicMock(rowcount=1)
    mock_db_session.execute.side_effect = [first_result, second_result]
    reset_count = await repository._reset_retryable_stale_jobs(list(range(1_001, 0, -1)))

    assert reset_count == 1_001
    assert mock_db_session.execute.await_count == 2
    statement_lengths = [
        len(call.args[0].compile().params["id_1"])
        for call in mock_db_session.execute.await_args_list
    ]
    assert statement_lengths == [1_000, 1]
    assert len(mock_db_session.execute.await_args_list[0].args[0].compile().params) == 6

    select_result = MagicMock()
    select_result.all.return_value = []
    mock_db_session.reset_mock()
    mock_db_session.execute.side_effect = None
    mock_db_session.execute.return_value = select_result
    await repository._find_stale_job_rows()
    compiled_select = str(
        mock_db_session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True})
    )
    assert (
        "ORDER BY reprocessing_jobs.lease_expires_at ASC, reprocessing_jobs.id ASC"
        in compiled_select
    )
    assert "LIMIT 1000" in compiled_select
    assert "FOR UPDATE" not in compiled_select


async def test_stale_reprocessing_claim_locks_rows_only_after_identity_phase(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    stale_row = MagicMock(
        id=10,
        attempt_count=1,
        job_type="RESET_WATERMARKS",
        payload={"security_id": "BOND-1", "earliest_impacted_date": "2026-08-01"},
        correlation_id="corr-claim-order",
        correlation_missing_reason=None,
        alternate_lookup_key=None,
        lease_expires_at=LEASE_EXPIRES_AT,
    )
    discovery_result = MagicMock()
    discovery_result.all.return_value = [stale_row]
    lock_result = MagicMock()
    claim_result = MagicMock()
    claim_result.all.return_value = [stale_row]
    unlock_result = MagicMock()
    unlock_result.scalar_one.return_value = True
    results = iter([discovery_result, lock_result, claim_result, unlock_result])
    call_order: list[str] = []

    def execute(statement, *_args):
        if "pg_advisory_lock" in str(statement):
            call_order.append("cohort_lock")
        if "pg_advisory_unlock" in str(statement):
            call_order.append("cohort_unlock")
        if "FOR UPDATE" in str(statement):
            call_order.append("row_cohort")
        return next(results)

    mock_db_session.execute.side_effect = execute
    savepoint = AsyncMock()
    mock_db_session.begin_nested.return_value = savepoint
    repository._lock_effective_dated_replay_identities = AsyncMock(
        side_effect=lambda _keys: call_order.append("identity_set")
    )

    claimed = await repository._claim_stale_job_cohort(max_attempts=3)

    assert claimed == [stale_row]
    discovery_sql = str(mock_db_session.execute.await_args_list[0].args[0])
    claim_sql = str(
        next(
            call.args[0]
            for call in mock_db_session.execute.await_args_list
            if "FOR UPDATE" in str(call.args[0])
        ).compile(dialect=postgresql.dialect())
    )
    assert "FOR UPDATE" not in discovery_sql
    assert "FOR UPDATE" in claim_sql
    assert "SKIP LOCKED" in claim_sql
    assert call_order == ["identity_set", "cohort_lock", "row_cohort", "cohort_unlock"]
    repository._lock_effective_dated_replay_identities.assert_awaited_once_with(
        ["RESET_WATERMARKS|6:BOND-1"]
    )
    savepoint.start.assert_awaited_once_with()
    savepoint.commit.assert_awaited_once_with()
    savepoint.rollback.assert_not_awaited()


async def test_stale_reprocessing_claim_rolls_back_before_advisory_unlock_on_failure(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    stale_row = MagicMock(
        id=10,
        attempt_count=1,
        job_type="LEASE_LIFECYCLE_PROOF",
        lease_expires_at=LEASE_EXPIRES_AT,
    )
    discovery_result = MagicMock()
    discovery_result.all.return_value = [stale_row]
    unlock_result = MagicMock()
    unlock_result.scalar_one.return_value = True
    call_order: list[str] = []
    savepoint = AsyncMock()

    async def record_rollback() -> None:
        call_order.append("savepoint_rollback")

    savepoint.rollback.side_effect = record_rollback
    mock_db_session.begin_nested.return_value = savepoint

    def execute(statement, *_args):
        sql = str(statement)
        if "pg_advisory_lock" in sql:
            call_order.append("cohort_lock")
            return MagicMock()
        if "pg_advisory_unlock" in sql:
            call_order.append("cohort_unlock")
            return unlock_result
        if "FOR UPDATE" in sql:
            call_order.append("row_cohort")
            raise RuntimeError("claim failed")
        call_order.append("discovery")
        return discovery_result

    mock_db_session.execute.side_effect = execute

    with pytest.raises(RuntimeError, match="claim failed"):
        await repository._claim_stale_job_cohort(max_attempts=3)

    assert call_order == [
        "discovery",
        "cohort_lock",
        "row_cohort",
        "savepoint_rollback",
        "cohort_unlock",
    ]
    savepoint.rollback.assert_awaited_once_with()
    savepoint.commit.assert_not_awaited()
    unlock_result.scalar_one.assert_called_once_with()


async def test_stale_reprocessing_recovery_logs_counts_without_identifier_collections(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value = MagicMock()

    with patch("portfolio_common.reprocessing_job_repository.logger.warning") as warning:
        await repository._mark_over_limit_stale_jobs_failed(
            [3, 2, 2, 1],
            max_attempts=3,
        )

    extra = warning.call_args.kwargs["extra"]
    assert extra["job_count"] == 3
    assert "job_ids" not in extra


async def test_find_and_reset_stale_jobs_is_noop_when_nothing_stale(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    repository._claim_stale_job_cohort = AsyncMock(return_value=[])

    reset_count = await repository.find_and_reset_stale_jobs()

    assert reset_count == 0
    assert mock_db_session.execute.await_count == 0


async def test_get_queue_stats_filters_by_job_type(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    result = MagicMock()
    result.one.return_value = MagicMock(
        pending_count=7,
        failed_count=2,
        oldest_pending_created_at=None,
    )
    mock_db_session.execute.return_value = result

    queue_stats = await repository.get_queue_stats("RESET_WATERMARKS")

    assert queue_stats == {
        "pending_count": 7,
        "failed_count": 2,
        "oldest_pending_created_at": None,
    }
    stmt = mock_db_session.execute.await_args.args[0]
    compiled_query = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "reprocessing_jobs.status IN ('PENDING', 'FAILED')" in compiled_query
    assert "reprocessing_jobs.job_type = 'RESET_WATERMARKS'" in compiled_query


async def test_find_and_reset_stale_jobs_marks_over_limit_rows_failed(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    stale_rows = [
        MagicMock(id=20, attempt_count=3),
        MagicMock(id=21, attempt_count=1),
    ]
    repository._claim_stale_job_cohort = AsyncMock(return_value=stale_rows)
    mock_failed_result = MagicMock()
    mock_reset_result = MagicMock()
    mock_reset_result.rowcount = 1
    mock_db_session.execute.side_effect = [
        mock_failed_result,
        mock_reset_result,
    ]

    reset_count = await repository.find_and_reset_stale_jobs(max_attempts=3)

    assert reset_count == 1


async def test_find_and_reset_stale_jobs_rechecks_processing_state_before_reset(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    repository._claim_stale_job_cohort = AsyncMock(return_value=[MagicMock(id=10, attempt_count=1)])
    mock_update_result = MagicMock()
    mock_update_result.rowcount = 0
    mock_db_session.execute.return_value = mock_update_result

    reset_count = await repository.find_and_reset_stale_jobs(max_attempts=3)

    assert reset_count == 0
    update_stmt = mock_db_session.execute.await_args.args[0]
    stmt_text = str(update_stmt)
    assert "reprocessing_jobs.status = :status_1" in stmt_text
    assert "reprocessing_jobs.lease_expires_at <= clock_timestamp()" in stmt_text


async def test_find_and_reset_stale_jobs_coalesces_retryable_fx_pair(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    stale_result = MagicMock()
    stale_result.all.return_value = [
        MagicMock(
            id=10,
            attempt_count=2,
            job_type="RESET_FX_WATERMARKS",
            payload={
                "from_currency": "USD",
                "to_currency": "SGD",
                "earliest_impacted_date": "2026-04-08",
                "content_hash": "sha256:" + ("a" * 64),
                "generated_at": "2026-04-10T08:00:00+00:00",
            },
            correlation_id="corr-stale",
            correlation_missing_reason=None,
            alternate_lookup_key=None,
            lease_token=LEASE_TOKEN,
        )
    ]
    repository._claim_stale_job_cohort = AsyncMock(return_value=stale_result.all.return_value)
    locked_result = MagicMock()
    locked_result.one_or_none.return_value = stale_result.all.return_value[0]
    quarantine_result = MagicMock()
    quarantine_result.mappings.return_value.all.return_value = []
    coalesce_result = MagicMock()
    complete_result = MagicMock(rowcount=1)
    mock_db_session.execute.side_effect = [
        locked_result,
        MagicMock(),
        quarantine_result,
        coalesce_result,
        complete_result,
    ]

    recovered_count = await repository.find_and_reset_stale_jobs(max_attempts=3)

    assert recovered_count == 1
    assert mock_db_session.execute.await_count == 5
    locked_row_statement = mock_db_session.execute.await_args_list[0].args[0]
    compiled_locked_row = str(locked_row_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "FOR UPDATE" in compiled_locked_row
    assert "lease_token" in compiled_locked_row
    assert "lease_expires_at <= clock_timestamp()" in compiled_locked_row
    repeated_lock_statement = mock_db_session.execute.await_args_list[1].args[0]
    assert "pg_advisory_xact_lock" in str(repeated_lock_statement)
    quarantine_statement = mock_db_session.execute.await_args_list[2].args[0]
    assert "pg_input_is_valid" in str(quarantine_statement)
    assert "FOR UPDATE" not in str(quarantine_statement)
    quarantine_sql = str(quarantine_statement)
    assert "btrim(payload->>'from_currency', :trim_chars)" in quarantine_sql
    quarantine_parameters = mock_db_session.execute.await_args_list[2].args[1]
    assert "\u00a0" in quarantine_parameters["trim_chars"]
    coalesce_statement, coalesce_parameters = mock_db_session.execute.await_args_list[3].args
    assert "GREATEST" in str(coalesce_statement)
    assert coalesce_parameters["attempt_count"] == 2
    complete_statement = mock_db_session.execute.await_args_list[4].args[0]
    compiled_complete = str(complete_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "Coalesced into pending FX replay during stale recovery" in compiled_complete


@pytest.mark.parametrize(
    ("job_type", "payload"),
    [
        (
            "RESET_FX_WATERMARKS",
            {
                "from_currency": "USD",
                "to_currency": "SGD",
                "earliest_impacted_date": "2026-04-08",
                "content_hash": "sha256:" + ("a" * 64),
                "generated_at": "not-a-timestamp",
            },
        ),
        (
            "RESET_FX_WATERMARKS",
            {
                "from_currency": "USD",
                "to_currency": "SGD",
                "earliest_impacted_date": "2026-04-08",
                "content_hash": "sha256:" + ("a" * 64),
                "generated_at": "2026-08-26T10:00:00",
            },
        ),
        (
            "RESET_WATERMARKS",
            {
                "security_id": "unsafe\x00identity",
                "earliest_impacted_date": "2026-04-08",
            },
        ),
        (
            "RESET_WATERMARKS",
            {
                "security_id": "unsafe\ud800identity",
                "earliest_impacted_date": "2026-04-08",
            },
        ),
        (
            "RESET_WATERMARKS",
            {
                "security_id": " SEC-1 ",
                "earliest_impacted_date": "2026-04-08",
            },
        ),
    ],
)
async def test_find_and_reset_stale_jobs_fails_malformed_effective_dated_replay(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
    job_type: str,
    payload: dict[str, str],
) -> None:
    stale_result = MagicMock()
    stale_result.all.return_value = [
        MagicMock(
            id=10,
            attempt_count=1,
            job_type=job_type,
            payload=payload,
        )
    ]
    repository._claim_stale_job_cohort = AsyncMock(return_value=stale_result.all.return_value)
    failed_result = MagicMock(rowcount=1)
    mock_db_session.execute.return_value = failed_result

    recovered_count = await repository.find_and_reset_stale_jobs(max_attempts=3)

    assert recovered_count == 0
    assert mock_db_session.execute.await_count == 1
    failed_statement = mock_db_session.execute.await_args.args[0]
    compiled_failed = str(failed_statement.compile(compile_kwargs={"literal_binds": True}))
    assert "status='FAILED'" in compiled_failed
    assert "Malformed effective-dated replay during stale recovery" in compiled_failed


async def test_stage_pending_fx_revaluation_requires_an_authoritative_instant(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    with pytest.raises(ValueError, match="generated_at must be timezone-aware"):
        await repository.stage_pending_fx_revaluation_job(
            from_currency="USD",
            to_currency="SGD",
            earliest_impacted_date=date(2026, 4, 8),
            content_hash="sha256:" + ("a" * 64),
            generated_at=datetime(2026, 8, 26, 10, 0),
            correlation_id="corr-naive-time",
            correlation_missing_reason=None,
            alternate_lookup_key=None,
            attempt_count=0,
        )

    mock_db_session.execute.assert_not_awaited()


async def test_stage_pending_fx_revaluation_preserves_quarantined_earliest_date(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    quarantine_result = MagicMock()
    quarantine_result.mappings.return_value.all.return_value = [
        {
            "id": 7,
            "payload": {
                "from_currency": "USD",
                "to_currency": "SGD",
                "earliest_impacted_date": "2026-04-06",
                "content_hash": "sha256:" + ("b" * 64),
                "generated_at": "not-a-timestamp",
            },
            "payload_json": (
                '{"from_currency":"USD","to_currency":"SGD","earliest_impacted_date":"2026-04-06"}'
            ),
            "status": "PENDING",
            "payload_representable": True,
            "earliest_date_representable": True,
            "generated_at_representable": False,
        }
    ]
    mock_db_session.execute.side_effect = [
        MagicMock(),
        quarantine_result,
        quarantine_result,
        MagicMock(),
        MagicMock(),
    ]

    await repository.stage_pending_fx_revaluation_job(
        from_currency="USD",
        to_currency="SGD",
        earliest_impacted_date=date(2026, 4, 8),
        content_hash="sha256:" + ("a" * 64),
        generated_at=datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc),
        correlation_id="corr-authoritative",
        correlation_missing_reason=None,
        alternate_lookup_key=None,
    )

    quarantine_statement = mock_db_session.execute.await_args_list[1].args[0]
    assert "FOR UPDATE" not in str(quarantine_statement)
    lock_statement = mock_db_session.execute.await_args_list[2].args[0]
    assert "FOR UPDATE" in str(lock_statement)
    quarantine_update = mock_db_session.execute.await_args_list[3].args[0]
    assert "status=:status" in str(quarantine_update)
    _, upsert_parameters = mock_db_session.execute.await_args_list[4].args
    assert upsert_parameters["effective_date"] == date(2026, 4, 6)


async def test_stage_reset_watermarks_preserves_quarantined_earliest_date(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    quarantine_result = MagicMock()
    quarantine_result.mappings.return_value.all.return_value = [
        {
            "id": 7,
            "payload": {
                "security_id": "BOND-1",
                "earliest_impacted_date": "2025-W01-2",
            },
            "payload_json": ('{"security_id":"BOND-1","earliest_impacted_date":"2025-W01-2"}'),
            "status": "PENDING",
            "payload_representable": True,
            "earliest_date_representable": False,
        }
    ]
    upsert_result = MagicMock()
    upsert_result.mappings.return_value.one.return_value = {
        "id": 8,
        "job_type": "RESET_WATERMARKS",
        "payload": {"security_id": "BOND-1", "earliest_impacted_date": "2024-12-31"},
        "status": "PENDING",
        "attempt_count": 0,
        "last_attempted_at": None,
        "failure_reason": None,
        "created_at": None,
        "updated_at": None,
        "was_inserted": True,
    }
    mock_db_session.execute.side_effect = [
        MagicMock(),
        quarantine_result,
        quarantine_result,
        MagicMock(),
        upsert_result,
    ]

    await repository.stage_reset_watermarks_job(
        security_id="BOND-1",
        earliest_impacted_date=date(2025, 1, 6),
        correlation_id="corr-authoritative",
    )

    quarantine_statement = mock_db_session.execute.await_args_list[1].args[0]
    assert "pg_input_is_valid" in str(quarantine_statement)
    assert "FOR UPDATE" not in str(quarantine_statement)
    lock_statement = mock_db_session.execute.await_args_list[2].args[0]
    assert "FOR UPDATE" in str(lock_statement)
    quarantine_update = mock_db_session.execute.await_args_list[3].args[0]
    assert "status=:status" in str(quarantine_update)
    _, upsert_parameters = mock_db_session.execute.await_args_list[4].args
    assert upsert_parameters["earliest_impacted_date"] == date(2024, 12, 31)


async def test_replay_trim_contract_matches_python_strip_whitespace() -> None:
    assert set(_REPLAY_TEXT_TRIM_CHARS) == {
        chr(codepoint) for codepoint in range(0x110000) if chr(codepoint).isspace()
    }


async def test_create_job_coalesces_pending_reset_watermarks_job(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    upsert_result = MagicMock()
    upsert_result.mappings.return_value.one.return_value = {
        "id": 10,
        "job_type": "RESET_WATERMARKS",
        "payload": {"security_id": "AAPL", "earliest_impacted_date": "2025-01-05"},
        "status": "PENDING",
        "attempt_count": 0,
        "last_attempted_at": None,
        "failure_reason": None,
        "created_at": None,
        "updated_at": None,
        "was_inserted": False,
    }
    mock_db_session.execute.return_value = upsert_result

    result = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "AAPL", "earliest_impacted_date": "2025-01-07"},
        correlation_id="corr-07",
    )

    assert result.id == 10
    assert result.payload["earliest_impacted_date"] == "2025-01-05"
    assert result.correlation_id is None
    mock_db_session.add.assert_not_called()
    mock_db_session.flush.assert_not_awaited()
    assert mock_db_session.execute.await_count == 3


async def test_create_job_updates_pending_reset_watermarks_job_to_earliest_date(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    upsert_result = MagicMock()
    upsert_result.mappings.return_value.one.return_value = {
        "id": 10,
        "job_type": "RESET_WATERMARKS",
        "payload": {"security_id": "AAPL", "earliest_impacted_date": "2025-01-05"},
        "status": "PENDING",
        "attempt_count": 0,
        "last_attempted_at": None,
        "failure_reason": None,
        "created_at": None,
        "updated_at": None,
        "was_inserted": False,
    }
    mock_db_session.execute.return_value = upsert_result

    result = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "AAPL", "earliest_impacted_date": "2025-01-05"},
        correlation_id="corr-05",
    )

    assert result.payload["earliest_impacted_date"] == "2025-01-05"
    assert result.correlation_id is None
    mock_db_session.add.assert_not_called()
    mock_db_session.flush.assert_not_awaited()
    assert mock_db_session.execute.await_count == 3


async def test_create_job_preserves_earliest_correlation_for_reset_watermarks(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    upsert_result = MagicMock()
    upsert_result.mappings.return_value.one.return_value = {
        "id": 11,
        "job_type": "RESET_WATERMARKS",
        "payload": {"security_id": "AAPL", "earliest_impacted_date": "2025-01-05"},
        "status": "PENDING",
        "correlation_id": "corr-05",
        "attempt_count": 0,
        "last_attempted_at": None,
        "failure_reason": None,
        "created_at": None,
        "updated_at": None,
        "was_inserted": False,
    }
    mock_db_session.execute.return_value = upsert_result

    result = await repository.create_job(
        "RESET_WATERMARKS",
        {"security_id": "AAPL", "earliest_impacted_date": "2025-01-05"},
        correlation_id="corr-05",
    )

    assert result.correlation_id == "corr-05"


@pytest.mark.parametrize(
    ("was_inserted", "expected_outcome"),
    [
        (True, ResetWatermarksStageOutcome.CREATED),
        (False, ResetWatermarksStageOutcome.COALESCED_PENDING),
    ],
)
async def test_stage_reset_watermarks_job_reports_exact_upsert_outcome(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
    was_inserted: bool,
    expected_outcome: ResetWatermarksStageOutcome,
) -> None:
    upsert_result = MagicMock()
    upsert_result.mappings.return_value.one.return_value = {
        "id": 12,
        "job_type": "RESET_WATERMARKS",
        "payload": {"security_id": "BOND-1", "earliest_impacted_date": "2025-01-05"},
        "status": "PENDING",
        "attempt_count": 0,
        "last_attempted_at": None,
        "failure_reason": None,
        "created_at": None,
        "updated_at": None,
        "was_inserted": was_inserted,
    }
    mock_db_session.execute.return_value = upsert_result

    result = await repository.stage_reset_watermarks_job(
        security_id="BOND-1",
        earliest_impacted_date=date(2025, 1, 5),
        correlation_id="corr-bond-1",
    )

    assert result.job.id == 12
    assert result.outcome is expected_outcome
    lock_statement, lock_parameters = mock_db_session.execute.await_args_list[0].args
    assert "pg_advisory_xact_lock" in str(lock_statement)
    assert lock_parameters == {"identity_key": "RESET_WATERMARKS|6:BOND-1"}
    statement = str(mock_db_session.execute.await_args.args[0])
    assert "(xmax = 0) AS was_inserted" in statement


async def test_reset_watermarks_batch_locks_unique_identities_in_global_order(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.return_value = MagicMock()

    await repository.lock_reset_watermarks_replay_identities(["LONG", "A", "LONG"])

    identity_keys = [
        call.args[1]["identity_key"] for call in mock_db_session.execute.await_args_list
    ]
    assert identity_keys == ["RESET_WATERMARKS|1:A", "RESET_WATERMARKS|4:LONG"]
    assert all(
        "pg_advisory_xact_lock" in str(call.args[0])
        for call in mock_db_session.execute.await_args_list
    )


async def test_create_job_sets_correlation_for_generic_jobs(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.refresh.return_value = None

    result = await repository.create_job(
        "OTHER_JOB",
        {"transaction_ids": ["T1"]},
        correlation_id="corr-generic",
    )

    assert result.correlation_id == "corr-generic"
    mock_db_session.add.assert_called_once()
    mock_db_session.flush.assert_awaited_once()


async def test_create_job_normalizes_sentinel_correlation_for_generic_jobs(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.refresh.return_value = None

    result = await repository.create_job(
        "OTHER_JOB",
        {"transaction_ids": ["T1"]},
        correlation_id="<not-set>",
    )

    assert result.correlation_id is None


async def test_update_job_status_requires_processing_ownership(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    update_result = MagicMock()
    update_result.rowcount = 0
    ownership_result = MagicMock()
    ownership_result.one_or_none.return_value = None
    mock_db_session.execute.side_effect = [update_result, ownership_result]

    outcome = await repository.update_job_status(99, "COMPLETE", lease_token=LEASE_TOKEN)

    assert outcome is ReprocessingJobTransitionOutcome.NOT_FOUND
    stmt = mock_db_session.execute.await_args_list[0].args[0]
    stmt_text = str(stmt)
    assert "reprocessing_jobs.status = :status_1" in stmt_text
    assert "reprocessing_jobs.lease_token = :lease_token_1" in stmt_text
    assert "reprocessing_jobs.lease_expires_at > clock_timestamp()" in stmt_text


async def test_owned_requeue_uses_repository_policy_for_direct_requeue(
    repository: ReprocessingJobRepository,
) -> None:
    identity = SimpleNamespace(identity_key="RESET_WATERMARKS|2:S1")
    repository._effective_dated_replay_identity = AsyncMock(return_value=identity)
    repository._lock_effective_dated_replay_identity = AsyncMock()
    repository._lock_live_owned_job = AsyncMock(return_value=True)
    repository._pending_replay_sibling_exists = AsyncMock(return_value=False)
    repository._apply_owned_transition = AsyncMock(
        return_value=ReprocessingJobTransitionOutcome.APPLIED
    )

    outcome = await repository.requeue_owned_effective_dated_job(
        99,
        lease_token=LEASE_TOKEN,
    )

    assert outcome is ReprocessingJobTransitionOutcome.REQUEUED
    repository._lock_effective_dated_replay_identity.assert_awaited_once_with(identity.identity_key)
    repository._apply_owned_transition.assert_awaited_once_with(
        99,
        "PENDING",
        lease_token=LEASE_TOKEN,
    )


async def test_reset_pending_sibling_lookup_uses_normalized_identity(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    sibling_result = MagicMock()
    sibling_result.mappings.return_value.all.return_value = [
        {
            "id": 12,
            "payload": {"security_id": " BOND-1 "},
            "payload_json": '{"security_id":" BOND-1 "}',
        }
    ]
    mock_db_session.execute.return_value = sibling_result
    identity = SimpleNamespace(
        job_type="RESET_WATERMARKS",
        payload={"security_id": "BOND-1"},
    )

    exists = await repository._pending_replay_sibling_exists(
        job_id=11,
        identity=identity,
    )

    assert exists is True
    scan_statement, scan_parameters = mock_db_session.execute.await_args_list[0].args
    scan_sql = str(scan_statement)
    assert "btrim(payload->>'security_id', :trim_chars)" in scan_sql
    assert "jsonb_typeof" not in scan_sql
    assert "pg_input_is_valid(payload::text, 'jsonb') IS NOT TRUE THEN TRUE" in scan_sql
    assert "FOR UPDATE" not in scan_sql
    assert scan_parameters == {
        "job_id": 11,
        "security_id": "BOND-1",
        "trim_chars": _REPLAY_TEXT_TRIM_CHARS,
    }
    lock_statement, lock_parameters = mock_db_session.execute.await_args_list[1].args
    assert "FOR UPDATE" in str(lock_statement)
    assert lock_parameters == {
        "candidate_ids": [12],
        "malformed_candidate_ids": [],
        "job_type": "RESET_WATERMARKS",
    }


async def test_owned_requeue_coalesces_pending_sibling_before_completing_claim(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    identity = SimpleNamespace(identity_key="RESET_WATERMARKS|2:S1")
    savepoint = AsyncMock()
    call_order: list[str] = []
    savepoint.start.side_effect = lambda: call_order.append("savepoint_started")
    mock_db_session.begin_nested.return_value = savepoint
    repository._effective_dated_replay_identity = AsyncMock(return_value=identity)
    repository._lock_effective_dated_replay_identity = AsyncMock()
    repository._lock_live_owned_job = AsyncMock(return_value=True)
    repository._pending_replay_sibling_exists = AsyncMock(return_value=True)
    repository._coalesce_pending_replay = AsyncMock(
        side_effect=lambda _identity: call_order.append("sibling_coalesced")
    )
    repository._apply_owned_transition = AsyncMock(
        return_value=ReprocessingJobTransitionOutcome.APPLIED
    )

    outcome = await repository.requeue_owned_effective_dated_job(
        99,
        lease_token=LEASE_TOKEN,
    )

    assert outcome is ReprocessingJobTransitionOutcome.COALESCED_PENDING
    assert call_order == ["savepoint_started", "sibling_coalesced"]
    savepoint.start.assert_awaited_once_with()
    repository._coalesce_pending_replay.assert_awaited_once_with(identity)
    repository._apply_owned_transition.assert_awaited_once_with(
        99,
        "COMPLETE",
        lease_token=LEASE_TOKEN,
    )
    savepoint.commit.assert_awaited_once()
    savepoint.rollback.assert_not_awaited()


async def test_owned_requeue_rolls_back_sibling_change_after_lease_loss(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    identity = SimpleNamespace(identity_key="RESET_WATERMARKS|2:S1")
    savepoint = AsyncMock()
    mock_db_session.begin_nested.return_value = savepoint
    repository._effective_dated_replay_identity = AsyncMock(return_value=identity)
    repository._lock_effective_dated_replay_identity = AsyncMock()
    repository._lock_live_owned_job = AsyncMock(return_value=True)
    repository._pending_replay_sibling_exists = AsyncMock(return_value=True)
    repository._coalesce_pending_replay = AsyncMock()
    repository._apply_owned_transition = AsyncMock(
        return_value=ReprocessingJobTransitionOutcome.LEASE_EXPIRED
    )

    outcome = await repository.requeue_owned_effective_dated_job(
        99,
        lease_token=LEASE_TOKEN,
    )

    assert outcome is ReprocessingJobTransitionOutcome.LEASE_EXPIRED
    savepoint.start.assert_awaited_once_with()
    savepoint.rollback.assert_awaited_once()
    savepoint.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("status", "lease_token", "lease_expired", "expected"),
    [
        ("COMPLETE", LEASE_TOKEN, False, ReprocessingJobTransitionOutcome.NOT_PROCESSING),
        (
            "PROCESSING",
            "b" * 32,
            False,
            ReprocessingJobTransitionOutcome.CLAIM_MISMATCH,
        ),
        ("PROCESSING", LEASE_TOKEN, True, ReprocessingJobTransitionOutcome.LEASE_EXPIRED),
        ("PROCESSING", LEASE_TOKEN, False, ReprocessingJobTransitionOutcome.RACED),
    ],
)
async def test_update_job_status_classifies_refused_transition(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
    status: str,
    lease_token: str,
    lease_expired: bool,
    expected: ReprocessingJobTransitionOutcome,
) -> None:
    update_result = MagicMock()
    update_result.rowcount = 0
    ownership_result = MagicMock()
    ownership_result.one_or_none.return_value = SimpleNamespace(
        status=status,
        lease_token=lease_token,
        lease_expired=lease_expired,
    )
    mock_db_session.execute.side_effect = [update_result, ownership_result]

    outcome = await repository.update_job_status(99, "COMPLETE", lease_token=LEASE_TOKEN)

    assert outcome is expected


async def test_renew_lease_uses_database_clock_and_exact_claim(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    update_result = MagicMock()
    update_result.rowcount = 1
    mock_db_session.execute.return_value = update_result

    outcome = await repository.renew_lease(
        99,
        lease_token=LEASE_TOKEN,
        lease_duration_seconds=120,
    )

    assert outcome is ReprocessingJobTransitionOutcome.APPLIED
    statement = str(mock_db_session.execute.await_args.args[0])
    assert "reprocessing_jobs.lease_token = :lease_token_1" in statement
    assert "reprocessing_jobs.lease_expires_at > clock_timestamp()" in statement
    assert "clock_timestamp() + make_interval" in statement


async def test_get_lease_remaining_seconds_uses_database_clock(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    mock_db_session.execute.side_effect = [
        MagicMock(one_or_none=MagicMock(return_value=MagicMock(lease_remaining_seconds=87.5)))
    ]

    remaining = await repository.get_lease_remaining_seconds(
        99,
        lease_token=LEASE_TOKEN,
    )

    assert remaining == 87.5
    statement = str(mock_db_session.execute.await_args.args[0])
    assert "EXTRACT(epoch" in statement
    assert "reprocessing_jobs.lease_expires_at - clock_timestamp()" in statement
    assert "reprocessing_jobs.lease_expires_at > clock_timestamp()" in statement


@pytest.mark.parametrize(
    ("lease_token", "lease_duration_seconds", "message"),
    [
        ("", 120, "token is required"),
        (LEASE_TOKEN, 0, "duration must be positive"),
    ],
)
async def test_renew_lease_rejects_invalid_authority(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
    lease_token: str,
    lease_duration_seconds: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        await repository.renew_lease(
            99,
            lease_token=lease_token,
            lease_duration_seconds=lease_duration_seconds,
        )

    mock_db_session.execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("status", "failure_reason", "message"),
    [
        ("PROCESSING", None, "transition status"),
        ("PENDING", None, "transition status"),
        ("COMPLETE", "unexpected", "failure reason"),
        ("FAILED", None, "requires a failure reason"),
        ("FAILED", " ", "requires a failure reason"),
    ],
)
async def test_update_job_status_rejects_invalid_owned_transition(
    repository: ReprocessingJobRepository,
    mock_db_session: AsyncMock,
    status: str,
    failure_reason: str | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        await repository.update_job_status(
            99,
            status,
            lease_token=LEASE_TOKEN,
            failure_reason=failure_reason,
        )

    mock_db_session.execute.assert_not_awaited()
