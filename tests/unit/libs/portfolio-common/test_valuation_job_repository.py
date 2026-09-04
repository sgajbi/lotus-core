# tests/unit/libs/portfolio-common/test_valuation_job_repository.py
from datetime import date
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from portfolio_common.infrastructure.persistence.statement_batching import (
    POSTGRES_STATEMENT_ROW_LIMIT,
)
from portfolio_common.valuation_job_contracts import (
    ValuationJobUpsert as ContractValuationJobUpsert,
)
from portfolio_common.valuation_job_repository import (
    ValuationJobRepository,
    ValuationJobUpsert,
    _valuation_job_upsert_stmt,
)

pytestmark = pytest.mark.asyncio


async def test_repository_preserves_valuation_job_upsert_import_compatibility() -> None:
    assert ValuationJobUpsert is ContractValuationJobUpsert


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def repository(mock_db_session: AsyncMock) -> ValuationJobRepository:
    """Provides an instance of the repository with a mock session."""
    return ValuationJobRepository(mock_db_session)


@patch("portfolio_common.valuation_job_repository.pg_insert")
async def test_upsert_job_builds_correct_statement(
    mock_pg_insert, repository: ValuationJobRepository, mock_db_session: AsyncMock
):
    """
    GIVEN valuation job details including an epoch
    WHEN upsert_job is called
    THEN it should construct an insert statement with the correct values and
    on_conflict_do_update clause.
    """
    # Arrange
    mock_final_statement = MagicMock()
    mock_returning_statement = MagicMock()
    (
        mock_pg_insert.return_value.values.return_value.on_conflict_do_update.return_value
    ) = mock_final_statement
    mock_final_statement.returning.return_value = mock_returning_statement
    latest_epoch_result = MagicMock()
    latest_epoch_result.all.return_value = []
    insert_result = MagicMock()
    insert_result.all.return_value = [("PORT_VJR_01", "SEC_VJR_01", date(2025, 8, 11), 1)]
    skip_result = MagicMock()
    skip_result.fetchall.return_value = []
    mock_db_session.execute.side_effect = [latest_epoch_result, insert_result, skip_result]

    job_details = {
        "portfolio_id": "PORT_VJR_01",
        "security_id": "SEC_VJR_01",
        "valuation_date": date(2025, 8, 11),
        "epoch": 1,
        "correlation_id": "corr-vjr-123",
    }

    # Act
    await repository.upsert_job(**job_details)

    # Assert
    mock_pg_insert.return_value.values.assert_called_once()
    called_values = mock_pg_insert.return_value.values.call_args.args[0]
    assert len(called_values) == 1
    assert called_values[0]["portfolio_id"] == job_details["portfolio_id"]
    assert called_values[0]["epoch"] == job_details["epoch"]
    assert called_values[0]["status"] == "PENDING"

    mock_pg_insert.return_value.values.return_value.on_conflict_do_update.assert_called_once_with(
        index_elements=["portfolio_id", "security_id", "valuation_date", "epoch"],
        set_=ANY,
        where=ANY,
    )

    assert mock_db_session.execute.await_count == 3
    assert mock_final_statement.returning.call_count == 1
    assert mock_db_session.execute.await_args_list[1].args[0] == mock_returning_statement


@patch("portfolio_common.valuation_job_repository.pg_insert")
async def test_upsert_job_skips_when_newer_epoch_already_exists(
    mock_pg_insert, repository: ValuationJobRepository, mock_db_session: AsyncMock
):
    latest_epoch_result = MagicMock()
    latest_epoch_result.all.return_value = [("PORT_VJR_02", "SEC_VJR_02", date(2025, 8, 12), 3)]
    mock_db_session.execute.return_value = latest_epoch_result

    await repository.upsert_job(
        portfolio_id="PORT_VJR_02",
        security_id="SEC_VJR_02",
        valuation_date=date(2025, 8, 12),
        epoch=2,
        correlation_id="corr-vjr-stale",
    )

    mock_pg_insert.assert_not_called()
    mock_db_session.execute.assert_awaited_once()


@patch("portfolio_common.valuation_job_repository.pg_insert")
async def test_upsert_job_normalizes_sentinel_correlation(
    mock_pg_insert, repository: ValuationJobRepository, mock_db_session: AsyncMock
):
    latest_epoch_result = MagicMock()
    latest_epoch_result.all.return_value = []
    insert_result = MagicMock()
    insert_result.all.return_value = [("P1", "S1", date(2025, 8, 10), 1)]
    skip_result = MagicMock()
    skip_result.fetchall.return_value = []
    mock_db_session.execute.side_effect = [latest_epoch_result, insert_result, skip_result]

    await repository.upsert_job(
        portfolio_id="P1",
        security_id="S1",
        valuation_date=date(2025, 8, 10),
        epoch=1,
        correlation_id="<not-set>",
    )

    values_args = mock_pg_insert.return_value.values.call_args.args[0]
    assert values_args[0]["correlation_id"] is None
    assert values_args[0]["correlation_missing_reason"] == "correlation_id_not_supplied"
    assert values_args[0]["alternate_lookup_key"] == (
        "valuation_job|epoch=1|portfolio_id=P1|security_id=S1|valuation_date=2025-08-10"
    )


@patch("portfolio_common.valuation_job_repository.pg_insert")
async def test_upsert_job_marks_prior_pending_epochs_as_superseded(
    mock_pg_insert, repository: ValuationJobRepository, mock_db_session: AsyncMock
):
    mock_final_statement = MagicMock()
    mock_returning_statement = MagicMock()
    (
        mock_pg_insert.return_value.values.return_value.on_conflict_do_update.return_value
    ) = mock_final_statement
    mock_final_statement.returning.return_value = mock_returning_statement
    latest_epoch_result = MagicMock()
    latest_epoch_result.all.return_value = [("P1", "S1", date(2025, 8, 10), 1)]
    insert_result = MagicMock()
    insert_result.all.return_value = [("P1", "S1", date(2025, 8, 10), 2)]
    skip_result = MagicMock()
    skip_result.fetchall.return_value = [(101,)]
    mock_db_session.execute.side_effect = [latest_epoch_result, insert_result, skip_result]

    await repository.upsert_job(
        portfolio_id="P1",
        security_id="S1",
        valuation_date=date(2025, 8, 10),
        epoch=2,
        correlation_id="corr-vjr-002",
    )

    skip_stmt = mock_db_session.execute.await_args_list[-1].args[0]
    compiled_query = str(skip_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "SKIPPED_SUPERSEDED" in compiled_query
    assert "Superseded by newer valuation epoch." in compiled_query
    assert "portfolio_valuation_jobs.epoch < 2" in compiled_query


@patch("portfolio_common.valuation_job_repository.pg_insert")
async def test_upsert_job_does_not_rearm_processing_job_with_same_correlation(
    mock_pg_insert, repository: ValuationJobRepository, mock_db_session: AsyncMock
):
    mock_final_statement = MagicMock()
    mock_returning_statement = MagicMock()
    (
        mock_pg_insert.return_value.values.return_value.on_conflict_do_update.return_value
    ) = mock_final_statement
    mock_final_statement.returning.return_value = mock_returning_statement
    latest_epoch_result = MagicMock()
    latest_epoch_result.all.return_value = [("P1", "S1", date(2025, 8, 10), 2)]
    insert_result = MagicMock()
    insert_result.all.return_value = []
    skip_result = MagicMock()
    skip_result.fetchall.return_value = []
    mock_db_session.execute.side_effect = [latest_epoch_result, insert_result, skip_result]

    await repository.upsert_job(
        portfolio_id="P1",
        security_id="S1",
        valuation_date=date(2025, 8, 10),
        epoch=2,
        correlation_id="corr-processing",
    )

    mock_pg_insert.return_value.values.return_value.on_conflict_do_update.assert_called_once_with(
        index_elements=["portfolio_id", "security_id", "valuation_date", "epoch"],
        set_=ANY,
        where=ANY,
    )
    where_clause = (
        mock_pg_insert.return_value.values.return_value.on_conflict_do_update.call_args.kwargs[
            "where"
        ]
    )
    compiled_where = str(where_clause.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_valuation_jobs.status != 'PROCESSING'" in compiled_where
    assert "portfolio_valuation_jobs.status = 'PENDING'" in compiled_where
    assert "IS NOT DISTINCT FROM" in compiled_where
    assert "portfolio_valuation_jobs.status NOT IN ('COMPLETE', 'FAILED')" in compiled_where


@patch("portfolio_common.valuation_job_repository.pg_insert")
async def test_explicit_source_correction_can_rearm_completed_job(
    mock_pg_insert, repository: ValuationJobRepository, mock_db_session: AsyncMock
) -> None:
    mock_final_statement = MagicMock()
    mock_returning_statement = MagicMock()
    (
        mock_pg_insert.return_value.values.return_value.on_conflict_do_update.return_value
    ) = mock_final_statement
    mock_final_statement.returning.return_value = mock_returning_statement
    latest_epoch_result = MagicMock()
    latest_epoch_result.all.return_value = [("P1", "S1", date(2025, 8, 10), 2)]
    insert_result = MagicMock()
    insert_result.all.return_value = [("P1", "S1", date(2025, 8, 10), 2)]
    skip_result = MagicMock()
    skip_result.fetchall.return_value = []
    mock_db_session.execute.side_effect = [latest_epoch_result, insert_result, skip_result]

    await repository.upsert_job(
        portfolio_id="P1",
        security_id="S1",
        valuation_date=date(2025, 8, 10),
        epoch=2,
        correlation_id="corr-source-correction",
        rearm_completed=True,
    )

    where_clause = (
        mock_pg_insert.return_value.values.return_value.on_conflict_do_update.call_args.kwargs[
            "where"
        ]
    )
    compiled_where = str(where_clause.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolio_valuation_jobs.status != 'PROCESSING'" in compiled_where
    assert "portfolio_valuation_jobs.status NOT IN ('COMPLETE', 'FAILED')" not in compiled_where


async def test_source_requeue_requires_transport_neutral_correction_identity(
    repository: ValuationJobRepository,
) -> None:
    with pytest.raises(ValueError, match="source_correction_id is required"):
        await repository.upsert_job(
            portfolio_id="P1",
            security_id="S1",
            valuation_date=date(2025, 8, 10),
            epoch=2,
            correlation_id="shared-transport-correlation",
            requeue_if_processing=True,
        )


async def test_source_requeue_compares_correction_identity_not_transport_correlation() -> None:
    statement = _valuation_job_upsert_stmt(
        [
            ValuationJobUpsert(
                portfolio_id="P1",
                security_id="S1",
                valuation_date=date(2025, 8, 10),
                epoch=2,
                correlation_id="shared-transport-correlation",
                source_correction_id="sha256:" + ("a" * 64),
            )
        ],
        requeue_if_processing=True,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    conflict_predicate = compiled.rsplit(" WHERE ", maxsplit=1)[-1]
    assert "source_correction_id IS NOT DISTINCT FROM excluded.source_correction_id" in (
        conflict_predicate
    )
    assert "correlation_id IS NOT DISTINCT FROM excluded.correlation_id" not in conflict_predicate


async def test_position_readiness_fence_compares_exact_outbox_sequence() -> None:
    statement = _valuation_job_upsert_stmt(
        [
            ValuationJobUpsert(
                portfolio_id="P1",
                security_id="S1",
                valuation_date=date(2025, 8, 10),
                epoch=2,
                correlation_id="readiness-correlation",
                source_correction_id="sha256:" + ("b" * 64),
                readiness_outbox_id=417,
            )
        ],
        rearm_completed=True,
        requeue_if_processing=True,
        fence_by_readiness_sequence=True,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    conflict_predicate = compiled.rsplit(" WHERE ", maxsplit=1)[-1]
    assert "417 > portfolio_valuation_jobs.claimed_readiness_outbox_id" in conflict_predicate
    assert "portfolio_valuation_jobs.claimed_readiness_outbox_id" in conflict_predicate
    assert "excluded.claimed_readiness_outbox_id" not in conflict_predicate
    assert "claimed_readiness_outbox_id" in compiled
    assert "417" not in compiled.split("ON CONFLICT", maxsplit=1)[0]


async def test_position_readiness_uses_revision_fenced_upsert(
    repository: ValuationJobRepository,
) -> None:
    repository._upsert_jobs = AsyncMock(return_value=1)  # type: ignore[method-assign]

    count = await repository.upsert_position_readiness_job(
        portfolio_id="P1",
        security_id="S1",
        valuation_date=date(2025, 8, 10),
        epoch=2,
        correlation_id="readiness-correlation",
        source_mutation_id="sha256:" + ("c" * 64),
        readiness_outbox_id=418,
    )

    assert count == 1
    repository._upsert_jobs.assert_awaited_once()  # type: ignore[attr-defined]
    assert repository._upsert_jobs.await_args.kwargs == {  # type: ignore[attr-defined]
        "rearm_completed": True,
        "requeue_if_processing": True,
        "fence_by_readiness_sequence": True,
    }


async def test_upsert_jobs_deduplicates_duplicate_requests(repository: ValuationJobRepository):
    jobs = [
        ValuationJobUpsert(
            portfolio_id="P1",
            security_id="S1",
            valuation_date=date(2025, 8, 10),
            epoch=1,
            correlation_id="corr-1",
        ),
        ValuationJobUpsert(
            portfolio_id="P1",
            security_id="S1",
            valuation_date=date(2025, 8, 10),
            epoch=1,
            correlation_id="corr-2",
        ),
    ]

    normalized_jobs = repository._normalize_jobs(jobs)

    assert normalized_jobs == [
        ValuationJobUpsert(
            portfolio_id="P1",
            security_id="S1",
            valuation_date=date(2025, 8, 10),
            epoch=1,
            correlation_id="corr-2",
        )
    ]


async def test_upsert_jobs_normalizes_reversed_inputs_to_unique_key_lock_order(
    repository: ValuationJobRepository,
):
    jobs = [
        ValuationJobUpsert("P2", "S1", date(2025, 8, 9), 1, "corr-3"),
        ValuationJobUpsert("P1", "S2", date(2025, 8, 10), 1, "corr-2"),
        ValuationJobUpsert("P1", "S1", date(2025, 8, 11), 2, "corr-1"),
    ]

    normalized_jobs = repository._normalize_jobs(jobs)

    assert [
        (job.portfolio_id, job.security_id, job.valuation_date, job.epoch)
        for job in normalized_jobs
    ] == [
        ("P1", "S1", date(2025, 8, 11), 2),
        ("P1", "S2", date(2025, 8, 10), 1),
        ("P2", "S1", date(2025, 8, 9), 1),
    ]


@patch("portfolio_common.valuation_job_repository._valuation_job_upsert_stmt")
async def test_high_fanout_upserts_use_bind_safe_ordered_statement_chunks(
    mock_upsert_statement,
    repository: ValuationJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    returning_statement = MagicMock()
    mock_upsert_statement.return_value.returning.return_value = returning_statement
    first_result = MagicMock()
    first_result.all.return_value = [()] * POSTGRES_STATEMENT_ROW_LIMIT
    second_result = MagicMock()
    second_result.all.return_value = [()]
    mock_db_session.execute.side_effect = [first_result, second_result]
    jobs = [
        ValuationJobUpsert(
            "P-HIGH-FANOUT",
            f"S-{index:05d}",
            date(2025, 8, 12),
            1,
            "corr-high-fanout",
        )
        for index in range(POSTGRES_STATEMENT_ROW_LIMIT + 1)
    ]

    staged_count = await repository._execute_upsert_jobs(
        jobs,
        rearm_completed=True,
        requeue_if_processing=True,
    )

    assert staged_count == POSTGRES_STATEMENT_ROW_LIMIT + 1
    assert [len(call.args[0]) for call in mock_upsert_statement.call_args_list] == [
        POSTGRES_STATEMENT_ROW_LIMIT,
        1,
    ]
    assert all(
        call.kwargs
        == {
            "rearm_completed": True,
            "requeue_if_processing": True,
            "fence_by_readiness_sequence": False,
        }
        for call in mock_upsert_statement.call_args_list
    )
    assert mock_db_session.execute.await_count == 2


async def test_high_fanout_epoch_lookup_uses_bind_safe_statement_chunks(
    repository: ValuationJobRepository,
    mock_db_session: AsyncMock,
) -> None:
    first_result = MagicMock()
    first_result.all.return_value = [("P-HIGH-FANOUT", "S-00000", date(2025, 8, 12), 3)]
    second_result = MagicMock()
    second_result.all.return_value = [
        (
            "P-HIGH-FANOUT",
            f"S-{POSTGRES_STATEMENT_ROW_LIMIT:05d}",
            date(2025, 8, 12),
            4,
        )
    ]
    mock_db_session.execute.side_effect = [first_result, second_result]
    jobs = [
        ValuationJobUpsert(
            "P-HIGH-FANOUT",
            f"S-{index:05d}",
            date(2025, 8, 12),
            1,
            "corr-high-fanout",
        )
        for index in range(POSTGRES_STATEMENT_ROW_LIMIT + 1)
    ]

    latest_epochs = await repository.get_latest_epochs_for_scopes(jobs)

    assert latest_epochs == {
        ("P-HIGH-FANOUT", "S-00000", date(2025, 8, 12)): 3,
        (
            "P-HIGH-FANOUT",
            f"S-{POSTGRES_STATEMENT_ROW_LIMIT:05d}",
            date(2025, 8, 12),
        ): 4,
    }
    assert mock_db_session.execute.await_count == 2
